#!/usr/bin/env python

import sys
from itertools import starmap
from datetime import date
import argparse

from vpd_heatsum import calc_VPD
from queries import PREC_QUERY, IRRI_QUERY, FAST_CLIMATE_QUERY, DAYLIGHT_QUERY
import login  # TODO: get the real login module from Christian, this is fake


DB = login.get_db()
C = DB.cursor()


def calculateLightIntensity(rawData, flowerDate='2012-07-01'):
    L1, L2 = [], []
    dates = [row[0].date() for row in rawData]
    fDate = map(int, flowerDate.split('-'))
    fDate = date(fDate[0], fDate[1], fDate[2])

    dailyLight = {date_: [] for date_ in set(dates)}
    for row in rawData:
        if row[1] > 0.0:
            dailyLight[row[0].date()].append(row[1])

    L1, L2 = [], []
    for day in dailyLight:
        if day < fDate:
            L1.append(sum(dailyLight[day]) * len(dailyLight[day]))
        else:
            L2.append(sum(dailyLight[day]) * len(dailyLight[day]))

    return sum(L1) / len(L1), sum(L2) / len(L2)


def calculateSoilWater(precipitation, evaporation,
                       soilVolume, availMoistCap, irrigation=dict()):

    soilWater = []
    dates = sorted(evaporation)
    #~ initSoilWater = 0 # unused variable

    soilWater.append(0)  # initial
    # Initial 14 days (0-13) ... sum up water gain up to soil capacity
    for date_ in dates[:14]:

        waterGain = precipitation.get(date_, [0.0])[0] \
            + irrigation.get(date_, [0.0])[0]
        soilWater.append(min(soilVolume, waterGain + soilWater[-1]))

    # From day 14 on calculate net water = soilWater from day before +
    # evaporation loss + water gain
    for date_ in dates[14:]:
        evaporationLoss = evaporation.get(date_, 0.0)
        waterGain = precipitation.get(date_, [0.0])[0] \
            + irrigation.get(date_, [0.0])[0]
        netWater = soilWater[-1] + evaporationLoss + waterGain
        soilWater.append(max(min(netWater, soilVolume), 0))

    return dict(zip(dates, soilWater[1:]))


def calculateTempStressDays(rawData, tub=30.0, tlb=8.0,
                            flowerDate='2012-07-01'):
    stressScore = lambda x: len(x) * sum(x)/len(x)

    #~ hotDays, coldDays = [], [] # unused variables
    dates = [row[0].date() for row in rawData]
    fDate = map(int, flowerDate.split('-'))
    print fDate
    fDate = date(fDate[0], fDate[1], fDate[2])
    dailyMinMaxTemp = {date_: [1000.0, -1000.0] for date_ in set(dates)}
    for row in rawData:
        date_, temp = row[0].date(), row[1]
        dailyMinMaxTemp[date_] = [min(temp, dailyMinMaxTemp[date_][0]),
                                  max(temp, dailyMinMaxTemp[date_][1])]
    C1, C2, H1, H2 = [], [], [], []
    for day in dailyMinMaxTemp:
        tMin, tMax = dailyMinMaxTemp[day]
        coldStress, heatStress = tMin < tlb, tMax > tub

        if day < fDate:
            if coldStress:
                C1.append(abs(tlb - tMin))
            if heatStress:
                H1.append(abs(tMax - tub))
        else:
            if coldStress:
                C2.append(abs(tlb - tMin))
            if heatStress:
                H2.append(abs(tMax - tub))

    return tuple(map(stressScore, [C1, C2, H1, H2]))


def calculateDroughtStressDays(rawData,
                               soilVolume, availMoistCap,
                               precipitation, irrigation,
                               stressThreshold=10.0,
                               flowerDate='2012-07-01'):
    evaporation = calculateEvaporation(rawData)

    soilWater = calculateSoilWater(precipitation, evaporation,
                                   soilVolume, availMoistCap,
                                   irrigation=irrigation)
    fDate = map(int, flowerDate.split('-'))
    fDate = date(fDate[0], fDate[1], fDate[2])
    W1, W2 = 0, 0
    for day in soilWater:
        if soilWater[day] < stressThreshold:
            if day < fDate:
                W1 += 1
            else:
                W2 += 1

    return W1, W2


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


def main(cultureID, floweringDate, soilVolume, availMoistCap):
    """
    Parameters
    ----------
    cultureID : int
        ID of the culture, e.g. 56878
    floweringDate : string
        ??? date string in YYYY-MM-DD format, e.g. '2012-07-01'
    soilVolume : int
        soil volume in ???, e.g. 42
    availMoistCap : float
        ???, e.g. 0.14
    """
    #~ cultureID = 56878 # don't overwrite input params
    #~ floweringDate = '2012-07-01' # don't overwrite input params

    # Parameters for Area 5544 (Atting), ooo spooky :O
    #~ soilVolume, availMoistCap = 42, 0.14 # don't overwrite input params

    C.execute(PREC_QUERY % {'CULTURE_ID': cultureID})
    precipitation = dict(map(lambda x: (x[0], x[1:]),
                             [row for row in C.fetchall()]))
    C.execute(IRRI_QUERY % {'CULTURE_ID': cultureID})
    irrigation = dict(map(lambda x: (x[0].date(), x[1:]),
                          [row for row in C.fetchall()]))

    C.execute(FAST_CLIMATE_QUERY % {'CULTURE_ID': cultureID})
    climateData = [row for row in C.fetchall()]

    tempStressDays = calculateTempStressDays(climateData,
                                             flowerDate=floweringDate)
    droughtStressDays = calculateDroughtStressDays(climateData,
                                                   soilVolume, availMoistCap,
                                                   precipitation, irrigation,
                                                   stressThreshold=10.0,
                                                   flowerDate=floweringDate)

    C.execute(DAYLIGHT_QUERY % {'CULTURE_ID': cultureID})
    lightData = [row for row in C.fetchall()]

    lightIntensity = calculateLightIntensity(lightData,
                                             flowerDate=floweringDate)

    print tempStressDays + droughtStressDays + lightIntensity
    pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('culture_id', type=int)
    parser.add_argument('flowering_date')
    parser.add_argument('soil_volume', type=int)
    parser.add_argument('available_moist_cap', type=float)
    args = parser.parse_args(sys.argv[1:])

    main(args.culture_id, args.flowering_date, args.soil_volume,
         args.available_moist_cap)
