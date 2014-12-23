#!/usr/bin/env python

TRIAL_DATES_QUERY = """
select
C.planted + interval 14 day,
C.terminated
from cultures C
where C.id = %(CULTURE_ID)i;
""".strip().replace('\n', ' ')
# returns one row with two columns: trial start date (YYYY-MM-DD),
# trial end date (YYYY-MM-DD)


PREC_QUERY = """
SELECT
DATE(P.datum),
P.amount
FROM precipitation P
JOIN cultures C ON P.location_id = C.location_id
WHERE C.id = %(CULTURE_ID)i
ORDER BY P.datum;
""".strip().replace('\n', ' ')
# results in two columns: date (YYYY-MM-DD), amount (float)
 

IRRI_QUERY = """
SELECT
DATE(I.datum),
I.amount,
I.treatment_id
FROM irrigation I
WHERE I.culture_id = %(CULTURE_ID)i
ORDER BY I.datum;
""".strip().replace('\n', ' ')
# results in three columns: date (YYYY-MM-DD), amount (float), treatment_id (169 = control, 170 = stress)



FAST_CLIMATE_QUERY = """
SELECT
wind.date1, temperature, windspeed, relHumidity
FROM cultures C
inner join
(select C.id as C1, FFHM.datum as date1, FFHM.amount as windspeed
from dwd_hourlyMeanWindspeed_FFHM FFHM
left join usesWeatherStation uWS on uWS.station_id = FFHM.station_id and uWS.stationData = 'FFHM'
left join cultures C on C.location_id = uWS.location_id
where C.id = %(CULTURE_ID)i
and (FFHM.datum >= C.planted + interval 14 day)
and FFHM.datum < C.terminated
and FFHM.invalid is NULL
ORDER BY FFHM.datum) wind
on C.id = wind.C1
left join
(select C.id as C2, TAHV.datum as date2, TAHV.amount as temperature
from dwd_hourlyAirTemperature_TAHV TAHV
left join usesWeatherStation uWS on uWS.station_id = TAHV.station_id and uWS.stationData = 'TAHV'
left join cultures C on C.location_id = uWS.location_id
where C.id = %(CULTURE_ID)i
and (TAHV.datum >= C.planted + interval 14 day)
and TAHV.datum < C.terminated
and TAHV.invalid is NULL
ORDER BY TAHV.datum) temp
on wind.date1 = temp.date2
left join
(select C.id as C3, UUHV.datum as date3, UUHV.amount as relHumidity
from dwd_hourlyRelHumidity_UUHV UUHV
left join usesWeatherStation uWS on uWS.station_id = UUHV.station_id and uWS.stationData = 'UUHV'
left join cultures C on C.location_id = uWS.location_id
where C.id = %(CULTURE_ID)i
and (UUHV.datum >= C.planted + interval 14 day)
and UUHV.datum < C.terminated
and UUHV.invalid is NULL
ORDER BY UUHV.datum) hum
on temp.date2 = hum.date3;
""".strip().replace('\n', ' ')
# results in four columns: date-time (YYYY-MM-DD hh:mm:ss), hourly temperature in degree celsius (float), 
# hourly windspeed in m/sec (float), hourly relative humidity in % (integer)


DAYLIGHT_QUERY = """
SELECT
sC.datum,
sC.amount
FROM solarCalc_hourlySolarRadiation sC
JOIN cultures C ON C.location_id = sC.location_id
WHERE C.id = %(CULTURE_ID)i
AND (sC.datum >= C.planted + interval 14 day)
AND (sC.datum < C.terminated)
ORDER BY sC.datum
""".strip().replace('\n', ' ')
# results in two columns: date-time (YYYY-MM-DD hh:mm:ss), hourly solar radiation (float)

