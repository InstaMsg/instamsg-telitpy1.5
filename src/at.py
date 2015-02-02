# -*- coding: utf-8 -*-
import MDM
import MDM2
import MOD
import exceptions

class ATError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)

class ATTimeoutError(exceptions.IOError):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
timeout= ATTimeoutError
error = ATError

def sendCmd(cmd, timeOut=2, expected='OK\r\n', addCR = 1,mdm=1):
    try:
        if(mdm==2):
            mdm=MDM2
        else:
            mdm=MDM
        if (timeOut <= 0): timeOut=2
        if (addCR == 1):
            r= mdm.send(cmd + '\r', 5)
        else:
            r = mdm.send(cmd, 5)
        if (r < 0):
            raise timeout('Send "%s" timed out.' % cmd)
        timer = MOD.secCounter() + timeOut
        response = cmd + mdm.read()
        while (timeOut > 0 and (not expected or response.find(expected) == -1)):
            response = response + mdm.read()
            timeOut = timer - MOD.secCounter()
        if(response.find(expected) == -1):
            if (timeOut > 0):
                raise error('Expected response "%s" not received.' % expected.strip())
            else:
                raise timeout('Receive timed out.')
        if(response.find('ERROR') > 0):
            raise error('ERROR response received for "%s".'% cmd) 
        else:
            return response
    except error, e:
        raise error(str(e))
    except timeout,e:
        raise timeout(str(e))
    except Exception, e:
        raise error("UnexpectedError, command %s failed." %cmd)
    
def reboot():
    try:
        sendCmd('AT#REBOOT')
        return 1
    except:
        return 0
    
def factoryReset():
    try:
        sendCmd('AT&F')
        return 1
    except:
        return 0
    
def getModel():
    try:
        return sendCmd('AT+GMM',1).split('\r\n')[1]
    except:
        return ''

def getFirmwareVersion():
    try:
        return sendCmd('AT+GMR',1).split('\r\n')[1]
    except:
        return ''

def getSignalQuality():
    try:
        return sendCmd('AT+CSQ',1).split('\r\n')[1].replace('+CSQ: ','').split(',')
    except:
        return []
    
def subscriberNumber():
    try:
        return sendCmd('AT+CNUM',1).split('\r\n')[1].replace('+CNUM: ','').split(',')
    except:
        return []
#Python Script AT commands

def setTemperatureMonitor(mode,urcmode=1,action=1,hysteresis=255,gpio=None):
#    parameters: (0,1),(0,1),(0-7),(0-255),(1-8)
    try:
        cmd = 'AT#TEMPMON=%d,%d,%d,%d'%(mode,urcmode,action,hysteresis)
        if(gpio): cmd = cmd + ',%d'%gpio
        sendCmd(cmd)
        return mode
    except:
        return -1

def getTemperature():
    try:
        return sendCmd('AT#TEMPMON=1').split('\r\n')[1].replace('#TEMPMEAS: ','').split(',')
    except:
        return ''

def setFlowControl(value=0):
    try:
        resp = sendCmd('AT&K?')
        if(resp.find('00%d'%value) < 0):
            resp= sendCmd('AT&K=%d' %value)
        return 1
    except:
        return -1
    
def setCmux(mode=0,baudrate=9600):
    try:
        resp = sendCmd('AT#CMUXSCR?')
        if(resp.find('#CMUXSCR: %d'%mode) < 0 or resp.find('#CMUXSCR: %d,%d'%(mode,baudrate)) <0 ):
            resp= sendCmd('AT#CMUXSCR=%d,%d' %(mode,baudrate))
        return 1
    except:
        return -1
    
def getAntennaStatus():
#0 - antenna connected.
#1 - antenna connector short circuited to ground.
#2 - antenna connector short circuited to power.
#3 - antenna not detected (open).
    try:
        return int(sendCmd('AT#GSMAD=3',10).split('\r\n')[1].split(':')[1])
    except:
        return -1

def getActiveScript():
    return sendCmd('AT#ESCRIPT?',1).replace('#ESCRIPT: ','').replace('"','')
    
def getfilelist():
    return sendCmd('AT#LSCRIPT',1).replace('#LSCRIPT: ','').replace('"','').split('\r\n')

#Time AT commands

def getRtcTime():
    return sendCmd('AT+CCLK?',1).split('\r\n')[1].split('"')[1]

def setRtcTime(time):
#time in "yy/MM/dd,hh:mm:ss±zz"
#zz is time zone (indicates the difference, expressed in quarter of an hour, 
#between the local time and GMT; two last digits are mandatory), range is -47..+48
    return sendCmd('AT+CCLK = "%s"' %time)

def setDateFormat(mode=1,auxmode=1):
    return sendCmd('AT+CSDF=%d,%d' %(mode,auxmode))

def setAutoTimeZoneUpdateFromNetwork(value=1):
    resp = sendCmd('AT+CTZU?')
    if(resp.find('+CTZU: %d'%value) < 0):
        resp= sendCmd('AT+CTZU=%d' %value)
    return resp

def setAutoDateTimeUpdateFromNetwork(value=7, mode=0):
    resp = sendCmd('AT#NITZ?')
    if(resp.find('#NITZ: %d,%d'%(value,mode)) < 0):
        resp= sendCmd('AT#NITZ=%d,%d' %(value,mode))
    return resp

def setNtpSever(ip='ntp.ioeye.com',port=123):
    resp = sendCmd('AT#NTP?')
    if(resp.find('#NTP="%s",%d,%d,%d' %(ip, port,1,5)) < 0):
        resp= sendCmd('AT#NTP="%s",%d,%d,%d' %(ip, port,1,5))
    return resp

def setPowerMode(mode=1):
#0 - minimum functionality, NON-CYCLIC SLEEP mode: in this mode, the AT interface is not accessible. Consequently, once you have set <fun> level 0, do not send further characters. Otherwise these characters remain in the input buffer and may delay the output of an unsolicited result code. The first wake-up event, or rising RTS line, stops power saving and takes the ME back to full functionality level <fun>=1.
#1 - mobile full functionality with power saving disabled (factory default)
#2 - disable TX
#4 - disable either TX and RX
#5 - mobile full functionality with power saving enabled
    resp = getPowerMode()
    if(resp!=mode):
        return sendCmd('AT+CFUN= %d' %(mode))  
    return resp

def setInterfaceStyle():
    if(sendCmd('AT#SELINT?',1).find('AT#SELINT: 2') > 0): return 1
    else:sendCmd('AT#SELINT=2',1)

def getPowerMode():
    return int(sendCmd('AT+CFUN?').split('\r\n')[1].split(':')[1])

def getBatteryStatus():
    return sendCmd('AT+CBC').split('\r\n')[1].replace('+CBC: ', '').split(',')

def getFireWallSettings():
    return sendCmd('AT#FRWL?')

def addToFireWall(ip,subnet):
    cmdValue= 'AT#FRWL=1,"%s","%s"' %(ip, subnet)
    return sendCmd(cmdValue)

def removeFromFireWall(ip,subnet):
    cmdValue= 'AT#FRWL=0,"%s","%s"' %(ip, subnet)
    return sendCmd(cmdValue)

def dropAllFireWallRules():
    return sendCmd('AT#FRWL=2')

def getIMEI(retry = 20):
    imei=''
    if(retry <= 0): retry=1
    while (retry > 0):
        retry = retry - 1
        try:
            imei = sendCmd('AT+CGSN').split('\r\n')[1]
            if(imei): break
            MOD.sleep(50)
        except:
            MOD.sleep(50)
            continue
    return imei

def initSimDetect(simDetectMode='',retry = 20):  
    if simDetectMode < 0 or simDetectMode > 2: return 0
    success=0
    if(retry <= 0): retry=1
    while (retry > 0):
        retry = retry - 1
        try:
            response = sendCmd('AT#SIMDET?',5)
            if (response.find(str(simDetectMode) + ',') > 0):
                success = 1
                break
            else:
                sendCmd('AT#SIMDET=' + str(simDetectMode) ,5)
                success = 1
                break
            MOD.sleep(50)
        except:
            MOD.sleep(50)
            continue
    return success

def initPin(pin='',retry = 20):  
    success=0
    if(retry <= 0): retry=1
    while (retry > 0):
        retry = retry - 1
        try:
            response = sendCmd('AT+CPIN?',5)
            if (response.find('READY') > 0):
                success = 1
                break
            if (response.find('SIM PIN') > 0):
                sendCmd('AT+CPIN=' + pin,5)
                success = 1
                break
            MOD.sleep(50)
        except:
            MOD.sleep(50)
            continue
    return success

def initNetwork(retry = 20):
    success=0
    if(retry <= 0): retry=1
    while (retry > 0):
        retry = retry - 1
        try:
            response = sendCmd('AT+CREG?', 5)
            if (response.find('0,1') > 0 or response.find('0,5') > 0):
                success=1
                break
            MOD.sleep(50)
        except:
            MOD.sleep(50)
            continue
    return success  

def initGPRS(pdpContextId= 1, apn='',userid='', passw='',retry=20):
    success=0
    if(retry <= 0): retry=1
    while (retry > 0):
        retry = retry - 1
        try:
            gprs=sendCmd('AT+CGDCONT?;#USERID?',1)
            if(gprs.find('%d,"IP","%s"'%(pdpContextId, apn)) < 0 or gprs.find('#USERID: "%s"'%userid) < 0):
                sendCmd('AT+CGDCONT=%d,"IP","%s";#USERID="%s";#PASSW="%s"' %(pdpContextId, apn,userid,passw))    
            sendCmd('AT+CGATT?',5,'+CGATT: 1')
            setGPRSContextConfig()
            success=1
            break
        except:
            MOD.sleep(10)
            continue
    return success  

def activateGPRSContext(pdpContextId=1, retry = 20):
#"Activates the GPRS context for internet."
    success=0
    if(pdpContextId > 5 or pdpContextId < 1): return 0
    if(retry <= 0): retry=1
    while (retry > 0):
        retry = retry - 1
        try:
            sendCmd('AT#SGACT=%d,1'%pdpContextId,1,'IP')
            success=1
            break
        except:
            MOD.sleep(10)
            continue
    return success  

def deactivateGPRSContext(pdpContextId=1, retry = 20):
#"Activates the GPRS context for internet."
    success=0
    if(pdpContextId > 5 or pdpContextId < 1): return 0
    if(retry <= 0): retry=1
    while (retry > 0):
        retry = retry - 1
        try:
            sendCmd('AT#SGACT=%d,0'%pdpContextId,1)
            success=1
            break
        except:
            MOD.sleep(10)
            continue
    return success 

def setGPRSAutoAttach(value=1):
    resp = sendCmd('AT#AUTOATT?')
    if(resp.find('#AUTOATT: %d'%value) < 0):
        cmdValue = 'AT#AUTOATT=%d' %value
        resp= sendCmd(cmdValue)
    return resp

def getGPRSContextStatus(pdpContextId=1, retry=5):  
    status=0
    if(retry <= 0): retry=1
    while (retry > 0):
        retry = retry - 1
        try:
            if(sendCmd('AT#SGACT?',1).find('#SGACT: %d,1'%pdpContextId) > 0): status=1
            break
        except:
            MOD.sleep(10)
            continue
    return status  

def initGPRSConnection(pdpContextId=1, retry=20, drop=0):
# Set drop=1 if you want to drop existing GPRS context create new one.
    try:
        status = 0
        if(retry <= 0): retry = 1
        status = getGPRSContextStatus(pdpContextId, 1)
        while((status in (0, 2) or drop) and retry > 0):
            retry = retry - 1
            if(status == 0):
                activateGPRSContext(1)
            elif(status == 1 and drop == 1):
                deactivateGPRSContext(pdpContextId, 1)
                activateGPRSContext(pdpContextId, 1)
            elif(status == 2):
                MOD.sleep(10)
            drop = 0
            status = getGPRSContextStatus(pdpContextId, 1)
        return status
    except:
        return 0

def setGPRSContextConfig(pdpContextId=1,retry=15,delay=180):
    sendCmd('AT#SGACTCFG=%d,%d,%d'%(pdpContextId,retry,delay))
     
def configureSocket(connId,cid=1,pktSz=512,maxTo=0,connTo=600,txTo=50,keepAlive=0,listenAutoRsp=0):
#connId(1-6),cid(0-5),pktSz(0-1500),maxTo(0-65535),connTo(10-1200),txTo(0-255)
#keepAlive(0 – 240)min
    sendCmd('AT#SCFG=%d,%d,%d,%d,%d,%d'%(connId,cid,pktSz,maxTo,connTo,txTo))
    sendCmd('AT#SCFGEXT= %d,0,0,%d,%d'%(connId,keepAlive,listenAutoRsp))
        
def connectSocket(connId,addr,proto=0,closureType=0,IPort=0,timeout=60):
    connMode=1 #always connect in command mode
    sendCmd('AT#SD=%d,%d,%d,"%s",%d,%d,%d'%(connId,proto,addr[1],addr[0],closureType,IPort,connMode),timeout)

def closeSocket(connId,timeout):
    sendCmd('AT#SH=%d' %connId, timeout)

def socketRecv(connId,maxByte,timeout):
    return sendCmd('AT#SRECV=%d,%d'%(connId, maxByte),timeout).split('\r\n')[2]

def socketSend(connId,data,bytestosend,timeout,multiPart=0):
#bytestosend(1-1500)
    if(multiPart==0):
        sendCmd('AT#SSENDEXT=%d,%d'%(connId,bytestosend),1,'')
    sendCmd(data, timeout, expected='OK\r\n', addCR = 0)
    return bytestosend

def socketGetHTTP(connId,addr,data,timeout=30):
    try:
        sendCmd('AT#SD=%d,0,%d,"%s",0,0,0'%(connId,addr[1],addr[0]),timeout,expected='CONNECT\r\n',mdm=2)
        sendCmd(data,timeout,expected='HTTP/1.1 200 OK', addCR=0, mdm=2)
    finally:
        sendCmd('+++',timeout, expected='NO CARRIER\r\n', addCR=0, mdm=2)
    
def socketStatus(connId=None):
    if(connId):
        return sendCmd('AT#SS',mdm=2).split('\r\n')[connId].replace('#SS: ','')
    else:
        return sendCmd('AT#SS',mdm=2).replace('#SS: ','').split('\r\n')[1:6]

def suspendSocket():   
    sendCmd('+++')
    MOD.sleep(20)

def resumeSocket(connId):
    sendCmd('AT#SO='%connId)

def socketInfo(connId):
    return sendCmd('AT#SI='%connId).split('\r\n')[1].replace('#SI: ','').split(',')

def socketListen(connId,listenState,listenPort,closureType=0,timeout=60):
    sendCmd('AT#SL=%d,%d,%d,%d' %(connId,listenState,listenPort,closureType),timeout)

def socketAccept(connId,connMode=1):
    sendCmd('AT#SA=%d,%d'%(connId,connMode))

def socketBase64(connId,enc,dec):
    sendCmd('#AT#BASE64=%d,%d,%d'%(connId,enc,dec))
    