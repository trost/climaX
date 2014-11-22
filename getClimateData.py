#!/usr/bin/env python

import sys
sys.path.append('/home/schudoma/projects/trost/QSolanum')
sys.path.append('/home/schudoma/projects/trost/QSolanum/climaX')

from itertools import starmap
from datetime import datetime

import os 
import pickle

from vpd_heatsum import calc_VPD
import login
DB = login.get_db()
C = DB.cursor()



CLIMATE_QUERY1 = """
SELECT 
DATE(T.datum), 
T.tmin, 
T.tmax, 
P.amount,
SUM(SC.amount)
FROM temperatures T 
JOIN cultures C ON C.location_id = T.location_id 
 AND year(C.planted) = 2012 
JOIN solarCalc_hourlySolarRadiation SC ON DATE(SC.datum) = T.datum
 AND SC.location_id = T.location_id
 AND year(SC.datum) = 2012
LEFT OUTER JOIN precipitation P ON P.datum = T.datum 
 AND P.location_id = T.location_id 
WHERE C.id = 56878
 AND year(T.datum) = 2012 
 AND T.datum < '2012-06-08' 
 AND (T.datum >= C.planted - interval 14 day) 
 AND T.datum <= C.terminated 
GROUP BY DATE(T.datum)
ORDER BY T.datum;
""".strip().replace('\n', '')

PREC_QUERY = """
SELECT 
DATE(P.datum),
P.amount
FROM precipitation P 
JOIN cultures C ON P.location_id = C.location_id 
WHERE C.id = 56878 
ORDER BY P.datum; 
""".strip().replace('\n', ' ')

IRRI_QUERY = """
SELECT
DATE(I.datum),
I.amount,
I.treatment_id
FROM irrigation I
WHERE I.culture_id = 56878 
ORDER BY I.datum;
""".strip().replace('\n', ' ')



CLIMATE_QUERY2 = """
SELECT 
TAHV.datum, 
TAHV.amount,
FFHM.amount,
UUHV.amount
FROM cultures C 
JOIN usesWeatherStation uWS ON uWS.location_id = C.location_id 
 AND C.id = 56878
JOIN dwd_hourlyAirTemperature_TAHV TAHV ON TAHV.station_id = uWS.station_id
 AND year(TAHV.datum) = year(C.planted)
JOIN dwd_hourlyMeanWindspeed_FFHM FFHM ON FFHM.station_id = uWS.station_id
 AND FFHM.datum = TAHV.datum
JOIN dwd_hourlyRelHumidity_UUHV UUHV ON UUHV.station_id = uWS.station_id
 AND UUHV.datum = TAHV.datum
WHERE C.id = 56878
 AND year(TAHV.datum) = 2012 
 -- AND TAHV.datum < '2012-06-08' 
 AND (TAHV.datum >= C.planted + interval 14 day) 
 AND TAHV.datum <= C.terminated 
GROUP BY TAHV.datum
ORDER BY TAHV.datum;
""".strip().replace('\n', ' ')



def calculateTemperatureStress(rawData, tub=30.0, tlb=8.0):
    
    stressScore = lambda x:len(x) * sum(x)/len(x)

    coldDays, hotDays = [], []
    loTemp, hiTemp = tlb, tub
    for day in rawData:        
        if day[1] < tlb:
            coldDays.append(abs(tlb - day[1]))
            loTemp = min(day[1])
        elif day[2] > tub:
            hotDays.append(abs(day[2] - tub))
            hiTemp = max(day[2])
        pass
    return stressScore(coldDays), stressScore(hotDays)

def calculateSoilWater(precipitation, evaporation,  
                       soilVolume, availMoistCap, irrigation=dict()):  
    
    soilWater = []
    dates = sorted(evaporation)
    initSoilWater = 0

    soilWater.append(0) # initial 
    # Initial 14 days (0-13) ... sum up water gain up to soil capacity
    for date_ in dates[:14]:

        waterGain = precipitation.get(date_, [0.0])[0] + irrigation.get(date_, [0.0])[0]
        soilWater.append(min(soilVolume, waterGain + soilWater[-1]))
        
        #initSoilWater += precipitation.get(date_, [0.0])[0]
        #initSoilWater += irrigation.get(date_, [0.0])[0]
        


    #initSoilWater = min(soilVolume, initSoilWater)
    #soilWater.append(initSoilWater)
    
    # From day 14 on calculate net water = soilWater from day before + evaporation loss + water gain
    for date_ in dates[14:]:
        evaporationLoss = evaporation.get(date_, 0.0)
        # print precipitation.get(date_, 0.0), irrigation.get(date_, [0.0])[0]

        waterGain = precipitation.get(date_, [0.0])[0] + irrigation.get(date_, [0.0])[0]  
        # netwater = (soilVolume, last computed soilwater + evaporation loss + water gain)
        netWater = soilWater[-1] + evaporationLoss + waterGain  #soilVolume,  


        soilWater.append(max(min(netWater, soilVolume), 0))

    # del soilWater[0]
    # return dict(zip(dates[14:], soilWater[1:]))
    return dict(zip(dates, soilWater[1:]))


def calculateEvaporation(rawData):
    """
    ATT: rel. humidity is coming in as percentage, needs to be fraction
    """
    def PenmanEvaporation(vpd, windspeed):
        """ 
        Calculates evaporation in mm/day from 
        vapour pressure deficit and windspeed.
        Formula from Principles of Environmental Physics (Penman 1948)

        ATT: Windspeed is coming in as m/s, needs to be mph
        """
        ms_to_mph = 2.23693629205
        return 0.376 * vpd * (windspeed * ms_to_mph) ** 0.76

    # data format: [date, temperature, windspeed, relHumidity] 
    dates = [row[0].date() for row in rawData]
    windSpeeds = [row[2] for row in rawData]
    vpd = starmap(calc_VPD, [(row[1], row[3]/100.0) for row in rawData])    
    dailyVPD = {date_: [] for date_ in set(dates)}
    dailyWindSpeed = {date_: [] for date_ in dailyVPD}
    for date_, vpd in zip(dates, vpd):
        dailyVPD[date_].append(vpd)
    for date_, windSpeed in zip(dates, windSpeeds):
        dailyWindSpeed[date_].append(windSpeed)
    
    def mean(numbers):
        return sum(numbers) / float(len(numbers))

    # return daily PenmanEvaporation for daily means of vpd and windspeed
    return {date_: PenmanEvaporation(mean(dailyVPD[date_]),
                                     mean(dailyWindSpeed[date_])) 
            
            for date_ in dates}

def main(argv):
    
    # Parameters for Area 5544 (Atting), ooo spooky :O
    soilVolume, availMoistCap = 42, 0.14


    C.execute(PREC_QUERY)
    precipitation = dict(map(lambda x:(x[0], x[1:]), 
                             [row for row in C.fetchall()]))
    C.execute(IRRI_QUERY)
    irrigation = dict(map(lambda x:(x[0].date(), x[1:]), 
                          [row for row in C.fetchall()]))

    if not os.path.exists('evaporation.dat'):
        print 'de novo'
        C.execute(CLIMATE_QUERY2)

        evaporation = calculateEvaporation([row for row in C.fetchall()])        
        pickle.dump(evaporation, open('evaporation.dat', 'wb'))
    else:
        evaporation = pickle.load(open('evaporation.dat'))


        
    soilWater = calculateSoilWater(precipitation, evaporation, 
                                   soilVolume, availMoistCap, 
                                   irrigation=irrigation)

    

    for date_ in sorted(soilWater):
        print date_, soilWater[date_]


    

    pass


if __name__ == '__main__': main(sys.argv[1:])
