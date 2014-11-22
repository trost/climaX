#!/usr/bin/env python

"""
Python port of SolarCalc 1.0 
This port only the internal calculation routines, thus making
the tool applicable for batch data processing without GUI.

Please contact me, in case I'm violating anything with this... 
Not doing it on purpose.. I'm just tired of clicking through the GUI :/

For references, formulas etc, see
http://www.ars.usda.gov/services/software/download.htm?softwareid=62
"""

import sys
import math
import csv
import datetime

__author__ = 'Christian Schudoma'
__copyright__ = 'Copyright 2014, Christian Schudoma'
__license__ = 'MIT(?)'
__version__ = '0.1a'
__maintainer__ = 'Christian Schudoma'
__email__ = 'cschu@darkjade.net'

def solarDeclination(doy):
    temp2 = sum([278.97, 
                 0.9856 * doy, 
                 1.9165 * math.sin((356.6 + 0.9856 * doy) * math.pi / 180.0)])
    temp2 = math.sin(temp2 * math.pi / 180.0)
    return math.asin(0.39785 * temp2);

def getET(doy):
    ETcalc = (279.575 + 0.9856 * doy) * math.pi / 180.0;
    temp1 = sum([-104.7 * math.sin(ETcalc), 
                 596.2 * math.sin(ETcalc * 2), 
                 4.3 * math.sin(3 * ETcalc),
                 -12.7 * math.sin(4 * ETcalc),
                 -429.3 * math.cos(ETcalc),
                 -2.0 * math.cos(2 * ETcalc),
                 19.3 * math.cos(3 * ETcalc)])
    return temp1 / 3600.0;

def calcHalfDayLength(solarDecl, latitude):
    temp3 = sum([math.cos(90.0 * math.pi / 180.0),
                 -math.sin(latitude) * math.sin(solarDecl)])
    temp3 /= (math.cos(solarDecl) * math.cos(latitude))
    return (math.acos(temp3) * 180.0 / math.pi) / 15.0

def zenith(latitude, solarDecl, t, solarNoon):
    temp = sum([math.sin(latitude) * math.sin(solarDecl),
                math.cos(latitude) * math.cos(solarDecl)])
    temp *= math.cos(15.0 * (t - solarNoon) * math.pi / 180.0)
    return math.acos(temp)

def main(argv):

    Fd = 1.0
    Fp = 0.0
    Spo = 1360.0
    albedo = 0.15

    out = sys.stdout

    try:
        latitude, longitude, elevation, year = map(float, argv[1:4]) + [int(argv[4])]
        cliReader = csv.reader(open(argv[0]), delimiter=',', quotechar='"')
        stationID = argv[0][:4]
    except:
        sys.stderr.write('Expecting <climate file> latitude longitude elevation[m], year[YYYY]!\n')
        sys.exit(1)

    latitude *= math.pi / 180.0
    longitude *= math.pi / 180.0
    LC = longitude / (360.0 * 24.0)

    maxDays = 365
    if (year % 4 == 0) and (((year % 100) != 0) or ((year % 400) == 0)):
        maxDays = 366
    

    days = {}
    for row in cliReader:
        if len(row) == 0:
            continue
        try:
            day, tmin, tmax, prec = [int(row[0])] + map(float, row[1:4])
        except:
            continue
        days[day] = (tmin, tmax, prec)
        
    for day in xrange(1, maxDays + 1):

        ET = getET(day)
        solarNoon = 12.0 - LC - ET
        solarDecl = solarDeclination(day)
        # zenithAngle = zenith(latitude, solarDecl, time, solarNoon)
        halfDayLength = calcHalfDayLength(solarDecl, latitude)
        sunrise = solarNoon - halfDayLength
        sunset = solarNoon + halfDayLength

        tmin, tmax, prec = days.get(day, (0.0, 0.0, 0.0))
        yesterday = days.get(day - 1, (None, None, 0.0))
        rainyDayBefore = yesterday[2] > 0.0
        # default - clear sky
        tao = 0.7 
        if rainyDayBefore:
            if prec > 0.0:
                # raining yesterday and today
                tao = 0.3
            else:
                # raining only yesterday
                tao = 0.6
        elif prec > 0.0:
            # raining today
            tao = 0.4

        # at non-polar coordinates, tao value is lower 
        # with daily air temperature differences lower than 10
        if abs(latitude / math.pi * 180.0) < 60.0:
            deltaT = tmax - tmin
            if deltaT <= 10.0 and deltaT != 0.0:
                tao /= (11.0 - deltaT)
        airTemp = (tmax + tmin) / 2.0
        Pa = 101.0 * math.exp(-1.0 * elevation / 8200.)
        La =  5.67e-08 * math.pow((airTemp + 273.16), 4.0);
                
        for t in xrange(24):
            zenithAngle = zenith(latitude, solarDecl, t, solarNoon)
            temp = zenithAngle
            m = Pa / 101.3 / math.cos(temp)

            # Sp: diffuse radiation
            # Sd: diffuse sky irradiance on horizontal plane
            # Sb: beam irradiance on horizontal surface
            if t < sunrise or t > sunset:
                Sp, Sd, Sb = 0.0, 0.0, 0.0
            else:
                try:
                    pow_ = math.pow(tao, m)      
                except:
                    pow_ = 0.0
                Sp = Spo * pow_                
                Sd = 0.3 * (1.0 - pow_) * math.cos(zenithAngle) * Spo
                Sb = Sp * math.cos(zenithAngle)
            
            # total irradiance on horizontal surface,
            # 0.0 case for northern latitudes without daylight
            try:
                St = max(0.0, Sb + Sd)
            except:
                # NaN case from java?
                St = 0.0
                
            # reflected radiation
            Sr = albedo * St
            # absorbed radiation (estimated)
            Fp = math.cos(zenithAngle)
            Rabs = (1.0 - albedo) * (Fp * Sp + Fd * Sd) + 0.05 * La

            # print t
            dateObj = datetime.datetime.strptime('%03i %i %i' % (day, year, t),
                                                 '%j %Y %H')

            ## current output goes directly into SQL format
            line = map(str, ['NULL',
                             dateObj.strftime("'%Y-%m-%d %H:%M:%S'"),
                             stationID,
                             St,
                             'NULL'])
            # St, deltaT, tao])
            sql = 'INSERT INTO solarCalc_hourlySolarRadiation VALUES(%s);'
            out.write(sql % (','.join(line)) + '\n')
            
            


            pass

            
            


    pass



if __name__ == '__main__': main(sys.argv[1:])
