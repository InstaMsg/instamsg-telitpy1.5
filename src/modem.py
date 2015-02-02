# -*- coding: utf-8 -*-
import at
import exceptions

class ModemError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
error = ModemError

MODEM_LOG_LEVEL_DISABLED = 0
MODEM_LOG_LEVEL_INFO = 1
MODEM_LOG_LEVEL_ERROR = 2
MODEM_LOG_LEVEL_DEBUG = 3

class Modem:
    DEFAULT_NTP_PORT = 23
    
    def __init__(self, settings, onDebugMessageCallBack = None):  
        if(onDebugMessageCallBack is not None and not callable(onDebugMessageCallBack)): raise ValueError('[Modem]:: onDebugMessageCallBack should be a callable object.') 
        try:
            self.__onDebugMessageCallBack = onDebugMessageCallBack
            self.__log(MODEM_LOG_LEVEL_INFO, "[Modem]:: Configuring modem...")
            self.__initOptions(settings)
            self.state = 0
            self.__init()
            self.__setPowerMode()
            self.__setFireWall() 
            self.__initGPRSConnection()
            if (self.ntpServer):
                self.__setNtp()
            else:
                self.__enableNetworkTime()
            self.__log(MODEM_LOG_LEVEL_INFO, "[Modem]:: Configured successfully with settings: %s" % str(self.settings()))
        except Exception, e:
            raise ModemError("[Modem]:: Error while initializing modem. %s" % str(e))
        
    def state(self):
        return self.state
    
    def getSignalQuality(self):
        try:
            return at.getSignalQuality()
        except:
            return -1
    
    def settings(self):
        try:
            return {
                 'state':self.state,
                 'imei':self.imei,
                 'model':self.model,
                 'firmware':self.firmware,
                 'power_mode':self.powerMode,
                 'subscriber_number':self.subscriberNumber,
                 'antenna_status':self.__getAntennaStatus(),
                 'signal_quality': self.getSignalQuality(),
                 'ntp_server': self.ntpServer,
                 'sim_detection_mode':self.simDetectionMode,
                 'sim_pin':self.simPin,
                 'gprs_apn':self.gprsApn,
                 'gprs_userid':self.gprsUserId,
                 'gprs_pswd':self.gprsPwd,
                 'firewall_addresses': self.firewallAddresses
                 }
        except:
            return {}
        
    def __getAntennaStatus(self):
        try:
            s = "Unable to determine antenna status. "
            if(self.antennaStatus is 0):
                return  "0 - Antenna Connected."
            elif(self.antennaStatus is 1):
                return "1 - Antenna connector short circuited to ground."
            elif(self.antennaStatus is 2):
                return "2 - Antenna connector short circuited to power."
            elif(self.antennaStatus is 3):
                return "3 - Antenna not detected (open)."
            else:
                return s
        except:
            return s
        
    def __initOptions(self,options):
        if(options.has_key('logLevel')):
            self.__logLevel = options.get('logLevel')
        else:self.__logLevel = 0
        if(options.has_key('firewall_addresses')):
            self.firewallAddresses = options['firewall_addresses']
        else: self.firewallAddresses = None
        if(options.has_key('ntp_server')):
            self.ntpServer = options['ntp_server']
            if(options.has_key('ntp_port')):
                self.ntpPort = options['ntp_port']
            else: self.ntpPort = self.DEFAULT_NTP_PORT
        else: 
            self.ntpServer, self.ntpPort = None, None
        if(options.has_key('sim_detection_mode')):
            self.simDetectionMode = options.get('sim_detection_mode')
        else:self.simDetectionMode = 1  
        if(options.has_key('sim_pin')):
            self.simPin = options.get('sim_pin')
        else:self.simPin = 1    
        if(options.has_key('gprs_apn')):
            self.gprsApn = options.get('gprs_apn')
        else:self.gprsApn = ''    
        if(options.has_key('gprs_userid')):
            self.gprsUserId = options.get('gprs_userid')
        else:self.gprsUserId = '' 
        if(options.has_key('gprs_pswd')):
            self.gprsPwd = options.get('gprs_pswd')
        else:self.gprsPwd = '' 
        
    def __init(self, retry=20):
        try:
            if(retry <= 0): retry = 1
            self.state = 0
            self.model = at.getModel()
            self.imei = at.getIMEI()
            self.firmware = at.getFirmwareVersion()
            self.powerMode = at.getPowerMode()
            self.subscriberNumber = at.subscriberNumber()
            self.antennaStatus = at.getAntennaStatus()
            self.__log(MODEM_LOG_LEVEL_INFO, '[Modem]:: Checking and initializing SIM...')
            if(not at.initSimDetect(self.simDetectionMode, retry)): 
                self.__log(MODEM_LOG_LEVEL_INFO, '[Modem]:: Unable to initialize SIM.')
                return 0
            self.__log(MODEM_LOG_LEVEL_INFO, '[Modem]:: SIM Detected.')
            if(not at.initPin(self.simPin, retry)): 
                self.__log(MODEM_LOG_LEVEL_INFO, '[Modem]:: Unable to set SIM PIN.')
                return 0
            self.__log(MODEM_LOG_LEVEL_INFO, '[Modem]:: SIM OK.')
            self.__log(MODEM_LOG_LEVEL_INFO, '[Modem]:: Checking and initializing Network...')
            if(not at.initNetwork(retry)): 
                self.__log(MODEM_LOG_LEVEL_INFO, '[Modem]:: Unable to initialize Network.')
                return 0
            self.__log(MODEM_LOG_LEVEL_INFO, '[Modem]:: Network OK.')
            self.__log(MODEM_LOG_LEVEL_INFO, '[Modem]:: Checking and initializing GPRS settings...')
            if(not at.initGPRS(1, self.gprsApn, self.gprsUserId, self.gprsPwd, retry)): 
                self.__log(MODEM_LOG_LEVEL_INFO, '[Modem]:: Unable to initialize GPRS context.')
                return 0
            self.__log(MODEM_LOG_LEVEL_INFO, '[Modem]:: GPRS Settings OK.')
            self.__log(MODEM_LOG_LEVEL_INFO, '[Modem]:: SIM and GPRS OK.')
            self.modem['state'] = 1
        except:
            self.modem['state'] = 0
            self.__log(MODEM_LOG_LEVEL_ERROR, "[Modem]:: Error configuring modem. Continuing without it...")
    
    def __setNtp(self):
        try:
            self.__log(MODEM_LOG_LEVEL_INFO, "[Modem]:: Configuring NTP server...")
            at.setNtpSever(self.ntpServer, self.ntpPort or 123)
        except(at.error, at.timeout):
            self.__log(MODEM_LOG_LEVEL_INFO, "[Modem]:: Unable to configure NTP server. Enabling Network Time...")
            self.__enableNetworkTime()
                    
    def __enableNetworkTime(self):
        try:
            self.__log(MODEM_LOG_LEVEL_INFO, "[Modem]:: Enabling auto update network time...")
            at.setAutoTimeZoneUpdateFromNetwork()
            at.setAutoDateTimeUpdateFromNetwork()
        except(at.error, at.timeout):
            self.__log(MODEM_LOG_LEVEL_ERROR, "[Modem]:: Unable to set auto sync time from network. Continuing without it...")
    
    def __setPowerMode(self):
        try:
            self.__log(MODEM_LOG_LEVEL_INFO, "[Modem]:: Disabling power saving mode...")
            if(at.getPowerMode() is not 1):
                at.setPowerMode(1)
        except:
            self.__log(MODEM_LOG_LEVEL_INFO, "[Modem]:: Unable to disable power saving mode. Continuing without it...")
            
    def __initGPRSConnection(self):
            self.__log(MODEM_LOG_LEVEL_INFO, '[Modem]:: Checking and initializing GPRS connection...')
            gprs = at.initGPRSConnection(pdpContextId=1)
            if(gprs):
                self.__log(MODEM_LOG_LEVEL_INFO, "[Modem]:: GPRS OK.")
            else:
                self.__log(MODEM_LOG_LEVEL_ERROR, "[Modem]:: Unable to initialize GPRS connection.Continuing without it..")
    
    def __setFireWall(self):
        try:
            self.__log(MODEM_LOG_LEVEL_INFO, "[Modem]:: Dropping all firewall rules...")
            at.dropAllFireWallRules() 
            if(self.firewallAddresses):
                self.__log(MODEM_LOG_LEVEL_INFO, "[Modem]:: Initializing firewall...")
                for address in self.firewallAddresses:
                    at.addToFireWall(address[0], address[1])
                self.__log(MODEM_LOG_LEVEL_INFO, "[Modem]:: Firewall ser. Settings are: %s" % str(at.getFireWallSettings()))
        except:
            self.__log(MODEM_LOG_LEVEL_ERROR, "[Modem]:: Unable to set firewall. Continuing without it...")
    
    def __log(self, level, msg):
        try:
            if(level <= self.__logLevel):
                if(self.__onDebugMessageCallBack):
                    self.__onDebugMessageCallBack(level, msg) 
        except:
            pass
