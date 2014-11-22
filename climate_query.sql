select C.id, wind.date1, wind.val1, temp.date2, temp.val2, hum.date3, hum.val3 from cultures C
inner join 
(select C.id as C1, FFHM.datum as date1, FFHM.amount as val1
from dwd_hourlyMeanWindspeed_FFHM FFHM
left join usesWeatherStation uWS on uWS.station_id = FFHM.station_id and uWS.stationData = 'FFHM'
left join cultures C on C.location_id = uWS.location_id
where C.id = 44443
and (FFHM.datum >= C.planted + interval 14 day) 
and FFHM.datum <= C.terminated
ORDER BY FFHM.datum) wind
on C.id = wind.C1
left join
(select C.id as C2, TAHV.datum as date2, TAHV.amount as val2
from dwd_hourlyAirTemperature_TAHV TAHV
left join usesWeatherStation uWS on uWS.station_id = TAHV.station_id and uWS.stationData = 'TAHV'
left join cultures C on C.location_id = uWS.location_id
where C.id = 44443
and (TAHV.datum >= C.planted + interval 14 day) 
and TAHV.datum <= C.terminated
ORDER BY TAHV.datum) temp
on wind.date1 = temp.date2
left join
(select C.id as C3, UUHV.datum as date3, UUHV.amount as val3
from dwd_hourlyRelHumidity_UUHV UUHV
left join usesWeatherStation uWS on uWS.station_id = UUHV.station_id and uWS.stationData = 'UUHV'
left join cultures C on C.location_id = uWS.location_id
where C.id = 44443
and (UUHV.datum >= C.planted + interval 14 day) 
and UUHV.datum <= C.terminated
ORDER BY UUHV.datum) hum
on temp.date2 = hum.date3;



