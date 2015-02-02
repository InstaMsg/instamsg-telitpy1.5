# -*- coding: utf-8 -*-
import at
import exceptions

class SocketError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class SocketTimeoutError(exceptions.IOError):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class SocketMaxCountError(exceptions.IOError):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class SocketConfigError(exceptions.IOError):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
timeout= SocketTimeoutError
error = SocketError
configError = SocketConfigError
maxCountError = SocketMaxCountError

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