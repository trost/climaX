#!/usr/bin/env python
'''
Script to compute weekly midday vapour pressure deficit (VPD) values
and thermal time from DWD (German Weather Service - http://www.dwd.de)
XML data
'''
import sys
import os
import re
import math
import datetime

import numpy as np
from BeautifulSoup import BeautifulStoneSoup as BSS

__author__ = 'Christian Schudoma'
__copyright__ = 'Copyright 2013-2014, Christian Schudoma'
__license__ = 'MIT'
__version__ = '0.1a'
__maintainer__ = 'Christian Schudoma'
__email__ = 'cschu@darkjade.net'


def readClimateData_DWDXML(fn, start_date='2011-04-11', end_date='2011-09-02',
                           use_datetime=True):
    """
    Reads DWD Climate Data (tested on hourly temperatures, hourly rel.
    humidities) in the interval of
    (start_date (YYYY-MM-DD), end_date (YYYY-MM-DD)) from a DWD XML file
    containing data from a single weather station.

    WARNING: Don't try this on multi-station files or non-continuous intervals
    without modification!
    """
    start, end = (datetime.datetime.strptime(start_date, '%Y-%m-%d').date(),
                  datetime.datetime.strptime(end_date, '%Y-%m-%d').date())
    station_data = {}
    raw = open(fn).read()
    # remove spaces between tags... (BSS-requirement!)
    raw = re.sub('> [ ]+<', '><', raw.replace('\n', ''))
    soup = BSS(raw)
    soup_data = soup.data
    station = soup_data.stationname

    while True:
        if station is None:
            break
        #~ station_name = station.get('value') # unused variable
        # For debugging:
        #if station_name.strip() != 'Fassberg':
        #   station = station.nextSibling
        #   continue
        datapoint = station.v
        while True:
            if datapoint is None:
                break
            v_value = float(datapoint.text)

            date_, time_ = str(datapoint.get('date')), None
            if 'T' in date_:
                date_, time_ = [value.strip('Z') for value in date_.split('T')]
            day = datetime.datetime.strptime(date_, '%Y-%m-%d').date()
            if day >= start and day <= end:
                if use_datetime:
                    key = (date_, time_)
                else:
                    key = date_
                station_data[key] = station_data.get(key, []) + [v_value]
            datapoint = datapoint.nextSibling

        station = station.nextSibling
        pass
    return station_data


def calc_VPD(T_Celsius, relHumidity):
    """
    Different methods for calculating Vapour Pressure Deficit (VPD)
    from temperature and relative humidity values.
    Returns VPD, calculated according to Licor LI-6400 manual
    """
    #~ T = T_Celsius + 273.15 # T_Kelvin  # unused variable
    #~ PSI_IN_KPA = 6.8948 # unused variable

    # according to http://en.wikipedia.org/wiki/Vapour_Pressure_Deficit
    # A, B, C, D, E, F = -1.88e4, -13.1, -1.5e-2, 8e-7, -1.69e-11, 6.456
    # vp_sat = math.exp(A / T + B + C * T + D * T ** 2 + E * T ** 3 + F * math.log(T))
    # according to http://ohioline.osu.edu/aex-fact/0804.html
    # A, B, C, D, E, F = -1.044e4, -1.129e1, -2.702e-2, 1.289e-5, -2.478e-9, 6.456
    # vp_sat = math.exp(A / T + B + C * T + D * T ** 2 + E * T ** 3 + F * math.log(T)) * PSI_IN_KPA
    # according to
    # http://physics.stackexchange.com/questions/4343/how-can-i-calculate-vapor-pressure-deficit-from-temperature-and-relative-humidit
    # vp_sat = 6.11 * math.exp((2.5e6 / 461) * (1 / 273 - 1 / (273 + T)))
    # according to Licor LI-6400 manual pg 14-10
    # and Buck AL (1981) New equations for computing vapor pressure and enhancement factor. J Appl Meteor 20:1527-1532
    vp_sat = 0.61365 * math.exp((17.502 * T_Celsius) / (240.97 + T_Celsius))

    vp_air = vp_sat * relHumidity
    return vp_sat - vp_air  # or vp_sat * (1 - relHumidity)


def compute_weekly_midday_vpd(temperatures, relHumidity):
    """
    Computes the weekly midday (10am - 2pm) VPD.
    Returns dictionary {week-index: average midday VPD}
    """
    hourly = {timepoint: calc_VPD(temperatures[timepoint][0], relHumidity[timepoint][0])
              for timepoint in set(temperatures.keys()).intersection(set(relHumidity.keys()))}
    daily = {}
    midday = (datetime.datetime.strptime('10:00:00', '%H:%M:%S'),
              datetime.datetime.strptime('14:00:00', '%H:%M:%S'))
    for tp in hourly:
        try:
            hour = datetime.datetime.strptime(tp[1], '%H:%M:%S')
        except:
            hour = datetime.datetime.strptime(tp[1], '%H:%M')
        if midday[0] <= hour <= midday[1]:
            daily[tp[0]] = daily.get(tp[0], []) + [hourly[tp]]

    weekly = {}
    for k in sorted(daily):
        week = tuple(map(int, datetime.datetime.strftime(datetime.datetime.strptime(k, '%Y-%m-%d'), '%Y-%W').split('-')))
        weekly[week] = weekly.get(week, []) + [np.median(daily[k])]

    return {week: sum(weekly[week])/len(weekly[week]) for week in weekly}


def calc_heat_sum(tmin, tmax, tbase=6.0):
    """
    Calculates thermal time as heatsum.
    Daily heat sum is defined as:
    heat_sum_d = max(tx - tbase, 0), with
    tx = (tmin + tmax)/2 and
    tmax = min(tmax_measured, 30.0)
    """
    tmax = min(tmax, 30.0)
    tx = (tmin + tmax) / 2.0
    return max(tx - tbase, 0.0)


def compute_heatsum_per_day(maxTemps, minTemps):
    """
    Computes daily heat sums based on min/max temperatures for a range of days
    """
    heatsum, heatsum_day = 0, {}
    for k in sorted(set(maxTemps.keys()).intersection(set(minTemps.keys()))):
        heatsum += calc_heat_sum(minTemps[k], maxTemps[k])
        heatsum_day[k] = heatsum
    return heatsum_day


def compute_heatsum_per_week(heatsum_day, day=5):
    """
    Returns weekly heatsums from a representative day of the week
    (day=5: Friday => end of weekly measuring interval for many DWD stations!)
    """
    heatsum_week = {}
    for k in heatsum_day:
        year, week, weekday = map(int, datetime.datetime.strftime(datetime.datetime.strptime(k, '%Y-%m-%d'), '%Y %W %w').split())
        if weekday == day:
            heatsum_week[(year, week)] = heatsum_day[k]
    return heatsum_week


def main(argv):

    if len(argv) != 4:
        print 'Usage python %s <temperatures> <relHumidity> <start,end> <outfile>' % os.path.basename(sys.argv[0])
        print '<temperatures>, <relHumidity>: DWD XML files'
        print '<start,end>: start and end date in the format "YYYY-MM-DD,YYYY-MM-DD" (don\'t forget the "s)'
        print '<outfile>: specify a file for writing the output WARNING: file will be overwritten!'
        sys.exit(1)

    # manage parameters and read raw data
    fn_Temperatures, fn_RelHumidities = argv[0], argv[1]
    startd, endd = argv[2].split(',')
    fout = argv[3]
    rawTemperatures = readClimateData_DWDXML(fn_Temperatures)
    rawRelHumidities = readClimateData_DWDXML(fn_RelHumidities)

    # convert %-values from DWD to fractional values
    for k in rawRelHumidities:
        rawRelHumidities[k] = map(lambda x: x/100.0, rawRelHumidities[k])
    # group temperatures per day in order to facilitating the computation of daily min/max
    groupedTemperatures = {}
    for k in rawTemperatures:
        groupedTemperatures[k[0]] = groupedTemperatures.get(k[0], []) + rawTemperatures[k]
    # compute daily min/max temperatures
    maxTemperatures, minTemperatures = {}, {}
    for k in sorted(groupedTemperatures):
        maxTemperatures[k], minTemperatures[k] = max(groupedTemperatures[k]), min(groupedTemperatures[k])

    # compute VPD and thermal time
    VPD = compute_weekly_midday_vpd(rawTemperatures, rawRelHumidities)
    HEATSUM = compute_heatsum_per_week(compute_heatsum_per_day(maxTemperatures, minTemperatures))

    # write heatsum/vpd values
    out = open(fout, 'wb')
    out.write('Week\tVPD_midday[kPa]\theatsum[Cd]\n')
    for k in sorted(set(VPD).intersection(set(HEATSUM))):
        out.write('%i-%i\t%.3f\t%.3f\n' % (k[0], k[1], HEATSUM[k], VPD[k]))
    out.close()
    pass

if __name__ == '__main__':
    main(sys.argv[1:])
