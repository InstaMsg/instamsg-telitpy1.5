# -*- coding: utf-8 -*-
import MOD
import MDM
import MDM2
import sys 
import instamsg

####Brockers ###############################################################################

class Broker:
    
    def __init__(self, settings, publisher=None):
        self.name = str(settings.get('name'))
        self.dataLogger = settings.get('data_logger')
        self.tcpAddr = settings.get('tcp_addr')
        self.keepAlive = int(settings.get('keep_alive'))
        self.address = settings.get('address')
        self.debug = settings.get('debug')
        self.sock = None
        self.sockInit = 0
        self._subscribers = {}#{'topic':[callback1,callback2]}
        self._publisher = publisher
        self._nextConnTry = time.time()
        
    def process(self):
        try:
            self.__initSock()
            if(self.sockInit):
                t=time.time()
                if(self.dataLogger and self.dataLogger.shouldUpload()):
                    self.__processDataLogs()
                self.__receive()
        except SocketTimeoutError:
            pass
        except SocketError, msg:
            self.sockInit = 0
            if (self.debug):
                print("%s Broker SocketError in process: %s" % (self.name, str(msg)))
        except:
            if (self.debug):
                print("%s Broker Unknown Error in process: %s %s" % (self.name, str(sys.exc_info()[0]), str(sys.exc_info()[1])))
    
    def subscribe(self, topic, callback):
        try:
            callbackArray = self._subscribers.get(str(topic))
            if(callbackArray):
                try:
                    callbackArray.index(callback)
                except ValueError:
                    callbackArray.append(callback)
            else:
                self._subscribers[topic] = [callback]
            return 1
        except:
            return - 1
            
    
    def unsubscribe(self, topic, callback):
        try:
            callbackArray = self._subscribers.get(str(topic))
            if(callbackArray):
                try:
                    callbackArray.remove(callback)
                except ValueError:
                    pass
            else:
                if(callbackArray == []):
                    del self._subscribers[str(topic)]
            return 1
        except:
            return - 1
    
    def publish(self, datalists, address=None, log=1):
        i = 0
        try:
            address = address or self.address
            if(datalists and address):
                for datalist in datalists:
                    try:
                        if(log): data = self.__hexlify(datalist[1])
                        else: data = datalist[1]
                        if (self._publisher):
                            self._publisher.publishDataString(address, data , datalist[0], log)
                        else:
                            self.__publishDataString(address, data, datalist[0], log)
                        i = i + 1
                    except SocketError, msg:
                        self.sockInit = 0
                        if (self.debug):
                            print("%s Broker:: SocketError in publish: %s" % (self.name, str(msg)))
                    except:
                        self.sockInit = 0
                        print('%s Borker:: Unexpected error in publish. %s %s' % (self.name, str(sys.exc_info()[0]), str(sys.exc_info()[1])))
        except:
            self.sockInit = 0
            pass
        return i
    
    def ping(self):
        try:
            self.__publishDataString(self.address, '00000000', 0, 0)
            return 1
        except:
            return - 1
    
    def cleanUp(self):
        try:
            self.__closeSocket()
            self.sock = None
            return 1
        except:
            return - 1
        
    def __hexlify(self, data):
        a = []
        for x in data:
            a.append("%02X" % (ord(x)))
        return ''.join(a)
    
    def __unhexelify(self, data):
        a = []
        for i in range(0, len(data), 2):
            a.append(chr(int(data[i:i + 2], 16)))   
        return ''.join(a) 
        
    def __processDataLogs(self):
        try:
            if(self.dataLogger):
                if (self.debug):
                    print("%s Broker: Processing data logs..." % self.name)
                datalist = self.dataLogger.getRecords(10)
                i = 0
                if(datalist):
                    for data in datalist:
                        if ((data.find('<?xml version="1.0"?>') < 0 and self._publisher) or (data.find('<?xml version="1.0"?>') >= 0 and not self._publisher)):
                            if(not self.publish([[None, data.strip()]], None, 0)):
                                break
                        i = i + 1
                else:
                    if (self.debug):
                        print("%s Broker: No data logs to process..." % self.name)            
                if(i > 0):
                    if (self.debug):
                        print("%s Broker: %d data logs sent to server..." % (self.name, i))
                    resp = self.dataLogger.deleteRecords(i) 
                    if (self.debug):
                        if(resp == 1):
                            print("%s Broker: Deleted %d data logs sent to server." % (self.name, i))
                        else:
                            print("%s Broker: Error deleting %d data logs sent to server." % (self.name, i))
        except:
            if (self.debug):
                print('%s Borker:: Unexpected error in processing data logs. %s %s' % (self.name, str(sys.exc_info()[0]), str(sys.exc_info()[1])))
            
    
    def __publishDataString(self, address, data, time=None, log=1):
        if(log):
            if(not time):
                time = time.getTimeAndOffset()
            data = '<?xml version="1.0"?><datas>' + "<data_node><manufacturer>" + manufacturer + "</manufacturer><data>" + data + "</data>" + \
            "<id>" + address + "</id><time>" + time[0] + "</time><offset>" + time[1] + "</offset></data_node>" + '</datas>'
        if(log or log is None):
            data = '%08d' % (len(data)) + data
        try:
            self.__initSock()
            self.sock.sendall(data)
            if (self.debug):
                print("%s Broker: TCP data sent: %s" % (self.name, data))
        except Exception, e:
            if(log and self.dataLogger):
                self.dataLogger.write(data) 
                if (self.debug):
                    print("%s Broker: TCP publisher data send failed. Logged it." % self.name)
            if(e.__class__.__name__ == 'SocketError'):
                raise SocketError(str(e))
            else:
                raise Exception(str(e))
    
    def __initSock(self):
        t = time.time()
        if (self.sockInit is 0 and self._nextConnTry - t > 0): raise SocketError('Last connection failed. Waiting before retry.')
        if (self.sockInit is 0 and self._nextConnTry - t <= 0):
            self._nextConnTry = t + 90
            if(self.sock is not None):
                if (self.debug):
                    print('%s Broker: Closing socket...' % self.name)
                self.__closeSocket()
            if (self.debug):
                print('%s Broker: Connecting to %s:%s' % (self.name, self.tcpAddr[0], str(self.tcpAddr[1])))
            self.sock = Socket(10, self.keepAlive)
            self.sock.connect((self.tcpAddr[0], self.tcpAddr[1]))
            self.sockInit = 1
            if (self.debug):
                print('%s Broker: Connected to %s:%s' % (self.name, self.tcpAddr[0], str(self.tcpAddr[1])))
            self.__registerDevice()
    
    def __registerDevice(self):
        if (self.debug):
            print('%s Broker: Registering device.' % self.name)
        msg = '<?xml version="1.0"?><datas><data_node><manufacturer>%s</manufacturer><id>%s</id><data></data></data_node></datas>' %(manufacturer,self.address)
        self.__publishDataString(self.address, msg, None, None)
    
    def __receive(self):
        packet = ''
        try:
            headerSize = int(self.__recvNBytes(8))
        except ValueError:
            headerSize = 0
        if (headerSize != 0):
            packet = self.__recvNBytes(headerSize)
        if (packet != '' and len(self._subscribers) > 0 and len(packet) == headerSize):
            if (self.debug):
                print('Broker:: Received data:%s' % packet)
            self.__processSubscribers(packet) 
        
    def __recvNBytes(self, n):
        try:
            packet = []
            packet_size = 0
            data_block = ''
            while(packet_size < n):
                if(self.sock is not None):
                    data_block = self.sock.recv(n - packet_size)
                if not data_block:
                    break
                packet.append(data_block)
                packet_size = packet_size + len(data_block)
            packet = ''.join(packet)
            return packet
        except SocketTimeoutError:
            pass
    
    def __processSubscribers(self, packet):
        try:
            p = packet.split('/')
            host = p[0]
            topic = p[1] + '/' + p[2]
            data='/'.join(p[3:])
            data = self.__unhexelify(data)
            if (self.debug):
                print('Broker: Processing data %s for topic: %s' % (data, topic))
            callbackArray = self._subscribers.get(topic)
            if(callbackArray):
                for callback in callbackArray:
                    try:
                        callback(data)
                    except:
                        pass
        except Exception, e:
            if (self.debug):
                print('%s Borker:: Unexpected error in processing callbacks. %s %s' % (self.name, str(sys.exc_info()[0]), str(sys.exc_info()[1])))
    
    def __closeSocket(self):
        try:
            if(self.sock):
                self.sock.close()
                self.sock = None
        except:
            pass
        
 
class HTTPPublisher:
        
    def __init__(self, name, addr, url, logger=None):
        self._name = name
        self._addr = addr
        self._url = url
        self._dataLogger = logger
        self._sock = None
        self.__checkSettings()
    
    def publishDataString(self, address, data, time=None, log=1):
        try:
            if(log):
                if(not time):
                    time = time.getTimeAndOffset()
                data = self._url + self.__formatData(address, data, time)
            try:
                self._sock = Socket(30, 0)
#                self._sock.connect((self._addr[0], self._addr[1]))
#                self._sock.sendall("GET %s HTTP/1.0\r\nHost: %s\r\nUser-agent: ioEYE Connect\r\nConnection: close\r\n\r\n" % (data, self._addr[0]))
                self._sock.getHTTP(self._addr,data)
                if (self.debug):
                    print("%s HTTPPublisher:: HTTP data sent: %s" % (self._name, data))
            except Exception, e:
                if(log and self._dataLogger): 
                    self._dataLogger.write(data) 
                    if (self.debug):
                        print("%s HTTPPublisher:: Unable to send data to server. Logged it." % self._name) 
                raise Exception(str(e))
        finally:
            try:
                if(self._sock):
                    self._sock.close()
                    self._sock = None
            except:
                pass
                
    def __formatData(self, address, data, time):
        return "?data=" + data + "&device_serial_number=" + \
            address + "&manufacturer=" + manufacturer + "&time=" + time[0] + "&offset=" + time[1]
            
    def __checkSettings(self):
        if (not self._addr[0] and not self._addr[1]):
            raise ValueError("HTTPPublisher:: Not a valid HTTP host or port value: %s, %d" % (self._addr[0], self._addr[1]))

####Socket class ###############################################################################
class Socket:
    maxconn = 6
    connected = 0
    accepting = 0
    closing = 0
    addr = None
    socketStates = {}
    socketStates[0] = "Socket Closed."
    socketStates[1] = "Socket with an active data transfer connection."
    socketStates[2] = "Socket suspended."
    socketStates[3] = "Socket suspended with pending data."
    socketStates[4] = "Socket listening."
    socketStates[5] = "Socket with an incoming connection. Waiting for the accept or shutdown command."
    
    def __init__(self, timeout, keepAlive=10):
        self._timeout = timeout or 10  # sec
        self._keepAlive = keepAlive 
        self._listenAutoRsp = 0
        self._sockno = None
        self.connected = 0
            
    def __get_socketno(self):
        sockStates = at.socketStatus()
        for sockState in sockStates:
            ss = sockState.split(',')
            if ss[1] == '0':
                return int(ss[0])
        return None
    
    def __configureSocket(self):
        try:
            self._sockno = self.__get_socketno()
            if(self._sockno):
                at.configureSocket(connId=self._sockno, pktSz=512, connTo=self._timeout * 10, keepAlive=self._keepAlive, listenAutoRsp=self._listenAutoRsp)
            else:
                raise SocketMaxCountError('Socket::All sockets in use. Total number of socket cannot exceed %d.' % self.maxconn)
        except:
            raise SocketConfigError('Socket::Unable to configure socket')
        
    def __socketStatus(self):
        return int(at.socketStatus(self._sockno).split(',')[1])
    
    def connect(self, addr):
        try:
            at.initGPRSConnection()
            self.addr = addr
            self.__configureSocket()
            at.connectSocket(self._sockno, addr, timeout=self._timeout + 3)
            self.connected = 1
        except(SocketMaxCountError, SocketConfigError), msg:
            raise SocketError(str(msg))
        except:
            raise SocketError('Socket::Unable to connect to remote host %s' % str(addr))
        
    def listen(self, addr):
# Telit module only allows one connection at a time on a listening socket.
        try:
            at.initGPRSConnection()
            self.addr = addr
            self._listenAutoRsp = 1
            self.__configureSocket()
            at.socketListen(self._sockno, 1, addr(1), timeout=self._timeout + 3)
            self.connected = 1
            self.accepting = 1
        except(SocketMaxCountError, SocketConfigError), msg:
            raise SocketError(str(msg))
        except:
            raise SocketError('Unable to bind to %s .' % str(addr))
        
    def getHTTP(self, addr, data):
        try:
            at.initGPRSConnection()
            self.__configureSocket()
            data = "GET %s HTTP/1.0\r\nHost: %s\r\nUser-agent: ioEYE Connect\r\nConnection: close\r\n\r\n" % (data, addr[0])
            at.socketGetHTTP(self._sockno, addr, data, self._timeout)
        except(SocketMaxCountError, SocketConfigError), msg:
            raise SocketError(str(msg))
        except at.timeout:
            raise SocketTimeoutError('Socket:: HTTP Get Timed out.')
        except:
            raise SocketError('Socket::Error in HTTP Get.')
    
    def accept(self):
        try:
            at.socketAccept(self._sockno)
        except:
            raise SocketError('Socket:: Error in connection accept.')  
                     
    def close(self):
        try:
            if(self.__socketStatus() == 0):return
            if(self.accepting):
                at.socketListen(self._sockno, 0, self.addr[1], self._timeout) 
                self.accepting = 0   
            at.closeSocket(self._sockno)
            self.connected = 0
        except:
            raise SocketError('Socket::Unable to close socket %d' % self._sockno)
  
    def recv(self, bufsize):
        try:
            ss = self.__socketStatus()
            if(not ss):raise SocketError(self.socketStates[ss])
            if(ss == 3):
                if(bufsize > 1500 or bufsize < 0):bufsize = 1500
                return at.socketRecv(self._sockno, bufsize, self._timeout + 3)
            else:
                return ''
        except at.timeout:
            raise SocketTimeoutError('Socket:: Timed out.')
        except:
            raise SocketError('Socket::Error in recv data.')

    def send(self, data):
        try:
            ss = self.__socketStatus()
            if(not ss):raise SocketError(self.socketStates[ss])
            data = data[:1500]
            return at.socketSend(self._sockno, data, len(data), self._timeout + 3, 0)
        except at.timeout:
            raise SocketTimeoutError('Socket:: Timed out.')
        except:
            raise SocketError('Socket::Error in send data.')
                 
    def sendall(self, data):
        try:
            ss = self.__socketStatus()
            if(not ss):raise SocketError(self.socketStates[ss])
            i = 0
            while(data):
                partData = data[:1500]
                sendDataSize = at.socketSend(self._sockno, partData, len(partData), self._timeout + 3, i)
                data = data[sendDataSize:]
                i = i + 1
        except at.timeout:
            raise SocketTimeoutError('Socket:: Timed out.')
        except:
            raise SocketError('Socket::Error in sendall data.')  


#####Logger and file ###########################################################################  

class Logger:
    def __init__(self, handler, uploadInterval=300):
        self.handler = handler
        self.uploadInterval = uploadInterval
        self._nextUploadTime = time.time()
    
    def write(self, msg):
        if(msg and msg not in ('\n', '\r\n')):
            self.handler.log(msg)
    
    def cleanUp(self):
        try:
            self.handler.close()
        except:
            pass
    
    def getRecords(self, number, start=0):
        return self.handler.getRecords(number, start)
    
    def deleteRecords(self, number, start=0):
        return self.handler.deleteRecords(number, start)
    
    def shouldUpload(self):
        t = time.time()
        if(self._nextUploadTime - t < 0):
            self._nextUploadTime = t + self.uploadInterval
            return 1
        return 0

class SerialHandler:
    def __init__(self):
        import SER
        SER.set_speed('115200', '8N1')
    
    def log(self, msg):
        SER.send(msg + '\r\n')
        
    def close(self):
        pass
    
    def getRecords(self, number, start=0):
        return []
    
    def deleteRecords(self, number, start=0):
        return []
    
class FileHandler:
    
    def __init__(self, filename, maxBytes, timeStamp=1, rotate=1):
        self.maxBytes = maxBytes
        self.timeStamp = timeStamp
        self.baseFilename = filename
        self.rotate = rotate
        self.mode = 'ab'
        self.file = None
        
    def log(self, msg):
        try:
            if self.file is None:
                self.__open(self.mode)
            if(self.timeStamp):
                msg = "%s- %s\r\n" % (time.asctime(), msg)
            else:
                msg = "%s\r\n" % (msg)
            if self.__shouldRollover(msg):
                if(self.rotate):
                    self.__doRollover()
                else:
                    self.__doFifoRollover(msg)
            if(self.file):
                self.file.write(msg)
                self.file.flush()
        except IOError:
            if(self.file):
                self.close()
                self.file = None
        except:
            pass
    
    def getRecords(self, number, start=0):
        try:
            try:
                lines = []
                if(self.file):
                    self.close()
                self.file = self.__open('rb')
                lines = self.file.readlines()
                self.close()
                lines = lines[start:(start + number)]
                return lines
            except:
                lines = []
        finally:
            self.close()
            return lines
    
    def deleteRecords(self, number, start=0):
        try:
            try:
                success = -1
                if(self.file):
                    self.close()
                self.file = self.__open('rb')
                lines = self.file.readlines()
                self.close()
                self.file = self.__open('wb')
                lines = lines[0:start] + lines[(start + number):]
                self.file.writelines(lines)
                self.file.flush()
                self.close()
                self.file = None
                success = 1
            except:
                pass
        finally:
            self.close()
            return success
    
    def close(self):
        try:
            if(self.file):
                self.file.close()
            self.file = None
        except:
            pass
        
    def __shouldRollover(self, msg):
        if(self.file):
            if (self.__file_size() + len(msg) >= self.maxBytes):
                return 1 
        return 0

    def __doRollover(self):
        if(self.file):
            self.close()
            self.file = self.__open('wb')
            
    def __doFifoRollover(self, msg):
        try:
            if(self.file):
                fileSize = self.__file_size()
                lenMsg = len(msg)
                self.close()
                self.file = self.__open('rb')
                lines = self.file.readlines()
                while(fileSize + lenMsg >= self.maxBytes):
                    fileSize = fileSize - len(lines[0])
                    lines.pop(0)
                lines.append(msg)
                self.close()
                self.file = self.__open('wb')
                self.file.writelines(lines)
                self.file.flush()
                self.close()
                self.file = None
        except:
            self.close()
            
    def __open(self, mode):
        self.file = open(self.baseFilename, mode)
        return self.file
    
    def __file_size(self):
        self.file.seek(0, 2)
        return self.file.tell()

#####Time##################################################################################  
class Time:

    def __init__(self):
        self.error = TimeError;
             
    def time(self):
        try:
            return MOD.secCounter()
        except Exception, e:
            raise self.error('Time:: Unable to get time. %s' % repr(e))
        
    def asctime(self):
        try:
            return at.getRtcTime()
        except Exception, e:
            raise self.error('Time:: Unable to get time. %s' % repr(e))    
    
    def sleep(self, sec):
        MOD.sleep(int(sec) * 10)
        
    def getTimeAndOffset(self):
        try:
            t = self.asctime(self)
            now = self.localtime(self, t)
            timestr = "%04d%02d%02d%01d%02d%02d%02d" % (now[0], now[1], (now[2]), (now[6]), now[3], now[4], now[5])
            offset = str(self.__getOffset(t))
            return [timestr, offset]
        except Exception, e:
            raise self.error('Time:: Unable to parse time.')
        
    def localtime(self, time=None):
        if(time is None):
            time = self.asctime(self)
        t = time[0:-3].split(',')
        date = map(int, t[0].split('/'))
        time = map(int, t[1].split(':'))
        date[0] = date[0] + 2000
        time.append(self.weekDay(self, date)[0])
        return (date + time)
    
    def weekDay(self, date):
        year = date[0]
        month = date[1]
        day = date[2]
        offset = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
        week = {0:'Sunday',
                  1:'Monday',
                  2:'Tuesday',
                  3:'Wednesday',
                  4:'Thursday',
                  5:'Friday',
                  6:'Saturday'}
        afterFeb = 1
        if month > 2: afterFeb = 0
        aux = year - 1700 - afterFeb
        # dayOfWeek for 1700/1/1 = 5, Friday
        dayOfWeek = 5
        # partial sum of days betweem current date and 1700/1/1
        dayOfWeek = dayOfWeek + (aux + afterFeb) * 365                  
        # leap year correction    
        dayOfWeek = dayOfWeek + aux / 4 - aux / 100 + (aux + 100) / 400     
        # sum monthly and day offsets
        dayOfWeek = dayOfWeek + offset[month - 1] + (day - 1) 
        dayOfWeek = dayOfWeek % 7
        return dayOfWeek, week[dayOfWeek]
    
    def __getOffset(self, time):
        offset = int(time[-3:]) * 15 * 60
        return offset

#####AT Functions#########################################################################
class At:
    def __init__(self):
        self.timeout = ATTimeoutError
        self.error = ATError
        self.modem = {
             'imei':'',
             'model':'',
             'state':0,
             'firmware':'',
             'signal_quality':'',
             'power_mode':'',
             'subscriber_number':''
             }
    
    def getModem(self):
        return self.modem
        
    def sendCmd(self, cmd, timeOut=2, expected='OK\r\n', addCR=1, mdm=1):
        try:
            if(mdm == 2):
                mdm = MDM2
            else:
                mdm = MDM
            if (timeOut <= 0): timeOut = 2
            if (addCR == 1):
                r = mdm.send(cmd + '\r', 5)
            else:
                r = mdm.send(cmd, 5)
            if (r < 0):
                raise self.timeout('Send "%s" timed out.' % cmd)
            timer = MOD.secCounter() + timeOut
            response = cmd + mdm.read()
            while (timeOut > 0 and (not expected or response.find(expected) == -1)):
                response = response + mdm.read()
                timeOut = timer - MOD.secCounter()
            if(response.find(expected) == -1):
                if (timeOut > 0):
                    raise self.error('Expected response "%s" not received.' % expected.strip())
                else:
                    raise self.timeout('Receive timed out.')
            if(response.find('ERROR') > 0):
                raise self.error('ERROR response received for "%s".' % cmd) 
            else:
                return response
        except self.error, e:
            raise self.error(str(e))
        except self.timeout, e:
            raise self.timeout(str(e))
        except Exception, e:
            print("AtCmdError: %s" % str(sys.exc_info()[1]))
            raise self.error("UnexpectedError, command %s failed." % cmd)
    
    # Module AT commands

    def initModem(self, config, retry=20):
        try:
            if(retry <= 0): retry = 1
            self.modem['state'] = 0
            self.modem['model'] = self.getModel()
            self.modem['imei'] = self.getIMEI()
            self.modem['firmware'] = self.getFirmwareVersion()
            self.modem['signal_quality'] = self.getSignalQuality()
            self.modem['power_mode'] = self.getPowerMode()
            self.modem['subscriber_number'] = self.subscriberNumber()
            self.modem['antenna_status'] = self.getAntennaStatus()
            if (config['debug']):
                print('AT:: Checking and initializing SIM...')
            if(not self.initSimDetect(config['sim_detection_mode'], retry)): return 0
            if (config['debug']):
                print('AT:: SIM Detected.')
            if(not self.initPin(config['sim_pin'], retry)): return 0
            if (config['debug']):
                print('AT:: SIM OK.')
            if (config['debug']):
                print('AT:: Checking and initializing Network...')
            if(not self.initNetwork(retry)): return 0
            if (config['debug']):
                print('AT:: Network OK.')
            if (config['debug']):
                print('AT:: Checking and initializing GPRS settings...')
            if(not self.initGPRS(1, config['gprs_apn'], config['gprs_userid'], config['gprs_pswd'], retry)): return 0
            if (config['debug']):
                print('AT:: GPRS Settings OK.')
            if (config['debug']):
                print('AT:: Modem OK.')
            self.modem['state'] = 1
            return self.modem
        except:
            self.modem['state'] = 0
            return self.modem
        
    def reboot(self):
        try:
            self.sendCmd('AT#REBOOT')
            return 1
        except:
            return 0
        
    def factoryReset(self):
        try:
            self.sendCmd('AT&F')
            return 1
        except:
            return 0
        
    def getModel(self):
        try:
            return self.sendCmd('AT+GMM', 1).split('\r\n')[1]
        except:
            return ''
    
    def getFirmwareVersion(self):
        try:
            return self.sendCmd('AT+GMR', 1).split('\r\n')[1]
        except:
            return ''
    
    def getSignalQuality(self):
        try:
            return self.sendCmd('AT+CSQ', 1).split('\r\n')[1].replace('+CSQ: ', '').split(',')
        except:
            return []
        
    def subscriberNumber(self):
        try:
            return self.sendCmd('AT+CNUM', 1).split('\r\n')[1].replace('+CNUM: ', '').split(',')
        except:
            return []
    # Python Script AT commands
    
    def setTemperatureMonitor(self, mode, urcmode=1, action=1, hysteresis=255, gpio=None):
    #    parameters: (0,1),(0,1),(0-7),(0-255),(1-8)
        try:
            cmd = 'AT#TEMPMON=%d,%d,%d,%d' % (mode, urcmode, action, hysteresis)
            if(gpio): cmd = cmd + ',%d' % gpio
            self.sendCmd(cmd)
            return mode
        except:
            return -1
    
    def getTemperature(self):
        try:
            return self.sendCmd('AT#TEMPMON=1').split('\r\n')[1].replace('#TEMPMEAS: ', '').split(',')
        except:
            return ''
    
    def setFlowControl(self, value=0):
        try:
            resp = self.sendCmd('AT&K?')
            if(resp.find('00%d' % value) < 0):
                resp = self.sendCmd('AT&K=%d' % value)
            return 1
        except:
            return -1
        
    def setCmux(self, mode=0, baudrate=9600):
        try:
            resp = self.sendCmd('AT#CMUXSCR?')
            if(resp.find('#CMUXSCR: %d' % mode) < 0 or resp.find('#CMUXSCR: %d,%d' % (mode, baudrate)) < 0):
                resp = self.sendCmd('AT#CMUXSCR=%d,%d' % (mode, baudrate))
            return 1
        except:
            return -1
        
    def getAntennaStatus(self):
    # 0 - antenna connected.
    # 1 - antenna connector short circuited to ground.
    # 2 - antenna connector short circuited to power.
    # 3 - antenna not detected (open).
        try:
            return int(self.sendCmd('AT#GSMAD=3', 10).split('\r\n')[1].split(':')[1])
        except:
            return -1
    
    def getActiveScript(self):
        return self.sendCmd('AT#ESCRIPT?', 1).replace('#ESCRIPT: ', '').replace('"', '')
        
    def getfilelist(self):
        return self.sendCmd('AT#LSCRIPT', 1).replace('#LSCRIPT: ', '').replace('"', '').split('\r\n')
    
    # Time AT commands
    
    def getRtcTime(self):
        return self.sendCmd('AT+CCLK?', 1).split('\r\n')[1].split('"')[1]
    
    def setRtcTime(self, time):
    # time in "yy/MM/dd,hh:mm:ss±zz"
    # zz is time zone (indicates the difference, expressed in quarter of an hour, 
    # between the local time and GMT; two last digits are mandatory), range is -47..+48
        return self.sendCmd('AT+CCLK = "%s"' % time)
    
    def setDateFormat(self, mode=1, auxmode=1):
        return self.sendCmd('AT+CSDF=%d,%d' % (mode, auxmode))
    
    def setAutoTimeZoneUpdateFromNetwork(self, value=1):
        resp = self.sendCmd('AT+CTZU?')
        if(resp.find('+CTZU: %d' % value) < 0):
            resp = self.sendCmd('AT+CTZU=%d' % value)
        return resp
    
    def setAutoDateTimeUpdateFromNetwork(self, value=7, mode=0):
        resp = self.sendCmd('AT#NITZ?')
        if(resp.find('#NITZ: %d,%d' % (value, mode)) < 0):
            resp = self.sendCmd('AT#NITZ=%d,%d' % (value, mode))
        return resp
    
    def setNtpSever(self, ip='ntp.ioeye.com', port=123):
        resp = self.sendCmd('AT#NTP?')
        if(resp.find('#NTP="%s",%d,%d,%d' % (ip, port, 1, 5)) < 0):
            resp = self.sendCmd('AT#NTP="%s",%d,%d,%d' % (ip, port, 1, 5))
        return resp
    
    def setPowerMode(self, mode=1):
    # 0 - minimum functionality, NON-CYCLIC SLEEP mode: in this mode, the AT interface is not accessible. Consequently, once you have set <fun> level 0, do not send further characters. Otherwise these characters remain in the input buffer and may delay the output of an unsolicited result code. The first wake-up event, or rising RTS line, stops power saving and takes the ME back to full functionality level <fun>=1.
    # 1 - mobile full functionality with power saving disabled (factory default)
    # 2 - disable TX
    # 4 - disable either TX and RX
    # 5 - mobile full functionality with power saving enabled
        resp = self.getPowerMode(self)
        if(resp != mode):
            return self.sendCmd('AT+CFUN= %d' % (mode))  
        return resp
    
    def setInterfaceStyle(self):
        if(self.sendCmd('AT#SELINT?', 1).find('AT#SELINT: 2') > 0): return 1
        else:self.sendCmd('AT#SELINT=2', 1)
    
    def getPowerMode(self):
        return int(self.sendCmd('AT+CFUN?').split('\r\n')[1].split(':')[1])
    
    def getBatteryStatus(self):
        return self.sendCmd('AT+CBC').split('\r\n')[1].replace('+CBC: ', '').split(',')
    
    def getFireWallSettings(self):
        return self.sendCmd('AT#FRWL?')
    
    def addToFireWall(self, ip, subnet):
        cmdValue = 'AT#FRWL=1,"%s","%s"' % (ip, subnet)
        return self.sendCmd(cmdValue)
    
    def removeFromFireWall(self, ip, subnet):
        cmdValue = 'AT#FRWL=0,"%s","%s"' % (ip, subnet)
        return self.sendCmd(cmdValue)
    
    def dropAllFireWallRules(self):
        return self.sendCmd('AT#FRWL=2')
    
    def getIMEI(self, retry=20):
        imei = ''
        if(retry <= 0): retry = 1
        while (retry > 0):
            retry = retry - 1
            try:
                imei = self.sendCmd('AT+CGSN').split('\r\n')[1]
                if(imei): break
                MOD.sleep(50)
            except:
                MOD.sleep(50)
                continue
        return imei
    
    def initSimDetect(self, simDetectMode='', retry=20):  
        if simDetectMode < 0 or simDetectMode > 2: return 0
        success = 0
        if(retry <= 0): retry = 1
        while (retry > 0):
            retry = retry - 1
            try:
                response = self.sendCmd('AT#SIMDET?', 5)
                if (response.find(str(simDetectMode) + ',') > 0):
                    success = 1
                    break
                else:
                    self.sendCmd('AT#SIMDET=' + str(simDetectMode) , 5)
                    success = 1
                    break
                MOD.sleep(50)
            except:
                MOD.sleep(50)
                continue
        return success
    
    def initPin(self, pin='', retry=20):  
        success = 0
        if(retry <= 0): retry = 1
        while (retry > 0):
            retry = retry - 1
            try:
                response = self.sendCmd('AT+CPIN?', 5)
                if (response.find('READY') > 0):
                    success = 1
                    break
                if (response.find('SIM PIN') > 0):
                    self.sendCmd('AT+CPIN=' + pin, 5)
                    success = 1
                    break
                MOD.sleep(50)
            except:
                MOD.sleep(50)
                continue
        return success
    
    def initNetwork(self, retry=20):
        success = 0
        if(retry <= 0): retry = 1
        while (retry > 0):
            retry = retry - 1
            try:
                response = self.sendCmd('AT+CREG?', 5)
                if (response.find('0,1') > 0 or response.find('0,5') > 0):
                    success = 1
                    break
                MOD.sleep(50)
            except:
                MOD.sleep(50)
                continue
        return success  
    
    def initGPRS(self, pdpContextId=1, apn='', userid='', passw='', retry=20):
        success = 0
        if(retry <= 0): retry = 1
        while (retry > 0):
            retry = retry - 1
            try:
                gprs = self.sendCmd('AT+CGDCONT?;#USERID?', 1)
                if(gprs.find('%d,"IP","%s"' % (pdpContextId, apn)) < 0 or gprs.find('#USERID: "%s"' % userid) < 0):
                    self.sendCmd('AT+CGDCONT=%d,"IP","%s";#USERID="%s";#PASSW="%s"' % (pdpContextId, apn, userid, passw))    
                self.sendCmd('AT+CGATT?', 5, '+CGATT: 1')
                self.setGPRSContextConfig()
                success = 1
                break
            except:
                MOD.sleep(10)
                continue
        return success  
    
    def activateGPRSContext(self, pdpContextId=1, retry=20):
    # "Activates the GPRS context for internet."
        success = 0
        if(pdpContextId > 5 or pdpContextId < 1): return 0
        if(retry <= 0): retry = 1
        while (retry > 0):
            retry = retry - 1
            try:
                self.sendCmd('AT#SGACT=%d,1' % pdpContextId, 1, 'IP')
                success = 1
                break
            except:
                MOD.sleep(10)
                continue
        return success  
    
    def deactivateGPRSContext(self, pdpContextId=1, retry=20):
    # "Activates the GPRS context for internet."
        success = 0
        if(pdpContextId > 5 or pdpContextId < 1): return 0
        if(retry <= 0): retry = 1
        while (retry > 0):
            retry = retry - 1
            try:
                self.sendCmd('AT#SGACT=%d,0' % pdpContextId, 1)
                success = 1
                break
            except:
                MOD.sleep(10)
                continue
        return success 
    
    def setGPRSAutoAttach(self, value=1):
        resp = self.sendCmd('AT#AUTOATT?')
        if(resp.find('#AUTOATT: %d' % value) < 0):
            cmdValue = 'AT#AUTOATT=%d' % value
            resp = self.sendCmd(cmdValue)
        return resp
    
    def getGPRSContextStatus(self, pdpContextId=1, retry=5):  
        status = 0
        if(retry <= 0): retry = 1
        while (retry > 0):
            retry = retry - 1
            try:
                if(self.sendCmd('AT#SGACT?', 1).find('#SGACT: %d,1' % pdpContextId) > 0): status = 1
                break
            except:
                MOD.sleep(10)
                continue
        return status  
    
    def initGPRSConnection(self, pdpContextId=1, retry=20, drop=0, debug=0):
    # Set drop=1 if you want to drop existing GPRS context create new one.
        try:
            if (debug):
                print('AT:: Checking and initializing GPRS connection...')
            status = 0
            if(retry <= 0): retry = 1
            status = self.getGPRSContextStatus(pdpContextId, 1)
            while((status in (0, 2) or drop) and retry > 0):
                retry = retry - 1
                if(status == 0):
                    self.activateGPRSContext(1)
                elif(status == 1 and drop == 1):
                    self.deactivateGPRSContext(pdpContextId, 1)
                    self.activateGPRSContext(pdpContextId, 1)
                elif(status == 2):
                    MOD.sleep(10)
                drop = 0
                status = self.getGPRSContextStatus(pdpContextId, 1)
            if (debug):
                if(status):
                    print('AT:: GPRS OK.')
                else:
                    print('AT:: Unable to initialize GPRS connection.')
            return status
        except:
            if (debug):
                print('AT:: UnexpectedErorr. Unable to initialize GPRS connection.')
            return 0
        
    def setGPRSContextConfig(self, pdpContextId=1, retry=15, delay=180):
        self.sendCmd('AT#SGACTCFG=%d,%d,%d' % (pdpContextId, retry, delay))
         
    def configureSocket(self, connId, cid=1, pktSz=512, maxTo=0, connTo=600, txTo=50, keepAlive=0, listenAutoRsp=0):
    # connId(1-6),cid(0-5),pktSz(0-1500),maxTo(0-65535),connTo(10-1200),txTo(0-255)
    # keepAlive(0 – 240)min
        self.sendCmd('AT#SCFG=%d,%d,%d,%d,%d,%d' % (connId, cid, pktSz, maxTo, connTo, txTo))
        self.sendCmd('AT#SCFGEXT= %d,0,0,%d,%d' % (connId, keepAlive, listenAutoRsp))
            
    def connectSocket(self, connId, addr, proto=0, closureType=0, IPort=0, timeout=60):
        connMode = 1  # always connect in command mode
        self.sendCmd('AT#SD=%d,%d,%d,"%s",%d,%d,%d' % (connId, proto, addr[1], addr[0], closureType, IPort, connMode), timeout)
    
    def closeSocket(self, connId, timeout):
        self.sendCmd('AT#SH=%d' % connId, timeout)
    
    def socketRecv(self, connId, maxByte, timeout):
        return self.sendCmd('AT#SRECV=%d,%d' % (connId, maxByte), timeout).split('\r\n')[2]
    
    def socketSend(self, connId, data, bytestosend, timeout, multiPart=0):
    # bytestosend(1-1500)
        if(multiPart == 0):
            self.sendCmd('AT#SSENDEXT=%d,%d' % (connId, bytestosend), 1, '')
        self.sendCmd(data, timeout, expected='OK\r\n', addCR=0)
        return bytestosend
    
    def socketGetHTTP(self, connId, addr, data, timeout=30):
        try:
            resp = self.sendCmd('AT#SD=%d,0,%d,"%s",0,0,0' % (connId, addr[1], addr[0]), timeout, expected='CONNECT\r\n', mdm=2)
            resp = self.sendCmd(data, timeout, expected='HTTP/1.1 200 OK', addCR=0, mdm=2)
        finally:
            resp = self.sendCmd('+++', timeout, expected='NO CARRIER\r\n', addCR=0, mdm=2)
        
    def socketStatus(self, connId=None):
        if(connId):
            return self.sendCmd('AT#SS', mdm=2).split('\r\n')[connId].replace('#SS: ', '')
        else:
            return self.sendCmd('AT#SS', mdm=2).replace('#SS: ', '').split('\r\n')[1:6]
    
    def suspendSocket(self):   
        self.sendCmd('+++')
        MOD.sleep(20)
    
    def resumeSocket(self, connId):
        self.sendCmd('AT#SO=' % connId)
    
    def socketInfo(self, connId):
        return self.sendCmd('AT#SI=' % connId).split('\r\n')[1].replace('#SI: ', '').split(',')
    
    def socketListen(self, connId, listenState, listenPort, closureType=0, timeout=60):
        self.sendCmd('AT#SL=%d,%d,%d,%d' % (connId, listenState, listenPort, closureType), timeout)
    
    def socketAccept(self, connId, connMode=1):
        self.sendCmd('AT#SA=%d,%d' % (connId, connMode))
    
    def socketBase64(self, connId, enc, dec):
        self.sendCmd('#AT#BASE64=%d,%d,%d' % (connId, enc, dec))


#####Exceptions######################################################################## 
    
class Exception:
    def __init__(self, *args):
        self.args = args

    def __str__(self):
        if not self.args:
            return ''
        elif len(self.args) == 1:
            return str(self.args[0])
        else:
            return str(self.args)

    def __getitem__(self, i):
        return self.args[i]
    
class StandardError(Exception):
    pass

class SyntaxError(StandardError):
    filename = lineno = offset = text = None
    msg = ""
    def __init__(self, *args):
        self.args = args
        if len(self.args) >= 1:
            self.msg = self.args[0]
        if len(self.args) == 2:
            info = self.args[1]
            try:
                self.filename, self.lineno, self.offset, self.text = info
            except:
                pass
    def __str__(self):
        return str(self.msg)
    
class EnvironmentError(StandardError):
    def __init__(self, *args):
        self.args = args
        self.errno = None
        self.strerror = None
        self.filename = None
        if len(args) == 3:
            self.errno, self.strerror, self.filename = args
            self.args = args[0:2]
        if len(args) == 2:
            # common case: PyErr_SetFromErrno()
            self.errno, self.strerror = args

    def __str__(self):
        if self.filename is not None:
            return '[Errno %s] %s: %s' % (self.errno, self.strerror,
                                          repr(self.filename))
        elif self.errno and self.strerror:
            return '[Errno %s] %s' % (self.errno, self.strerror)
        else:
            return StandardError.__str__(self)

class IOError(EnvironmentError):
    pass

class OSError(EnvironmentError):
    pass

class RuntimeError(StandardError):
    pass

class NotImplementedError(RuntimeError):
    """Method or function hasn't been implemented yet."""
    pass

class RemovedFeatureError(RuntimeError):
    """Standard feature has been eliminated in this python build."""
    pass

class SystemError(StandardError):
    """Internal error in the Python interpreter.

    Please report this to the Python maintainer, along with the traceback,
    the Python version, and the hardware/OS platform and version."""
    pass

class EOFError(StandardError):
    """Read beyond end of file."""
    pass

class ImportError(StandardError):
    """Import can't find module, or can't find name in module."""
    pass

class TypeError(StandardError):
    """Inappropriate argument type."""
    pass

class ValueError(StandardError):
    """Inappropriate argument value (of correct type)."""
    pass

class AssertionError(StandardError):
    """Assertion failed."""
    pass

class ArithmeticError(StandardError):
    """Base class for arithmetic errors."""
    pass

class OverflowError(ArithmeticError):
    """Result too large to be represented."""
    pass

class FloatingPointError(ArithmeticError):
    """Floating point operation failed."""
    pass

class ZeroDivisionError(ArithmeticError):
    """Second argument to a division or modulo operation was zero."""
    pass

class LookupError(StandardError):
    """Base class for lookup errors."""
    pass

class IndexError(LookupError):
    """Sequence index out of range."""
    pass

class KeyError(LookupError):
    """Mapping key not found."""
    pass

class AttributeError(StandardError):
    """Attribute not found."""
    pass

class NameError(StandardError):
    """Name not found globally."""
    pass

class UnboundLocalError(NameError):
    """Local name referenced but not bound to a value."""
    pass

class MemoryError(StandardError):
    """Out of memory."""
    pass

class SystemExit(Exception):
    """Request to exit from the interpreter."""
    def __init__(self, *args):
        self.args = args
        if len(args) == 0:
            self.code = None
        elif len(args) == 1:
            self.code = args[0]
        else:
            self.code = args

class ATError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class ATTimeoutError(IOError):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class TimeError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class SocketError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class SocketTimeoutError(IOError):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class SocketMaxCountError(IOError):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class SocketConfigError(IOError):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
manufacturer = 'Telit'
at = instamsg.At()
time = instamsg.Time()
