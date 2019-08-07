#!/usr/bin/env python3
"""
Polyglot v2 node server for WeatherFlow Weather Station data.
Copyright (c) 2018 Robert Paauwe
"""
CLOUD = False
try:
    import polyinterface
except ImportError:
    import pgc_interface as polyinterface
    CLOUD = True
import sys
import time
import datetime
import urllib3
import json
import socket
import math
import threading

LOGGER = polyinterface.LOGGER

class Controller(polyinterface.Controller):
    def __init__(self, polyglot):
        super(Controller, self).__init__(polyglot)
        self.name = 'WeatherFlow'
        self.address = 'hub'
        self.primary = self.address
        self.stopping = False
        self.stopped = True
        self.myConfig = {}
        self.rain_data = {
                'hourly': 0,
                'hour' : 0,
                'daily': 0,
                'day': 0,
                'weekly': 0,
                'week': 0,
                'monthly': 0,
                'month': 0,
                'yearly': 0,
                'year': 0,
                'yesterday': 0,
                }
        self.hb = 0
        self.hub_timestamp = 0
        self.poly.onConfig(self.process_config)
        self.poly.onStop(self.my_stop)
        self.station = ''
        self.agl = 0.0
        self.elevation = 0.0
        self.http = None 

    def process_config(self, config):
        # This isn't really what the name implies, it is getting called
        # for all non-driver database updates.  It also appears to be called
        # after the database update has occured.  Thus it is pretty much
        # useless for parameter checking.

        # can we just ignore non-parameter changes?
        if self.myConfig == config['customParams']:
            return

        # looks like a parameter changed, so which one?
        new_params = config['customParams']
        self.myConfig = config['customParams']

    def query_wf(self):
        """
        We need to call this after we get the customParams because
        we need the station number. 
        """
        if self.station == "":
            LOGGER.info('no station defined, skipping lookup.')
            return

        path_str = '/swd/rest/stations/'
        path_str += self.station
        path_str += '?api_key=6c8c96f9-e561-43dd-b173-5198d8797e0a'

        try:
            #http = urllib3.HTTPConnectionPool('swd.weatherflow.com', maxsize=1)

            # Get station meta data. We really want AIR height above ground
            c = self.http.request('GET', path_str)
            awdata = json.loads(c.data.decode('utf-8'))
            for device in awdata['stations'][0]['devices']:
                if device['device_type'] == 'AR':
                    self.agl = float(device['device_meta']['agl'])
            c.close()

            # Get station observations. Pull Elevation and user unit prefs.
            path_str = '/swd/rest/observations/station/'
            path_str += self.station
            path_str += '?api_key=6c8c96f9-e561-43dd-b173-5198d8797e0a'
            c = self.http.request('GET', path_str)

            awdata = json.loads(c.data.decode('utf-8'))

            # TODO: check user preference for units and set accordingly
            # Check distance & temp
            # if dist in miles & temp in F == US
            # if dist in miles & temp in C == UK
            # else == metric
            temp_unit = awdata['station_units']['units_temp']
            dist_unit = awdata['station_units']['units_distance']

            if temp_unit == 'f' and dist_unit == 'mi':
                LOGGER.info('WF says units are US')
                self.units = 'us'
            elif temp_unit == 'c' and dist_unit == 'mi':
                LOGGER.info('WF says units are UK')
                self.units = 'uk'
            else:
                LOGGER.info('WF says units are metric')
                self.units = 'metric'

            self.elevation = float(awdata['elevation'])

            # obs is array of dictionaries. Array index 0 is what we want
            # to get current daily and yesterday daily rainfall values

            if 'obs' in awdata:
                if 'precip_accum_local_day' in awdata['obs'][0]:
                    LOGGER.info('daily rainfall = %f' %
                        awdata['obs'][0]['precip_accum_local_day'])
                else:
                    LOGGER.info('Missing local day rainfall acummulation.')
                if 'precip_accum_local_yesterday' in awdata['obs'][0]:
                    LOGGER.info('yesterday rainfall = %f' %
                        awdata['obs'][0]['precip_accum_local_yesterday'])
                else:
                    LOGGER.info('Missing local yesterday rainfall acummulation.')
            else:
                LOGGER.info('station info query has no observation data.')

            c.close()

        except Exception as e:
            LOGGER.error('Bad: %s' % str(e))


    def start(self):
        LOGGER.info('Starting WeatherFlow Node Server')
        self.http = urllib3.HTTPConnectionPool('swd.weatherflow.com', maxsize=1)
        self.check_params()
        self.discover()

        #for node in self.nodes:
        #       LOGGER.info (self.nodes[node].name + ' is at index ' + node)
        LOGGER.info('WeatherFlow Node Server Started.')

    def shortPoll(self):
        pass

    def longPoll(self):
        # Poll WF servers for current observation data
        self.query_data()
        self.heartbeat()
        self.set_hub_timestamp()

    def query(self):
        for node in self.nodes:
            self.nodes[node].reportDrivers()
        self.set_hub_timestamp()

    def discover(self, *args, **kwargs):
        """
        Add basic weather sensor nodes
                - Temperature (temp, dewpoint, heat index, wind chill, feels)
                - Humidity
                - Pressure (abs, sealevel, trend)
                - Wind (speed, gust, direction, gust direction, etc.)
                - Precipitation (rate, hourly, daily, weekly, monthly, yearly)
                - Light (UV, solar radiation, lux)
                - Lightning (strikes, distance)
        """

        self.query_wf()

        node = TemperatureNode(self, self.address, 'temperature', 'Temperatures')
        node.SetUnits(self.units)
        self.addNode(node)

        node = HumidityNode(self, self.address, 'humidity', 'Humidity')
        node.SetUnits(self.units)
        self.addNode(node)
        node = PressureNode(self, self.address, 'pressure', 'Barometric Pressure')
        node.SetUnits(self.units)
        self.addNode(node)
        node = WindNode(self, self.address, 'wind', 'Wind')
        node.SetUnits(self.units)
        self.addNode(node)
        node = PrecipitationNode(self, self.address, 'rain', 'Precipitation')
        node.SetUnits(self.units)
        self.addNode(node)
        node = LightNode(self, self.address, 'light', 'Illumination')
        node.SetUnits(self.units)
        self.addNode(node)
        node = LightningNode(self, self.address, 'lightning', 'Lightning')
        node.SetUnits(self.units)
        self.addNode(node)

        
        if 'customData' in self.polyConfig:
            try:
                self.rain_data['hourly'] = self.polyConfig['customData']['hourly']
                self.rain_data['daily'] = self.polyConfig['customData']['daily']
                self.rain_data['weekly'] = self.polyConfig['customData']['weekly']
                self.rain_data['monthly'] = self.polyConfig['customData']['monthly']
                self.rain_data['yearly'] = self.polyConfig['customData']['yearly']
                self.rain_data['hour'] = self.polyConfig['customData']['hour']
                self.rain_data['day'] = self.polyConfig['customData']['day']
                self.rain_data['month'] = self.polyConfig['customData']['month']
                self.rain_data['year'] = self.polyConfig['customData']['year']
                self.rain_data['yesterday'] = self.polyConfig['customData']['yesterday']
            except: 
                self.rain_data['hourly'] = 0
                self.rain_data['daily'] = 0
                self.rain_data['weekly'] = 0
                self.rain_data['monthly'] = 0
                self.rain_data['yearly'] = 0
                self.rain_data['yesterday'] = 0
                self.rain_data['hour'] = datetime.datetime.now().hour
                self.rain_data['day'] = datetime.datetime.now().day
                self.rain_data['week'] = datetime.datetime.now().isocalendar()[1]
                self.rain_data['month'] = datetime.datetime.now().month
                self.rain_data['year'] = datetime.datetime.now().year
                # TODO: Can we query the current accumulation data from
                # weatherflow servers???

            self.nodes['rain'].InitializeRain(self.rain_data)

            # Might be able to get some information from API using station
            # number:
            # swd.weatherflow.com/swd/rest/observations/station/<num>?apikey=

    def heartbeat(self):
        LOGGER.debug('heartbeat hb={}'.format(self.hb))
        if self.hb == 0:
            self.reportCmd("DON",2)
            self.hb = 1
        else:
            self.reportCmd("DOF",2)
            self.hb = 0

    def set_hub_timestamp(self):
        s = int(time.time() - self.hub_timestamp)
        LOGGER.debug("set_hub_timestamp: {}".format(s))
        self.setDriver('GV4', s, report=True, force=True)

    def delete(self):
        self.stopping = True
        LOGGER.info('Removing WeatherFlow node server.')

    def my_stop(self):
        self.stopping = True
        # Is there something we should do here to really stop?
        while not self.stopped:
            self.stopping = True

        LOGGER.info('WeatherFlow node server UDP thread finished.')

    def stop(self):
        self.stopping = True
        self.http.close()
        LOGGER.debug('Stopping WeatherFlow node server.')

    def check_units(self):
        if 'Units' in self.polyConfig['customParams']:
            units = self.polyConfig['customParams']['Units'].lower()

            if units != 'metric' and units != 'us' and units != 'uk':
                # invalid units
                units = 'metric'
                self.addCustomParam({'Units': units})
        else:
            units = 'metric'

        return units

    def check_params(self):
        default_units = "metric"

        self.units = self.check_units()

        if 'Station' in self.polyConfig['customParams']:
            self.station = self.polyConfig['customParams']['Station']

        self.myConfig = self.polyConfig['customParams']

        # Make sure they are in the params
        self.addCustomParam({'Station': self.station})

        # Remove all existing notices
        self.removeNoticesAll()

        # Add a notice?

    def remove_notices_all(self,command):
        LOGGER.info('remove_notices_all:')
        # Remove all existing notices
        self.removeNoticesAll()

    def update_profile(self,command):
        LOGGER.info('update_profile:')
        st = self.poly.installprofile()
        return st

    def query_data(self):
        LOGGER.info('Query WeatherFlow server for observation data')
        path_str = '/swd/rest/observations/station/'
        path_str += self.station
        path_str += '?api_key=6c8c96f9-e561-43dd-b173-5198d8797e0a'

        try:
            #http = urllib3.HTTPConnectionPool('swd.weatherflow.com', maxsize=1)

            # Get station observation data
            LOGGER.info(' -  ' + path_str)
            c = self.http.request('GET', path_str)
            data = json.loads(c.data.decode('utf-8'))
        except:
            close(c)
            LOGGER.error('Server Query failed')
            return

        LOGGER.info(data)

        # What we get back can contain indoor_keys, outdoor_keys or both
        # if we have outdoor_keys, use those. If we only have indoor_keys
        # lets switch over and use those.

        if 'outdoor_keys' in data and len(data['outdoor_keys']) > 0:
            LOGGER.info('Found outdoor keys!')
            self.obs_data(data, '')
        elif 'indoor_keys' in data and len(data['indoor_keys']) > 0:
            LOGGER.info('Found indoor keys!')
            self.obs_data(data, '_indoor')
        else:
            LOGGER.info('No observation data available for station.')

        c.close()

    def mySetDriver(self, node, driver, key, data):
        if key in data['obs'][0]:
            self.nodes[node].setDriver(driver, data['obs'][0][key])

    def obs_data(self, data, suffix):

        if len(data['obs']) == 0:
            LOGGER.info('missing observation data')
            return

        # Right now we expect both air and sky data in the obs. What if we
        # only get one of them?
        # do I need to create a function to set a driver and pass
        # def mySetDriver(node, driver, key, data):
        #    if key in data['obs'][0]:
        #        self.nodes[node].setDriver(driver, data['obs'][0][key])
        self.mySetDriver('temperature', 'ST', 'air_temperature' + suffix, data)
        self.mySetDriver('pressure', 'ST', 'barometric_pressure' + suffix, data)
        self.mySetDriver('pressure', 'GV0', 'sea_level_pressure' + suffix, data)
        self.mySetDriver('humidity', 'ST', 'relative_humidity' + suffix, data)
        self.mySetDriver('rain', 'ST', 'precip' + suffix, data)
        self.mySetDriver('rain', 'GV0', 'precip_accum_last_1hr' + suffix, data)
        self.mySetDriver('rain', 'GV1', 'precip_accum_local_day' + suffix, data)
        self.mySetDriver('rain', 'GV2', 'precip_accum_local_yesterday' + suffix, data)
        self.mySetDriver('wind', 'ST', 'wind_avg' + suffix, data)
        self.mySetDriver('wind', 'GV0', 'wind_direction' + suffix, data)
        self.mySetDriver('wind', 'GV1', 'wind_gust' + suffix, data)
        self.mySetDriver('wind', 'GV2', 'wind_lull' + suffix, data)
        self.mySetDriver('light', 'ST', 'uv' + suffix, data)
        self.mySetDriver('light', 'GV0', 'solar_radiation' + suffix, data)
        self.mySetDriver('light', 'GV1', 'brightness' + suffix, data)
        self.mySetDriver('lightning', 'ST', 'lightning_strike_last_3hr' + suffix, data)
        self.mySetDriver('lightning', 'GV0', 'lightning_strike_last_distance' + suffix, data)
        self.mySetDriver('temperature', 'GV0', 'feels_like' + suffix, data)
        self.mySetDriver('temperature', 'GV1', 'dew_point' + suffix, data)
        self.mySetDriver('temperature', 'GV2', 'heat_index' + suffix, data)
        self.mySetDriver('temperature', 'GV3', 'wind_chill' + suffix, data)
        self.mySetDriver('temperature', 'GV4', 'wet_bulb_temperature' + suffix, data)
        self.mySetDriver('temperature', 'GV5', 'delta_t' + suffix, data)
        self.mySetDriver('temperature', 'GV6', 'air_density' + suffix, data)

        #self.nodes['temperature'].setDriver('ST', data['obs'][0]['air_temperature'+suffix])
        #self.nodes['pressure'].setDriver('ST', data['obs'][0]['barometric_pressure'+suffix])
        #self.nodes['pressure'].setDriver('GV0', data['obs'][0]['sea_level_pressure'+suffix])
        #self.nodes['humidity'].setDriver('ST', data['obs'][0]['relative_humidity'+suffix])
        #self.nodes['rain'].setDriver('ST', data['obs'][0]['precip'+suffix])
        #self.nodes['rain'].setDriver('GV0', data['obs'][0]['precip_accum_last_1hr'+suffix])
        #self.nodes['rain'].setDriver('GV1', data['obs'][0]['precip_accum_local_day'+suffix])
        #self.nodes['rain'].setDriver('GV2', data['obs'][0]['precip_accum_local_yesterday'+suffix])
        #self.nodes['wind'].setDriver('ST', data['obs'][0]['wind_avg'+suffix])
        #self.nodes['wind'].setDriver('GV0', data['obs'][0]['wind_direction'+suffix])
        #self.nodes['wind'].setDriver('GV1', data['obs'][0]['wind_gust'+suffix])
        #self.nodes['wind'].setDriver('GV2', data['obs'][0]['wind_lull'+suffix])
        #self.nodes['light'].setDriver('ST', data['obs'][0]['uv'+suffix])
        #self.nodes['light'].setDriver('GV0', data['obs'][0]['solar_radiation'+suffix])
        #self.nodes['light'].setDriver('GV1', data['obs'][0]['brightness'+suffix])
        #self.nodes['lightning'].setDriver('ST', data['obs'][0]['lightning_strike_count_last_3hr'+suffix])
        #self.nodes['lightning'].setDriver('GV0', data['obs'][0]['lightning_strike_last_distance'+suffix])
        #self.nodes['temperature'].setDriver('GV0', data['obs'][0]['feels_like'+suffix])
        #self.nodes['temperature'].setDriver('GV1', data['obs'][0]['dew_point'+suffix])
        #self.nodes['temperature'].setDriver('GV2', data['obs'][0]['heat_index'+suffix])
        #self.nodes['temperature'].setDriver('GV3', data['obs'][0]['wind_chill'+suffix])
        #self.nodes['temperature'].setDriver('GV4', data['obs'][0]['wet_bulb_temperature'+suffix])
        #self.nodes['temperature'].setDriver('GV5', data['obs'][0]['delta_t'+suffix])
        #self.nodes['temperature'].setDriver('GV6', data['obs'][0]['air_density'+suffix])


    def SetUnits(self, u):
        self.units = u


    id = 'WeatherFlow'
    name = 'WeatherFlow'
    address = 'hub'
    stopping = False
    hint = [1, 11, 0, 0]
    units = 'metric'
    commands = {
        'DISCOVER': discover,
        'UPDATE_PROFILE': update_profile,
        'REMOVE_NOTICES_ALL': remove_notices_all
    }
    # Hub status information here: battery and rssi values.
    drivers = [
            {'driver': 'ST', 'value': 1, 'uom': 2},
            {'driver': 'GV4', 'value': 0, 'uom': 57}   # Hub seconds since seen
            ]


class TemperatureNode(polyinterface.Node):
    id = 'temperature'
    hint = [1,11,1,0]
    units = 'us'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 17},
            {'driver': 'GV0', 'value': 0, 'uom': 17}, # feels like
            {'driver': 'GV1', 'value': 0, 'uom': 17}, # dewpoint
            {'driver': 'GV2', 'value': 0, 'uom': 17}, # heat index
            {'driver': 'GV3', 'value': 0, 'uom': 17}, # windchill
            {'driver': 'GV4', 'value': 0, 'uom': 17}, # wet bulb
            {'driver': 'GV5', 'value': 0, 'uom': 17}, # delta T
            {'driver': 'GV6', 'value': 0, 'uom': 56}  # density
            ]
    uoms = {
            'ST': 17,
            'GV0': 17,
            'GV1': 17,
            'GV2': 17,
            'GV3': 17,
            'GV4': 17,
            'GV5': 17,
            'GV6': 56
            }
    
    def SetUnits(self, u):
        self.units = u
        if (u == 'metric'):  # C
            self.uoms['ST'] = 4
            self.uoms['GV0'] = 4
            self.uoms['GV1'] = 4
            self.uoms['GV2'] = 4
            self.uoms['GV3'] = 4
            self.uoms['GV4'] = 4
            self.uoms['GV5'] = 4
        elif (u == 'uk'):  # C
            self.uoms['ST'] = 4
            self.uoms['GV0'] = 4
            self.uoms['GV1'] = 4
            self.uoms['GV2'] = 4
            self.uoms['GV3'] = 4
            self.uoms['GV4'] = 4
            self.uoms['GV5'] = 4
        elif (u == 'us'):   # F
            self.uoms['ST'] = 17
            self.uoms['GV0'] = 17
            self.uoms['GV1'] = 17
            self.uoms['GV2'] = 17
            self.uoms['GV3'] = 17
            self.uoms['GV4'] = 17
            self.uoms['GV5'] = 17

    def Dewpoint(self, t, h):
        b = (17.625 * t) / (243.04 + t)
        rh = h / 100.0

        if rh <= 0:
            return 0

        c = math.log(rh)
        dewpt = (243.04 * (c + b)) / (17.625 - c - b)
        return round(dewpt, 1)

    def ApparentTemp(self, t, ws, h):
        wv = h / 100.0 * 6.105 * math.exp(17.27 * t / (237.7 + t))
        at =  t + (0.33 * wv) - (0.70 * ws) - 4.0
        return round(at, 1)

    def Windchill(self, t, ws):
        # really need temp in F and speed in MPH
        tf = (t * 1.8) + 32
        mph = ws / 0.44704

        wc = 35.74 + (0.6215 * tf) - (35.75 * math.pow(mph, 0.16)) + (0.4275 * tf * math.pow(mph, 0.16))

        if (tf <= 50.0) and (mph >= 5.0):
            return round((wc - 32) / 1.8, 1)
        else:
            return t

    def Heatindex(self, t, h):
        tf = (t * 1.8) + 32
        c1 = -42.379
        c2 = 2.04901523
        c3 = 10.1433127
        c4 = -0.22475541
        c5 = -6.83783 * math.pow(10, -3)
        c6 = -5.481717 * math.pow(10, -2)
        c7 = 1.22874 * math.pow(10, -3)
        c8 = 8.5282 * math.pow(10, -4)
        c9 = -1.99 * math.pow(10, -6)

        hi = (c1 + (c2 * tf) + (c3 * h) + (c4 * tf * h) + (c5 * tf *tf) + (c6 * h * h) + (c7 * tf * tf * h) + (c8 * tf * h * h) + (c9 * tf * tf * h * h))

        if (tf < 80.0) or (h < 40.0):
            return t
        else:
            return round((hi - 32) / 1.8, 1)

    def setDriver(self, driver, value):
        if (driver != "GV6"):
            if (self.units == "us"):
                value = (value * 1.8) + 32  # convert to F
            value = round(value, 1)

        super(TemperatureNode, self).setDriver(driver, value, report=True, force=False, uom=self.uoms[driver])



class HumidityNode(polyinterface.Node):
    id = 'humidity'
    hint = [1,11,2,0]
    units = 'metric'
    drivers = [{'driver': 'ST', 'value': 0, 'uom': 22}]

    def SetUnits(self, u):
        self.units = u

    def setDriver(self, driver, value):
        super(HumidityNode, self).setDriver(driver, value, report=True, force=False)

class PressureNode(polyinterface.Node):
    id = 'pressure'
    hint = [1,11,3,0]
    units = 'metric'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 117},  # abs (station) press
            {'driver': 'GV0', 'value': 0, 'uom': 117}, # rel (sealevel) press
            {'driver': 'GV1', 'value': 0, 'uom': 25}  # trend
            ]
    uoms = {
            'ST': 117,
            'GV0': 117,
            'GV1': 25
            }
    mytrend = []


    def SetUnits(self, u):
        # can we dynmically set the drivers here also?
        # what about the ID, can we dynamically change that to change
        # the node def?
        self.units = u
        if (u == 'metric'):  # millibar
            self.uoms['ST'] = 117
            self.uoms['GV0'] = 117
        elif (u == 'uk'):  # millibar
            self.uoms['ST'] = 117
            self.uoms['GV0'] = 117
        elif (u == 'us'):   # inHg
            self.uoms['ST'] = 23
            self.uoms['GV0'] = 23

    # convert station pressure in millibars to sealevel pressure
    def toSeaLevel(self, station, elevation):
        i = 287.05  # gas constant for dry air
        a = 9.80665 # gravity
        r = 0.0065  # standard atmosphere lapse rate
        s = 1013.35 # pressure at sealevel
        n = 288.15  # sea level temperature

        l = a / (i * r)

        c = i * r / a

        u = math.pow(1 + math.pow(s / station, c) * (r * elevation / n), l)

        return (round((station * u), 3))

    # track pressures in a queue and calculate trend
    def updateTrend(self, current):
        t = 1  # Steady
        past = 0

        if len(self.mytrend) > 1:
            LOGGER.info('LAST entry = %f' % self.mytrend[-1])
        if len(self.mytrend) == 180:
            # This should be poping the last entry on the list (or the 
            # oldest item added to the list).
            past = self.mytrend.pop()

        if self.mytrend != []:
            # mytrend[0] seems to be the last entry inserted, not
            # the first.  So how do we get the last item from the
            # end of the array -- mytrend[-1]
            past = self.mytrend[-1]

        # calculate trend
        LOGGER.info('TREND %f to %f' % (past, current))
        if ((past - current) > 1):
            t = 0 # Falling
        elif ((past - current) < -1):
            t = 2 # Rising

        # inserts the value at index 0 and bumps all existing entries
        # up by one index
        self.mytrend.insert(0, current)

        return t

    # We want to override the SetDriver method so that we can properly
    # convert the units based on the user preference.
    def setDriver(self, driver, value):
        if (self.units == 'us' and driver != 'GV1' ):
            value = round(value * 0.02952998751, 3)
        super(PressureNode, self).setDriver(driver, value, report=True, force=False, uom=self.uoms[driver])


class WindNode(polyinterface.Node):
    id = 'wind'
    hint = [1,11,4,0]
    units = 'metric'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 32},  # speed
            {'driver': 'GV0', 'value': 0, 'uom': 76}, # direction
            {'driver': 'GV1', 'value': 0, 'uom': 32}, # gust
            {'driver': 'GV2', 'value': 0, 'uom': 32}  # lull
            ]
    uoms = {
            'ST': 32,
            'GV0': 76,
            'GV1': 32,
            'GV2': 32
            }

    def SetUnits(self, u):
        self.units = u
        if (u == 'metric'):
            self.uoms['ST'] = 32
            self.uoms['GV1'] = '32'
            self.uoms['GV2'] = '32'
        elif (u == 'uk'): 
            self.uoms['ST'] = 48
            self.uoms['GV1'] = '48'
            self.uoms['GV2'] = '48'
        elif (u == 'us'): 
            self.uoms['ST'] = 48
            self.uoms['GV1'] = '48'
            self.uoms['GV2'] = '48'

    def setDriver(self, driver, value):
        if (driver == 'ST' or driver == 'GV1' or driver == 'GV3'):
            if (self.units != 'metric'):
                value = round(value / 1.609344, 2)
        super(WindNode, self).setDriver(driver, value, report=True, force=False, uom=self.uoms[driver])

class PrecipitationNode(polyinterface.Node):
    id = 'precipitation'
    hint = [1,11,5,0]
    units = 'metric'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 46},  # rate
            {'driver': 'GV0', 'value': 0, 'uom': 82}, # hourly
            {'driver': 'GV1', 'value': 0, 'uom': 82}, # daily
            {'driver': 'GV2', 'value': 0, 'uom': 82}  # yesterday
            ]
    uoms = {
            'ST': 46,
            'GV0': 82,
            'GV1': 82,
            'GV2': 82
            }
    hourly_rain = 0
    daily_rain = 0
    weekly_rain = 0
    monthly_rain = 0
    yearly_rain = 0
    yesterday_rain = 0

    prev_hour = 0
    prev_day = 0
    prev_week = 0
    prev_month = 0
    prev_year = 0

    def InitializeRain(self, acc):
        self.daily_rain = acc['daily']
        self.hourly_rain = acc['hourly']
        self.weekly_rain = acc['weekly']
        self.monthly_rain = acc['monthly']
        self.yearly_rain = acc['yearly']
        self.yesterday_rain = acc['yesterday']

        self.prev_hour = acc['hour']
        self.prev_day = acc['day']
        self.prev_week = acc['week']
        self.prev_month = acc['month']
        self.prev_year = acc['year']

        now = datetime.datetime.now()

        # Need to compare saved date with current date and clear out 
        # any accumlations that are old.

        current_hour = now.hour
        if self.prev_hour != now.hour:
            LOGGER.info('Clearing old hourly data')
            self.prev_hour = now.hour
            self.hourly_rain = 0

        if self.prev_day != now.day:
            LOGGER.info('Clearing old daily, hourly data')
            self.yesterday_rain = self.daily_rain
            self.prev_day = now.day
            self.hourly_rain = 0
            self.daily_rain = 0

        if self.prev_week != now.isocalendar()[1]:
            LOGGER.info('Clearing old weekly, daily, hourly data')
            self.prev_week = now.isocalendar()[1]
            self.hourly_rain = 0
            self.daily_rain = 0
            self.weekly_rain = 0

        if self.prev_month != now.month:
            LOGGER.info('Clearing old monthly, daily, hourly data')
            self.prev_month = now.month
            self.hourly_rain = 0
            self.daily_rain = 0
            self.weekly_rain = 0
            self.monthly_rain = 0

        if self.prev_year != now.year:
            LOGGER.info('Clearing old yearly, monthly, daily, hourly data')
            self.prev_year = now.year
            self.hourly_rain = 0
            self.daily_rain = 0
            self.weekly_rain = 0
            self.monthly_rain = 0
            self.yearly_rain = 0


    def SetUnits(self, u):
        self.units = u
        if (u == 'metric'):
            self.uoms['ST'] = 46
            self.uoms['GV0'] = 82
            self.uoms['GV1'] = 82
            self.uoms['GV2'] = 82
        elif (u == 'uk'): 
            self.uoms['ST'] = 46
            self.uoms['GV0'] = 82
            self.uoms['GV1'] = 82
            self.uoms['GV2'] = 82
        elif (u == 'us'): 
            self.uoms['ST'] = 24
            self.uoms['GV0'] = 105
            self.uoms['GV1'] = 105
            self.uoms['GV2'] = 105

    def hourly_accumulation(self, r):
        current_hour = datetime.datetime.now().hour
        if (current_hour != self.prev_hour):
            self.prev_hour = current_hour
            self.hourly_rain = 0

        self.hourly_rain += r
        return self.hourly_rain

    def daily_accumulation(self, r):
        current_day = datetime.datetime.now().day
        if (current_day != self.prev_day):
            self.yesterday_rain = self.daily_rain
            self.prev_day = current_day
            self.daily_rain = 0

        self.daily_rain += r
        return self.daily_rain

    def yesterday_accumulation(self):
        return self.yesterday_rain

    def weekly_accumulation(self, r):
        (y, w, d) = datetime.datetime.now().isocalendar()
        if w != self.prev_week:
            self.prev_week = w
            self.weekly_rain = 0

        self.weekly_rain += r
        return self.weekly_rain

    def monthly_accumulation(self, r):
        current_month = datetime.datetime.now().month
        if (current_month != self.prev_month):
            self.prev_month = current_month
            self.monthly_rain = 0

        self.monthly_rain += r
        return self.monthly_rain

    def yearly_accumulation(self, r):
        current_year = datetime.datetime.now().year
        if (current_year != self.prev_year):
            self.prev_year = current_year
            self.yearly_rain = 0

        self.yearly_rain += r
        return self.yearly_rain

        
    def setDriver(self, driver, value):
        if (self.units == 'us'):
            value = round(value * 0.03937, 2)
        super(PrecipitationNode, self).setDriver(driver, value, report=True, force=False, uom=self.uoms[driver])

class LightNode(polyinterface.Node):
    id = 'light'
    units = 'metric'
    hint = [1,11,6,0]
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 71},  # UV
            {'driver': 'GV0', 'value': 0, 'uom': 74},  # solar radiation
            {'driver': 'GV1', 'value': 0, 'uom': 36},  # Lux
            ]
    uoms = {
            'ST': 71,
            'GV0': 74,
            'GV1': 36
            }

    def SetUnits(self, u):
        self.units = u

    def setDriver(self, driver, value):
        super(LightNode, self).setDriver(driver, value, report=True, force=False)

class LightningNode(polyinterface.Node):
    id = 'lightning'
    hint = [1,11,7,0]
    units = 'metric'
    drivers = [
            {'driver': 'ST', 'value': 0, 'uom': 25},  # Strikes
            {'driver': 'GV0', 'value': 0, 'uom': 83},  # Distance
            ]
    uoms = {
            'ST': 25,
            'GV0': 83
            }

    def SetUnits(self, u):
        self.units = u
        if (u == 'metric'):
            self.uoms['ST'] = 83
            self.uoms['GV0'] = 25
        elif (u == 'uk'): 
            self.uoms['ST'] = 116
            self.uoms['GV0'] = 25
        elif (u == 'us'): 
            self.uoms['ST'] = 116
            self.uoms['GV0'] = 25

    def setDriver(self, driver, value):
        if (driver == 'GV0'):
            if (self.units != 'metric'):
                value = round(value / 1.609344, 1)
        super(LightningNode, self).setDriver(driver, value, report=True, force=False, uom=self.uoms[driver])


if __name__ == "__main__":
    try:
        polyglot = polyinterface.Interface('WeatherFlow')
        """
        Instantiates the Interface to Polyglot.
        """
        polyglot.start()
        """
        Starts MQTT and connects to Polyglot.
        """
        control = Controller(polyglot)
        """
        Creates the Controller Node and passes in the Interface
        """
        control.runForever()
        """
        Sits around and does nothing forever, keeping your program running.
        """
    except (KeyboardInterrupt, SystemExit):
        sys.exit(0)
        """
        Catch SIGTERM or Control-C and exit cleanly.
        """
