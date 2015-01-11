#!/usr/bin/env python

import sys
from itertools import starmap
import datetime
from collections import defaultdict
import argparse

from climax.vpd_heatsum import calc_VPD
from climax.queries import (TRIAL_DATES_QUERY, PREC_QUERY, IRRI_QUERY,
                            FAST_CLIMATE_QUERY, DAYLIGHT_QUERY)
from climax import login

CONNECTED_TO_DB = False

# treatment IDs
CONTROL = (169, 171)
STRESS = 170


def get_trial_daterange(culture_id, db_cursor):
    """
    given a culture ID, returns a list of dates
    beginning with the first date of the
    trial and including the last date of the trial.

    Parameters
    ----------
    culture_id : int
        the culture ID of a trial
    db_cursor : MySQLdb.cursors.Cursor
        a cursor to the (running) database

    Returns
    -------
    trial_dates : list of datetime.date
        a list of dates beginning with the first date of the
        trial and including the last date of the trial
    """
    db_cursor.execute(TRIAL_DATES_QUERY % {'CULTURE_ID': culture_id})
    start_date, end_date = db_cursor.fetchone()
    return list(generate_daterange(start_date, end_date, include_end_date=True))


def generate_daterange(start, end, include_end_date=True):
    """
    Parameters
    ----------
    start : datetime.date
        start date
    end : datetime.date
        end date

    Yields
    ------
    dates : generator of datetime.date
     Generates all the dates from start to end. The start date is always included.
     If include_end_date is True, this will include the end date (default).
    """
    current = start
    break_condition = 'current <= end' if include_end_date else 'current < end'
    while eval(break_condition):
        yield current
        current += datetime.timedelta(days=1)


def are_consecutive(dates):
    """
    returns True, iff dates are consecutive.

    Parameters
    ----------
    dates : list of datetime.date
        a list of dates
    """
    date_ints = set([d.toordinal() for d in dates])
    if max(date_ints) - min(date_ints) == len(date_ints) - 1:
        return True
    else:
        return False


def treatment_type(treatment_id):
    """
    converts a control/stress treatment ID to the string 'control' or
    'stress' respectively
    """
    if treatment_id in CONTROL:
        return 'control'
    elif treatment_id == STRESS:
        return 'stress'
    else:
        raise ValueError('Unexpected treatment ID: {}'.format(treatment_id))


def datestring2object(datestring):
    """
    takes a YYYY-MM-DD formatted date string and converts it into a
    datetime.date instance.
    """
    return datetime.date(*map(int, datestring.split('-')))


def get_light_intensity(light_data, flowerDate='2012-07-01'):
    """
    ???

    Parameters
    ----------
    light_data : list of (datetime.datetime, float) tuples
        hourly data of the amount of solar radiation
    flowerDate : str
        date string in YYYY-MM-DD format

    Returns
    -------
    lightIntensity : 2-tuple of float
        light intensity (before flowering, after flowering),
        e.g. (59630.84567157448, 49066.49380313513)
    """
    dates = [row[0].date() for row in light_data]
    flowering_date = datestring2object(flowerDate)

    dailyLight = {date_: [] for date_ in set(dates)}
    for row in light_data:
        if row[1] > 0.0:
            dailyLight[row[0].date()].append(row[1])

    L1, L2 = [], []
    for day in dailyLight:
        if day < flowering_date:
            L1.append(sum(dailyLight[day]) * len(dailyLight[day]))
        else: # day >= flowering_date
            L2.append(sum(dailyLight[day]) * len(dailyLight[day]))

    return sum(L1) / len(L1), sum(L2) / len(L2)


def yesterdays_soil_value(soil_water, day, treatment):
    """
    given a day, returns the soil water value of the previous day for
    a given treatment.

    Parameters
    ----------
    soil_water : defaultdict of defaultdict(float)
        maps from a datetime.date to a dict two one or two treatments
        ('control' and 'stress'). a treatment maps to the soil water
        content (on the given day and with the given treatment).
    day : datetime.date
        a day during the field trial
    treatment : str
        'control' or 'stress'

    Returns
    -------
    soil_value : float
        soil water value of the previous day under the given treatment,
        defaults to 0.0
    """
    yesterday = datetime.date.fromordinal(day.toordinal()-1)
    if yesterday in soil_water:
        return soil_water[yesterday].get(treatment, 0.0)
    else:
        return 0.0


def get_soil_water(trial_dates, precipitation, evaporation, soilVolume,
                   availMoistCap, irrigation=dict()):
    """
    calculates the soil water values for all days of a trial and both 'control'
    and 'stress' treatment.

    Parameters
    ----------
    trial_dates : list of datetime.date
        a list of dates beginning with the first date of the
        trial and including the last date of the trial
    precipitation : dict, key = datatime.date, value = float
        amount of precipitation on a given day
    evaporation : dict, key = datatime.date, value = float
        amount of evaporation on a given day
    soilVolume : float
        soil volume
    availMoistCap : float
        availabe moisture capacity
    irrigation : dict, key = datetime.date, value = list of (float, long) tuples
        maps from a date to a list of (irrigation amount, treatment_id) tuples.
        The treatment ID is either 169 (control group) or 170 (stress).
        Default: empty dict (irrigation data is not available for all
        days / field trials)

    Returns
    -------
    soil_water : defaultdict of defaultdict(float)
        maps from a datetime.date to a dict two one or two treatments
        ('control' and 'stress'). a treatment maps to the soil water content
        (on the given day and with the given treatment).
    """
    treatments = ('control', 'stress')
    soil_water = defaultdict(lambda : defaultdict(float))

    initial_days = set(trial_dates[:14])
    for day in trial_dates:
        # Initial 14 days (0-13) ... sum up water gain up to soil capacity
        if day in initial_days:
            if day in irrigation:
                for irri_amount, treatment_id in irrigation[day]:
                    treatment = treatment_type(treatment_id)
                    waterGain = precipitation.get(day, 0.0) + irri_amount
                    yesterdays_soil_water = yesterdays_soil_value(soil_water, day, treatment)
                    current_soil_water = min(soilVolume, waterGain + yesterdays_soil_water)
                    soil_water[day][treatment] = current_soil_water
            else:  # no irrigation
                waterGain = precipitation.get(day, 0.0)
                for treatment in treatments:
                    yesterdays_soil_water = yesterdays_soil_value(soil_water, day, treatment)
                    current_soil_water = min(soilVolume, waterGain + yesterdays_soil_water)
                    soil_water[day][treatment] = current_soil_water

        # From day 14 on calculate net water = soil_water from day before minus
        # evaporation loss + water gain
        else:
            if day in irrigation:
                for irri_amount, treatment_id in irrigation[day]:
                    treatment = treatment_type(treatment_id)
                    evaporationLoss = evaporation.get(day, 0.0)
                    waterGain = precipitation.get(day, 0.0) + irri_amount
                    yesterdays_soil_water = yesterdays_soil_value(soil_water, day, treatment)
                    netWater = yesterdays_soil_water - evaporationLoss + waterGain
                    current_soil_water = max(min(netWater, soilVolume), 0)
                    soil_water[day][treatment] = current_soil_water
            else:  # no irrigation
                evaporationLoss = evaporation.get(day, 0.0)
                waterGain = precipitation.get(day, 0.0)
                for treatment in treatments:
                    yesterdays_soil_water = yesterdays_soil_value(soil_water, day, treatment)
                    netWater = yesterdays_soil_water - evaporationLoss + waterGain
                    current_soil_water = max(min(netWater, soilVolume), 0)
                    soil_water[day][treatment] = current_soil_water
    return soil_water


def get_shelter_soil_water(trial_dates, precipitation, evaporation, soilVolume,
                           availMoistCap, irrigation=dict()):
    """
    deadline-orientied, hotfix workaround function for a single trial location
    with a non-movable shelter. This function should be merged with
    get_soil_water() as soon as possible.

    calculates the soil water values for all days of a trial and both 'control'
    and 'stress' treatment.

    Parameters
    ----------
    trial_dates : list of datetime.date
        a list of dates beginning with the first date of the
        trial and including the last date of the trial
    precipitation : dict, key = datatime.date, value = float
        amount of precipitation on a given day
    evaporation : dict, key = datatime.date, value = float
        amount of evaporation on a given day
    soilVolume : float
        soil volume
    availMoistCap : float
        availabe moisture capacity
    irrigation : dict, key = datetime.date, value = list of (float, long) tuples
        maps from a date to a list of (irrigation amount, treatment_id) tuples.
        The treatment ID is either 169 (control group) or 170 (stress).
        Default: empty dict (irrigation data is not available for all
        days / field trials)

    Returns
    -------
    soil_water : defaultdict of defaultdict(float)
        maps from a datetime.date to a dict two one or two treatments
        ('control' and 'stress'). a treatment maps to the soil water content
        (on the given day and with the given treatment).
    """
    treatments = ('control', 'stress')
    soil_water = defaultdict(lambda : defaultdict(float))

    initial_days = set(trial_dates[:14])
    for day in trial_dates:
        # Initial 14 days (0-13) ... sum up water gain up to soil capacity
        if day in initial_days:
            if day in irrigation:
                for irri_amount, treatment_id in irrigation[day]:
                    treatment = treatment_type(treatment_id)
                    if treatment == 'control':
                        waterGain = precipitation.get(day, 0.0) + irri_amount
                    else: # 'stress'
                        waterGain = irri_amount
                    yesterdays_soil_water = yesterdays_soil_value(soil_water, day, treatment)
                    current_soil_water = min(soilVolume, waterGain + yesterdays_soil_water)
                    soil_water[day][treatment] = current_soil_water
            else:  # no irrigation
                for treatment in treatments:
                    if treatment == 'control':
                        waterGain = precipitation.get(day, 0.0)
                    else: # 'stress'
                        waterGain = 0.0
                    yesterdays_soil_water = yesterdays_soil_value(soil_water, day, treatment)
                    current_soil_water = min(soilVolume, waterGain + yesterdays_soil_water)
                    soil_water[day][treatment] = current_soil_water

        # From day 14 on calculate net water = soil_water from day before minus
        # evaporation loss + water gain
        else:
            first_day_after_initial_days = trial_dates[14]
            if day in irrigation:
                for irri_amount, treatment_id in irrigation[day]:
                    treatment = treatment_type(treatment_id)
                    evaporationLoss = evaporation.get(day, 0.0)
                    waterGain = precipitation.get(day, 0.0) + irri_amount
                    if day == first_day_after_initial_days:
                        yesterdays_soil_water = yesterdays_soil_value(soil_water, day, 'control')
                    else:
                        yesterdays_soil_water = yesterdays_soil_value(soil_water, day, treatment)
                    netWater = yesterdays_soil_water - evaporationLoss + waterGain
                    current_soil_water = max(min(netWater, soilVolume), 0)
                    soil_water[day][treatment] = current_soil_water
            else:  # no irrigation
                evaporationLoss = evaporation.get(day, 0.0)
                waterGain = precipitation.get(day, 0.0)
                for treatment in treatments:
                    if day == first_day_after_initial_days:
                        yesterdays_soil_water = yesterdays_soil_value(soil_water, day, 'control')
                    else:
                        yesterdays_soil_water = yesterdays_soil_value(soil_water, day, treatment)
                    netWater = yesterdays_soil_water - evaporationLoss + waterGain
                    current_soil_water = max(min(netWater, soilVolume), 0)
                    soil_water[day][treatment] = current_soil_water
    return soil_water


def get_temp_stress_days(climate_data, tub=30.0, tlb=8.0,
                            flowerDate='2012-07-01'):
    """
    calculates the sum of temperature differences for four different time
    spans: cold stress days before flowering (BF), cold stress days after
    flowering (AF), heat stress days BF, heat stress days AF.

    Parameters
    ----------
    climate_data : (datetime.datetime, float or None, float or None, float or None)
        a tuple of (datetime YYYY-MM-DD hh:mm:ss, hourly temperature in degree
        celsius (float), hourly windspeed in m/sec (float),
        hourly relative humidity in % (float)).
        WARNING: some or all hourly values might be missing (None), i.e.
        climate_data could be a (datetime, None, None, None) tuple
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
    dates = [row[0].date() for row in climate_data]
    flowering_date = datestring2object(flowerDate)

    # initialize daily min/max temperature with values with unrealistically
    # high/low values
    dailyMinMaxTemp = {date_: [1000.0, -1000.0] for date_ in set(dates)}
    # iterate over all hourly values to find the real min/max temperature
    # for each day
    for row in climate_data:
        date_, temp = row[0].date(), row[1]
        if temp: # if there's no temperature value, we don't need to update
                 # the default values
            dailyMinMaxTemp[date_] = [min(temp, dailyMinMaxTemp[date_][0]),
                                      max(temp, dailyMinMaxTemp[date_][1])]

    cold_before, cold_after, heat_before, heat_after = [], [], [], []
    for day in dailyMinMaxTemp:
        tMin, tMax = dailyMinMaxTemp[day]
        coldStress, heatStress = tMin < tlb, tMax > tub

        if day < flowering_date:
            if coldStress:
                cold_before.append(abs(tlb - tMin))
            if heatStress:
                heat_before.append(abs(tMax - tub))
        else:  # day >= flowering_date
            if coldStress:
                cold_after.append(abs(tlb - tMin))
            if heatStress:
                heat_after.append(abs(tMax - tub))
    return tuple(sum(abs_temp_differences)
                 for abs_temp_differences in (cold_before, cold_after,
                                              heat_before, heat_after))


def get_drought_stress_days(culture_id, trial_dates, climate_data, soilVolume,
                            availMoistCap, precipitation, irrigation,
                            stress_threshold=10.0, flowerDate='2012-07-01'):
    """
    calculates the number of drought stress days before and after the flowering
    date.

    Parameters
    ----------
    culture_id : int
        culture ID of the trial
    trial_dates : list of datetime.date
        a list of dates beginning with the first date of the
        trial and including the last date of the trial
    climate_data : (datetime.datetime, float or None, float or None, float or None)
        a tuple of (datetime YYYY-MM-DD hh:mm:ss, hourly temperature in degree
        celsius (float), hourly windspeed in m/sec (float),
        hourly relative humidity in % (float)).
        WARNING: some or all hourly values might be missing (None), i.e.
        climate_data could be a (datetime, None, None, None) tuple
    soilVolume : float
        soil volume
    availMoistCap : float
        availabe moisture capacity
    precipitation : dict, key = datatime.date, value = float
        precipitation on a given day
    irrigation : dict, key = datetime.date, value = list of (float, long) tuples
        maps from a date to a list of (irrigation amount, treatment_id) tuples.
        The treatment ID is either 169 (control group) or 170 (stress).
    stress_threshold : float
        a day is considered a stress day if its soil water level is equal to or
        higher than this threshold
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
    def stress_days(soil_values, flowering_date, stress_threshold):
        """
        calclulates the number of soil water stress days (before and after
        the flowering date).

        Parameters
        ----------
        soil_values : dict; key = datetime.date, value = float
            maps from a date to its soil water value
        flowering_date : datetime.date
            flowering date of the trial
        stress_threshold : float
            a day is considered a stress day if its soil water level is equal
            to or higher than this threshold

        Returns
        -------
        stress_days : (int, int) tuple
            a tuple containing the number of (stress days before flowering,
            stress days after flowering)
        """
        stress_days_before, stress_days_after = 0, 0
        for day in soil_values:
            if soil_values[day] < stress_threshold:
                if day < flowering_date:
                    stress_days_before += 1
                else:  # day >= flowering_date
                    stress_days_after += 1
        return stress_days_before, stress_days_after

    evaporation = get_evaporation(climate_data)
    assert evaporation, "get_evaporation() returned no results"
    flowering_date = datestring2object(flowerDate)

    # WARNING: WORKAROUND for exceptional conditions (i.e. a non-movable
    # shelter) at one specific trial location
    if culture_id in (56875, 62327):
        soil_water = get_shelter_soil_water(trial_dates, precipitation,
                                            evaporation, soilVolume,
                                            availMoistCap, irrigation)
    else:
        soil_water = get_soil_water(trial_dates, precipitation, evaporation,
                                    soilVolume, availMoistCap, irrigation)

    # WARNING: WORKAROUND for clusterfuck in database management, cf. issue #6
    # The cultures 47109, 56879 have irrigation, but they don't distinguish
    # control/stress.
    if irrigation and culture_id not in (47109, 56879):
        control = {date: soil_water[date]['control'] for date in soil_water}
        stress = {date: soil_water[date]['stress'] for date in soil_water}
        return stress_days(control, flowering_date, stress_threshold), \
            stress_days(stress, flowering_date, stress_threshold)

    else:
        soil_values = {date: soil_water[date]['control'] for date in soil_water}
        return stress_days(soil_values, flowering_date, stress_threshold)


def get_evaporation(climate_data):
    """
    tries to calculate the Penman evaporation for all dates in the given
    climate data. returns a dictionary mapping from a date to its evaporation.
    dates won't be included, if evaporation couldn't be calculated for them.

    Parameters
    ----------
    climate_data : list of (datetime.datetime, float, float, float) tuples
        a tuple of (datetime YYYY-MM-DD hh:mm:ss, hourly temperature in degree
        celsius (float), hourly windspeed in m/sec (float),
        hourly relative humidity in % (float)).
        WARNING: all hourly values might be missing (None)!

    Returns
    -------
    daily_evaporation : dict, key=datetime.date, value=float
        a dictionary mapping from a date to the day's evaporation in mm/day
        WARNING: this dictionary contains only those dates, for which
        evaporation data could be calculated!
    """
    def penman_evaporation(vpd, windspeed):
        """
        Calculates evaporation in mm/day from
        vapour pressure deficit and windspeed.
        Formula from Principles of Environmental Physics (Penman 1948)

        ATT: Windspeed is coming in as m/s, needs to be mph

        Parameters
        ----------
        vpd : float
            Vapour Pressure Deficit
        windspeed : float
            wind in m/s

        Returns
        -------
        evaporation : float
            evaporation occurring in a day
        """
        ms_to_mph = 2.23693629205
        return 0.376 * vpd * (windspeed * ms_to_mph) ** 0.76

    # data format: [datetime.datetime, temperature, windspeed, relHumidity]
    dates = [row[0].date() for row in climate_data]

    daily_vpd = defaultdict(list) # VPD: Vapour Pressure Deficit
    daily_windspeed = defaultdict(list)
    for date_time, temperature, windspeed, humidity in climate_data:
        day = date_time.date()
        if temperature and humidity:
            # rel. humidity is coming in as percentage, needs to be fraction
            hourly_vpd = calc_VPD(temperature, humidity/100.0)
            daily_vpd[day].append(hourly_vpd)
        if windspeed:
            daily_windspeed[day].append(windspeed)

    def mean(numbers):
        return sum(numbers) / float(len(numbers))

    # return daily penman_evaporation for daily means of vpd and windspeed
    daily_evaporation = {}
    # a day may occur several times in climate_date, but we need to calculate
    # evaporation only once
    for day in set(dates):
        # we can only calculate evaporation if VPD and windspeed are available
        if day in daily_vpd and day in daily_windspeed:
            daily_evaporation[day] = \
                penman_evaporation(mean(daily_vpd[day]),
                                   mean(daily_windspeed[day]))
    return daily_evaporation


def get_climate_data(culture_id=56878, floweringDate='2012-07-01',
                     soilVolume=42, availMoistCap=0.14):
    """
    extract climate data (temperature stress days, drought stress days and
    light intensity) from the database.

    Parameters
    ----------
    culture_id : int
        ID of the culture, e.g. 56878
    floweringDate : string
        date string in YYYY-MM-DD format, e.g. '2012-07-01'
    soilVolume : int or float
        soil volume in ???, e.g. 42
    availMoistCap : float
        available moisture capacity, e.g. 0.14

    Returns
    -------
    has_irrigation : bool
        True, iff irrigation data is available for this trial
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
    global CONNECTED_TO_DB
    if not CONNECTED_TO_DB:
        database = login.get_db()
        global CURSOR
        CURSOR = database.cursor()
        CONNECTED_TO_DB = True

    CURSOR.execute(PREC_QUERY % {'CULTURE_ID': culture_id})
    precipitation = {date: precip for (date, precip) in CURSOR.fetchall()}

    CURSOR.execute(IRRI_QUERY % {'CULTURE_ID': culture_id})
    irrigation = defaultdict(list)
    # for some days, there are two rows (stress vs. control)
    for date, irri_amount, treatment_id in CURSOR.fetchall():
        irrigation[date].append( (irri_amount, treatment_id) )

    CURSOR.execute(FAST_CLIMATE_QUERY % {'CULTURE_ID': culture_id})
    climateData = [row for row in CURSOR.fetchall()]

    trial_dates = get_trial_daterange(culture_id, CURSOR)

    tempStressDays = \
        get_temp_stress_days(climateData, flowerDate=floweringDate)
    droughtStressDays = \
        get_drought_stress_days(culture_id, trial_dates, climateData, soilVolume, availMoistCap,
                            precipitation, irrigation, stress_threshold=10.0,
                            flowerDate=floweringDate)

    CURSOR.execute(DAYLIGHT_QUERY % {'CULTURE_ID': culture_id})
    lightData = [row for row in CURSOR.fetchall()]
    lightIntensity = get_light_intensity(lightData, flowerDate=floweringDate)

    has_irrigation = True if irrigation else False
    return has_irrigation, tempStressDays, droughtStressDays, lightIntensity


def main(args=None):
    """calls get_climate_data with arguments from the command line."""
    parser = argparse.ArgumentParser()
    parser.add_argument('culture_id', type=int,
                        help='ID of the culture, e.g. 56878')
    parser.add_argument('flowering_date',
                        help='date string in YYYY-MM-DD format, e.g. 2012-07-01')
    parser.add_argument('soil_volume', type=float,
                        help='soil volume, e.g. 42 or 27.5')
    parser.add_argument('available_moist_cap', type=float,
                        help='moisture capacity, e.g. 0.14')
    if args:
        args = parser.parse_args(args)
    else:
        args = parser.parse_args(sys.argv[1:])

    has_irrigation, tempStressDays, droughtStressDays, lightIntensity = \
        get_climate_data(args.culture_id, args.flowering_date,
                         args.soil_volume, args.available_moist_cap)

    print 'has irrigation:', has_irrigation
    print 'temperature stress days:', tempStressDays
    if has_irrigation:
        print 'drought stress days:'
        control_drought_days, stress_drought_days = droughtStressDays
        print '\tcontrol:', control_drought_days
        print '\tstress:', stress_drought_days
    else:
        print 'drought stress days:', droughtStressDays
    print 'light intensity:', lightIntensity


if __name__ == '__main__':
    main(sys.argv[1:])
