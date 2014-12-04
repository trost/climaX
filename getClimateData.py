#!/usr/bin/env python

import sys
from itertools import starmap
from datetime import date
from collections import defaultdict
import argparse

from vpd_heatsum import calc_VPD
from queries import PREC_QUERY, IRRI_QUERY, FAST_CLIMATE_QUERY, DAYLIGHT_QUERY
import login  # TODO: get the real login module from Christian, this is fake

# treatment IDs
CONTROL = 169
STRESS = 170


def datestring2object(datestring):
    """
    takes a YYYY-MM-DD formatted date string and converts it into a
    datetime.date instance.
    """
    return date(*map(int, datestring.split('-')))


def get_light_intensity(rawData, flowerDate='2012-07-01'):
    """
    Returns
    -------
    lightIntensity : 2-tuple of float
        light intensity (before flowering, after flowering),
        e.g. (59630.84567157448, 49066.49380313513)
    """
    L1, L2 = [], []
    dates = [row[0].date() for row in rawData]
    flowering_date = datestring2object(flowerDate)

    dailyLight = {date_: [] for date_ in set(dates)}
    for row in rawData:
        if row[1] > 0.0:
            dailyLight[row[0].date()].append(row[1])

    L1, L2 = [], []
    for day in dailyLight:
        if day < flowering_date:
            L1.append(sum(dailyLight[day]) * len(dailyLight[day]))
        else: # day >= flowering_date
            L2.append(sum(dailyLight[day]) * len(dailyLight[day]))

    return sum(L1) / len(L1), sum(L2) / len(L2)


def get_soil_water(precipitation, evaporation, soilVolume, availMoistCap,
               irrigation=dict()):
    """
    Parameters
    ----------
    precipitation : dict, key = datatime.date, value = float
        ???
    evaporation
    soilVolume : float
        soil volume
    availMoistCap : float
        ???
    irrigation : dict, key = datetime.date, value = list of (float, long) tuples
        maps from a date to a list of (irrigation amount, treatment_id) tuples.
        The treatment ID is either 169 (control group) or 170 (stress).
        Default: empty dict (irrigation data is not available for all
        days / field trials)

    Returns
    -------
    soil_water : dict or (dict, dict) tuple
        Iff ``irrigation`` is not empty, this returns a tuple of (control soil
        water, stress soil water) dictionaries. Both map from a date
        (datetime.date) to a soil water amount (float).
        Otherwise, this will only return one such dictionary.
    """
    # initial value needed to calculate yesterday's soil water
    soil_water, control_soil_water, stress_soil_water = [0], [0], [0]
    dates = sorted(evaporation)

    if irrigation:
        # Initial 14 days (0-13) ... sum up water gain up to soil capacity
        for date in dates[:14]:
            for irri_amount, treatment_id in irrigation[date]:
                waterGain = precipitation.get(date, 0.0) + irri_amount
                current_soil_water = min(soilVolume, waterGain + soil_water[-1])
                if treatment_id == CONTROL:
                    control_soil_water.append(current_soil_water)
                elif treatment_id == STRESS:
                    stress_soil_water.append(current_soil_water)
                else:
                    raise ValueError("Unexpected treatment ID: {}".format(treatment_id))

        # From day 14 on calculate net water = soil_water from day before +
        # evaporation loss + water gain
        for date in dates[14:]:
            for irri_amount, treatment_id in irrigation[date]:
                evaporationLoss = evaporation.get(date, 0.0)
                waterGain = precipitation.get(date, 0.0) + irri_amount
                netWater = soil_water[-1] + evaporationLoss + waterGain
                current_soil_water = max(min(netWater, soilVolume), 0)
                if treatment_id == CONTROL:
                    control_soil_water.append(current_soil_water)
                elif treatment_id == STRESS:
                    stress_soil_water.append(current_soil_water)
                else:
                    raise ValueError("Unexpected treatment ID: {}".format(treatment_id))
        return dict(zip(dates, control_soil_water[1:])), \
            dict(zip(dates, stress_soil_water[1:]))

    else:  # no irrigation
        for date in dates[:14]:
            waterGain = precipitation.get(date, 0.0)
            current_soil_water = min(soilVolume, waterGain + soil_water[-1])
            soil_water.append(current_soil_water)

        # From day 14 on calculate net water = soil_water from day before +
        # evaporation loss + water gain
        for date in dates[14:]:
            evaporationLoss = evaporation.get(date, 0.0)
            waterGain = precipitation.get(date, 0.0)
            netWater = soil_water[-1] + evaporationLoss + waterGain
            current_soil_water = max(min(netWater, soilVolume), 0)
            soil_water.append(current_soil_water)
        return dict(zip(dates, soil_water[1:]))


def get_temp_stress_days(rawData, tub=30.0, tlb=8.0,
                            flowerDate='2012-07-01'):
    """
    Parameters
    ----------
    rawData : ???
        ???
    tub : float
        temperature upper bound
    tlb : float
        temperature lower bound
    flowerDate : str
        date string in YYYY-MM-DD format

    Returns
    -------
    tempStressDays : 4-tuple of float
        sum of tempurature differences for (cold stress days before flowering,
        cold stress days after flowering, heat stress days before flowering,
        heat stress days after flowering).
        Example: (45.4, 4.3999999999999995, 2.5, 3.8999999999999986)
    """
    dates = [row[0].date() for row in rawData]
    flowering_date = datestring2object(flowerDate)

    dailyMinMaxTemp = {date_: [1000.0, -1000.0] for date_ in set(dates)}
    for row in rawData:
        date_, temp = row[0].date(), row[1]
        dailyMinMaxTemp[date_] = [min(temp, dailyMinMaxTemp[date_][0]),
                                  max(temp, dailyMinMaxTemp[date_][1])]
    C1, C2, H1, H2 = [], [], [], []
    for day in dailyMinMaxTemp:
        tMin, tMax = dailyMinMaxTemp[day]
        coldStress, heatStress = tMin < tlb, tMax > tub

        if day < flowering_date:
            if coldStress:
                C1.append(abs(tlb - tMin))
            if heatStress:
                H1.append(abs(tMax - tub))
        else:  # day >= flowering_date
            if coldStress:
                C2.append(abs(tlb - tMin))
            if heatStress:
                H2.append(abs(tMax - tub))

    return tuple(sum(dates) for dates in (C1, C2, H1, H2))


def get_drought_stress_days(rawData, soilVolume, availMoistCap, precipitation,
                        irrigation, stressThreshold=10.0,
                        flowerDate='2012-07-01'):
    """
    calculates the number of drought stress days before and after the flowering
    date.

    Parameters
    ----------
    rawData : list of (datetime.datetime, float, float, float) tuples
        ???
    soilVolume : float
        soil volume
    availMoistCap : float
        ???
    precipitation : dict, key = datatime.date, value = float
        ???
    irrigation : dict, key = datetime.date, value = list of (float, long) tuples
        maps from a date to a list of (irrigation amount, treatment_id) tuples.
        The treatment ID is either 169 (control group) or 170 (stress).
    stressThreshold : float
        ???
    flowerDate : str
        flowering date in YYYY-MM-DD format

    Returns
    -------
    droughtStressDays : (int, int) or ((int, int) (int, int))
        Iff ``irrigation`` is empty: number of drought stress days (DSDs)
        (before flowering, after flowering), e.g. (16, 0).
        Otherwise: ((control DSDs before, control DSDs after),
        (stress DSDs before, stress DSDs after)).
    """
    def stress_days(soil_water, flowering_date, stressThreshold):
        stress_days_before, stress_days_after = 0, 0
        for day in soil_water:
            if soil_water[day] < stressThreshold:
                if day < flowering_date:
                    stress_days_before += 1
                else:  # day >= flowering_date
                    stress_days_after += 1
        return stress_days_before, stress_days_after

    evaporation = get_evaporation(rawData)
    flowering_date = datestring2object(flowerDate)

    if irrigation:
        control, stress = get_soil_water(precipitation, evaporation,
                                         soilVolume, availMoistCap, irrigation)
        return stress_days(control, flowering_date, stressThreshold), \
            stress_days(stress, flowering_date, stressThreshold)

    else:
        soil_water = get_soil_water(precipitation, evaporation, soilVolume,
                                    availMoistCap, irrigation)
        return stress_days(soil_water, flowering_date, stressThreshold)



def get_evaporation(rawData):
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


def main(cursor, cultureID=56878, floweringDate='2012-07-01', soilVolume=42,
         availMoistCap=0.14):
    """
    Parameters
    ----------
    cursor : MySQLdb.cursors.Cursor
        cursor to the MySQL database
    cultureID : int
        ID of the culture, e.g. 56878
    floweringDate : string
        ??? date string in YYYY-MM-DD format, e.g. '2012-07-01'
    soilVolume : int or float
        soil volume in ???, e.g. 42
    availMoistCap : float
        ???, e.g. 0.14

    Returns
    -------
    tempStressDays : 4-tuple of float
        sum of tempurature differences for (cold stress days before flowering,
        cold stress days after flowering, heat stress days before flowering,
        heat stress days after flowering).
        Example: (45.4, 4.3999999999999995, 2.5, 3.8999999999999986)
    droughtStressDays : 2-tuple of int
        number of drought stress days (before flowering, after flowering),
        e.g. (16, 0)
    lightIntensity : 2-tuple of float
        light intensity (before flowering, after flowering),
        e.g. (59630.84567157448, 49066.49380313513)
    """
    cursor.execute(PREC_QUERY % {'CULTURE_ID': cultureID})
    precipitation = {date: precip for (date, precip) in cursor.fetchall()}

    cursor.execute(IRRI_QUERY % {'CULTURE_ID': cultureID})
    irrigation = defaultdict(list)
    # for some days, there are two rows (stress vs. control)
    for date, irri_amount, treatment_id in cursor.fetchall():
        irrigation[date].append( (irri_amount, treatment_id) )

    cursor.execute(FAST_CLIMATE_QUERY % {'CULTURE_ID': cultureID})
    climateData = [row for row in cursor.fetchall()]

    tempStressDays = \
        get_temp_stress_days(climateData, flowerDate=floweringDate)
    droughtStressDays = \
        get_drought_stress_days(climateData, soilVolume, availMoistCap,
                            precipitation, irrigation, stressThreshold=10.0,
                            flowerDate=floweringDate)

    cursor.execute(DAYLIGHT_QUERY % {'CULTURE_ID': cultureID})
    lightData = [row for row in cursor.fetchall()]

    lightIntensity = get_light_intensity(lightData, flowerDate=floweringDate)
    return tempStressDays, droughtStressDays, lightIntensity


if __name__ == '__main__':
    database = login.get_db()
    cursor = database.cursor()

    parser = argparse.ArgumentParser()
    parser.add_argument('culture_id', type=int,
                        help='ID of the culture, e.g. 56878')
    parser.add_argument('flowering_date',
                        help='date string in YYYY-MM-DD format, e.g. 2012-07-01')
    parser.add_argument('soil_volume', type=float,
                        help='soil volume, e.g. 42 or 27.5')
    parser.add_argument('available_moist_cap', type=float,
                        help='moisture capacity, e.g. 0.14')
    args = parser.parse_args(sys.argv[1:])

    tempStressDays, droughtStressDays, lightIntensity = \
        main(cursor, args.culture_id, args.flowering_date, args.soil_volume,
             args.available_moist_cap)
    print tempStressDays
    print droughtStressDays
    print lightIntensity
