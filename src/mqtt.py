# -*- coding: utf-8 -*-
import socket
import time
import sys
import exceptions
import mqttcodec

MQTT_LOG_LEVEL_DISABLED = 0
MQTT_LOG_LEVEL_INFO = 1
MQTT_LOG_LEVEL_ERROR = 2
MQTT_LOG_LEVEL_DEBUG = 3

class MqttClient:
    MQTT_RESULT_HANDLER_TIMEOUT = 10
    MQTT_MAX_RESULT_HANDLER_TIMEOUT = 500
    MAX_BYTES_MDM_READ = 511  # Telit MDM read limit
    
    def __init__(self, host, port, clientId, options={}):
        if(not clientId):
            raise ValueError('clientId cannot be null.')
        if(not host):
            raise ValueError('host cannot be null.')
        if(not port):
            raise ValueError('port cannot be null.')
        self.host = host
        self.port = port
        self.clientId = clientId
        self.options = options
        self.options['clientId'] = clientId
        self.keepAliveTimer = self.options['keepAliveTimer']
        self.reconnectTimer = options['reconnectTimer']
        self.__logLevel = options.get('logLevel')
        self.__cleanSession = 1
        self.__sock = None
        self.__sockInit = 0
        self.__connected = 0
        self.__connecting = 0
        self.__disconnecting = 0
        self.__waitingReconnect = 0
        self.__nextConnTry = time.time()
        self.__nextPingReqTime = time.time()
        self.__lastPingRespTime = self.__nextPingReqTime
        self.__mqttMsgFactory = MqttMsgFactory()
        self.__mqttEncoder = MqttEncoder()
        self.__mqttDecoder = MqttDecoder()
        self.__messageId = 0
        self.__onDisconnectCallBack = None
        self.__onConnectCallBack = None
        self.__onMessageCallBack = None
        self.__onDebugMessageCallBack = None
        self.__msgIdInbox = []
        self.__resultHandlers = {}  # {handlerId:{time:122334,handler:replyHandler, timeout:10, timeOutMsg:"Timed out"}}
        
    def process(self):
        try:
            if(not self.__disconnecting):
                self.connect()
                if(self.__sockInit):
                    self.__receive()
                    if (self.__nextPingReqTime - time.time() <= 0):
                        if (self.__nextPingReqTime - self.__lastPingRespTime > self.keepAliveTimer):
                            self.disconnect()
                        else: self.__sendPingReq()
                self.__processHandlersTimeout()
        except socket.error, msg:
            self.__resetInitSockNConnect()
            self.__log(MQTT_LOG_LEVEL_DEBUG, "[MqttClientError, method = process][SocketError]:: %s" % (str(msg)))
        except:
            self.__log(MQTT_LOG_LEVEL_ERROR, "[MqttClientError, method = process][Exception]:: %s %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
    
    def connect(self):
        try:
            self.__initSock()
            if(self.__connecting is 0 and self.__sockInit):
                if(not self.__connected):
                    self.__connecting = 1
                    self.__log(MQTT_LOG_LEVEL_INFO, '[MqttClient]:: Connecting to %s:%s' % (self.host, str(self.port)))   
                    fixedHeader = MqttFixedHeader(mqttcodec.CONNECT, qos=0, dup=0, retain=0)
                    connectMsg = self.__mqttMsgFactory.message(fixedHeader, self.options, self.options)
                    encodedMsg = self.__mqttEncoder.ecode(connectMsg)
                    self.__sendall(encodedMsg)
        except socket.timeout:
            self.__connecting = 0
            self.__log(MQTT_LOG_LEVEL_DEBUG, "[MqttClientError, method = connect][SocketTimeoutError]:: Socket timed out")
        except socket.error, msg:
            self.__resetInitSockNConnect()
            self.__log(MQTT_LOG_LEVEL_DEBUG, "[MqttClientError, method = connect][SocketError]:: %s" % (str(msg)))
        except:
            self.__connecting = 0
            self.__log(MQTT_LOG_LEVEL_ERROR, "[MqttClientError, method = connect][Exception]:: %s %s" % (str(sys.exc_info()[0]), str(sys.exc_info()[1])))
    
    def disconnect(self):
        try:
            try:
                self.__disconnecting = 1
                if(not self.__connecting  and not self.__waitingReconnect and self.__sockInit):
                    fixedHeader = MqttFixedHeader(mqttcodec.DISCONNECT, qos=0, dup=0, retain=0)
                    disConnectMsg = self.__mqttMsgFactory.message(fixedHeader)
                    encodedMsg = self.__mqttEncoder.ecode(disConnectMsg)
                    self.__sendall(encodedMsg)
            except Exception, msg:
                self.__log(MQTT_LOG_LEVEL_DEBUG, "[MqttClientError, method = __receive][%s]:: %s" % (msg.__class__.__name__ , str(msg)))
        finally:
            self.__closeSocket()
            self.__resetInitSockNConnect()
    
    def publish(self, topic, payload, qos=MQTT_QOS0, dup=0, resultHandler=None, resultHandlerTimeout=MQTT_RESULT_HANDLER_TIMEOUT, retain=0):
        if(not self.__connected or self.__connecting  or self.__waitingReconnect):
            raise MqttClientError("Cannot publish message as not connected.")
        self.__validateTopic(topic)
        self.__validateQos(qos)
        self.__validateResultHandler(resultHandler)
        self.__validateTimeout(resultHandlerTimeout)
        fixedHeader = MqttFixedHeader(self.PUBLISH, qos=mqttcodec.MQTT_QOS0, dup=0, retain=0)
        messageId = 0
        if(qos > mqttcodec.MQTT_QOS0): messageId = self.__generateMessageId()
        variableHeader = {'messageId': messageId, 'topic': str(topic)}
        publishMsg = self.__mqttMsgFactory.message(fixedHeader, variableHeader, payload)
        encodedMsg = self.__mqttEncoder.ecode(publishMsg)
        self.__sendall(encodedMsg)
        self.__validateResultHandler(resultHandler)
        if(qos == mqttcodec.MQTT_QOS0 and resultHandler): 
            resultHandler(Result(None, 1))  # immediately return messageId 0 in case of qos 0
        elif (qos > mqttcodec.MQTT_QOS0 and messageId and resultHandler): 
            timeOutMsg = 'Publishing message %s to topic %s with qos %d timed out.' % (payload, topic, qos)
            self.__resultHandlers[messageId] = {'time':time.time(), 'timeout': resultHandlerTimeout, 'handler':resultHandler, 'timeOutMsg':timeOutMsg}
        
    def subscribe(self, topic, qos, resultHandler=None, resultHandlerTimeout=MQTT_RESULT_HANDLER_TIMEOUT):
        if(not self.__connected or self.__connecting  or self.__waitingReconnect):
            raise MqttClientError("Cannot subscribe as not connected.")
        self.__validateTopic(topic)
        self.__validateQos(qos)
        self.__validateResultHandler(resultHandler)
        self.__validateTimeout(resultHandlerTimeout)
        fixedHeader = MqttFixedHeader(self.SUBSCRIBE, qos=1, dup=0, retain=0)
        messageId = self.__generateMessageId()
        variableHeader = {'messageId': messageId}
        subMsg = self.__mqttMsgFactory.message(fixedHeader, variableHeader, {'topic':topic, 'qos':qos})
        encodedMsg = self.__mqttEncoder.ecode(subMsg)
        if(resultHandler):
            timeOutMsg = 'Subscribe to topic %s with qos %d timed out.' % (topic, qos)
            self.__resultHandlers[messageId] = {'time':time.time(), 'timeout': resultHandlerTimeout, 'handler':resultHandler, 'timeOutMsg':timeOutMsg}
        self.__sendall(encodedMsg)
                
    def unsubscribe(self, topics, resultHandler=None, resultHandlerTimeout=MQTT_RESULT_HANDLER_TIMEOUT):
        if(not self.__connected or self.__connecting  or self.__waitingReconnect):
            raise MqttClientError("Cannot unsubscribe as not connected.")
        self.__validateResultHandler(resultHandler)
        self.__validateTimeout(resultHandlerTimeout)
        fixedHeader = MqttFixedHeader(self.UNSUBSCRIBE, qos=1, dup=0, retain=0)
        messageId = self.__generateMessageId()
        variableHeader = {'messageId': messageId}
        if(isinstance(topics, str)):
            topics = [topics]
        if(isinstance(topics, list)):
            for topic in topics:
                self.__validateTopic(topic)
                unsubMsg = self.__mqttMsgFactory.message(fixedHeader, variableHeader, topics)
                encodedMsg = self.__mqttEncoder.ecode(unsubMsg)
                if(resultHandler):
                    timeOutMsg = 'Unsubscribe to topics %s timed out.' % str(topics)
                    self.__resultHandlers[messageId] = {'time':time.time(), 'timeout': resultHandlerTimeout, 'handler':resultHandler, 'timeOutMsg':timeOutMsg}
                self.__sendall(encodedMsg)
                return messageId
        else:   raise TypeError('Topics should be an instance of string or list.') 
    
    def onConnect(self, callback):
        if(callable(callback)):
            self.__onConnectCallBack = callback
        else:
            raise ValueError('Callback should be a callable object.')
    
    def onDisconnect(self, callback):
        if(callable(callback)):
            self.__onDisconnectCallBack = callback
        else:
            raise ValueError('Callback should be a callable object.')
        
    def onDebugMessage(self, callback):
        if(callable(callback)):
            self.__onDebugMessageCallBack = callback
        else:
            raise ValueError('Callback should be a callable object.') 
    
    def onMessage(self, callback):
        if(callable(callback)):
            self.__onMessageCallBack = callback
        else:
            raise ValueError('Callback should be a callable object.') 
        
    def __validateTopic(self, topic):
        if(topic):
            pass
        else: raise ValueError('Topics cannot be Null or empty.')
        if (len(topic) < mqttcodec.MQTT_MAX_TOPIC_LEN + 1):
            pass
        else:
            raise ValueError('Topic length cannot be more than %d' % mqttcodec.MQTT_MAX_TOPIC_LEN)
        
    def __validateQos(self, qos):
        if(not isinstance(qos, int) or qos < mqttcodec.MQTT_QOS0 or qos > mqttcodec.MQTT_QOS2):
            raise ValueError('Qos should be a between %d and %d.' % (mqttcodec.MQTT_QOS0, mqttcodec.MQTT_QOS2)) 
        
    def __validateRetain(self, retain):
        if (not isinstance(retain, int) or retain != 0 or retain != 1):
            raise ValueError('Retain can only be integer 0 or 1')
        
    def __validateTimeout(self, timeout):
        if (not isinstance(timeout, int) or timeout < 0 or timeout > self.MQTT_MAX_RESULT_HANDLER_TIMEOUT):
            raise ValueError('Timeout can only be integer between 0 and %d.' % self.MQTT_MAX_RESULT_HANDLER_TIMEOUT)
        
    def __validateResultHandler(self, resultHandler):
        if(resultHandler is not None and not callable(resultHandler)):            
            raise ValueError('Result Handler should be a callable object.') 
            
    def __log(self, level, msg):
        if(level <= self.__logLevel):
            if(self.__onDebugMessageCallBack):
                self.__onDebugMessageCallBack(level, msg)

    def __sendall(self, data):
        try:
            if(data):
                self.__sock.sendall(data)
        except socket.error, msg:
            self.__resetInitSockNConnect()
            raise socket.error(str("Socket error in send: %s. Connection reset." % (str(msg))))
            
            
    def __receive(self):
        try:
            data = self.__sock.recv(self.MAX_BYTES_MDM_READ)
            if data: 
                mqttMsg = self.__mqttDecoder.decode(data)
            else:
                mqttMsg = None
            if (mqttMsg):
                self.__log(MQTT_LOG_LEVEL_INFO, '[MqttClient]:: Received message:%s' % mqttMsg.toString())
                self.__handleMqttMessage(mqttMsg) 
        except MqttDecoderError, msg:
            self.__log(MQTT_LOG_LEVEL_DEBUG, "[MqttClientError, method = __receive][%s]:: %s" % (msg.__class__.__name__ , str(msg)))
        except socket.timeout:
            pass
        except (MqttFrameError, socket.error), msg:
            self.__resetInitSockNConnect()
            self.__log(MQTT_LOG_LEVEL_DEBUG, "[MqttClientError, method = __receive][%s]:: %s" % (msg.__class__.__name__ , str(msg)))
            
    def __handleMqttMessage(self, mqttMessage):
        self.__lastPingRespTime = time.time()
        msgType = mqttMessage.fixedHeader.messageType
        if msgType == mqttcodec.CONNACK:
            self.__handleConnAckMsg(mqttMessage)
        elif msgType == mqttcodec.PUBLISH:
            self.__handlePublishMsg(mqttMessage)
        elif msgType == mqttcodec.SUBACK:
            self.__handleSubAck(mqttMessage)
        elif msgType == mqttcodec.UNSUBACK:
            self.__handleUnSubAck(mqttMessage)
        elif msgType == mqttcodec.PUBACK:
            self.__onPublish(mqttMessage)
        elif msgType == mqttcodec.PUBREC:
            self.__handlePubRecMsg(mqttMessage)
        elif msgType == mqttcodec.PUBCOMP:
            self.__onPublish(mqttMessage)
        elif msgType == mqttcodec.PUBREL:
            self.__handlePubRelMsg(mqttMessage)
        elif msgType == mqttcodec.PINGRESP:
            self.__lastPingRespTime = time.time()
        elif msgType in [mqttcodec.CONNECT, mqttcodec.SUBSCRIBE, mqttcodec.UNSUBSCRIBE, mqttcodec.PINGREQ]:
            pass  # Client will not receive these messages
        else:
            raise MqttEncoderError('MqttEncoder: Unknown message type.') 
    
    def __handleSubAck(self, mqttMessage):
        resultHandler = self.__resultHandlers.get(mqttMessage.messageId).get('handler')
        if(resultHandler):
            resultHandler(Result(mqttMessage, 1))
            del self.__resultHandlers[mqttMessage.messageId]
    
    def __handleUnSubAck(self, mqttMessage):
        resultHandler = self.__resultHandlers.get(mqttMessage.messageId).get('handler')
        if(resultHandler):
            resultHandler(Result(mqttMessage, 1))
            del self.__resultHandlers[mqttMessage.messageId]
    
    def __onPublish(self, mqttMessage):
        resultHandler = self.__resultHandlers.get(mqttMessage.messageId).get('handler')
        if(resultHandler):
            resultHandler(Result(mqttMessage, 1))
            del self.__resultHandlers[mqttMessage.messageId]
    
    def __handleConnAckMsg(self, mqttMessage):
        self.__connecting = 0
        connectReturnCode = mqttMessage.connectReturnCode
        if(connectReturnCode == mqttcodec.CONNECTION_ACCEPTED):
            self.__connected = 1
            self.__log(MQTT_LOG_LEVEL_INFO, '[MqttClient]:: Connected to %s:%s' % (self.host, str(self.port)))  
            if(self.__onConnectCallBack): self.__onConnectCallBack(self)  
        elif(connectReturnCode == mqttcodec.CONNECTION_REFUSED_UNACCEPTABLE_PROTOCOL_VERSION):
            self.__log(MQTT_LOG_LEVEL_DEBUG, '[MqttClient]:: Connection refused unacceptable mqtt protocol version.')
        elif(connectReturnCode == mqttcodec.CONNECTION_REFUSED_IDENTIFIER_REJECTED):
            self.__log(MQTT_LOG_LEVEL_DEBUG, '[MqttClient]:: Connection refused client identifier rejected.')  
        elif(connectReturnCode == mqttcodec.CONNECTION_REFUSED_SERVER_UNAVAILABLE):  
            self.__log(MQTT_LOG_LEVEL_DEBUG, '[MqttClient]:: Connection refused server unavailable.')
        elif(connectReturnCode == mqttcodec.CONNECTION_REFUSED_BAD_USERNAME_OR_PASSWORD):  
            self.__log(MQTT_LOG_LEVEL_DEBUG, '[MqttClient]:: Connection refused bad username or password.')
        elif(connectReturnCode == mqttcodec.CONNECTION_REFUSED_NOT_AUTHORIZED):  
            self.__log(MQTT_LOG_LEVEL_DEBUG, '[MqttClient]:: Connection refused not authorized.')
    
    def __handlePublishMsg(self, mqttMessage):
        if(mqttMessage.fixedHeader.qos > mqttcodec.MQTT_QOS1): 
            if(mqttMessage.messageId not in self.__msgIdInbox):
                self.__msgIdInbox.append(mqttMessage.messageId)
        if(self.__onMessageCallBack):
            self.__onMessageCallBack(mqttMessage)
            
    def __handlePubRelMsg(self, mqttMessage):
        fixedHeader = MqttFixedHeader(mqttcodec.PUBCOMP)
        variableHeader = {'messageId': mqttMessage.messageId}
        pubComMsg = self.__mqttMsgFactory.message(fixedHeader, variableHeader)
        encodedMsg = self.__mqttEncoder.ecode(pubComMsg)
        self.__sendall(encodedMsg)
        self.__msgIdInbox.remove(mqttMessage.messageId)
    
    def __handlePubRecMsg(self, mqttMessage):
        fixedHeader = MqttFixedHeader(mqttcodec.PUBREL)
        variableHeader = {'messageId': mqttMessage.messageId}
        pubRelMsg = self.__mqttMsgFactory.message(fixedHeader, variableHeader)
        encodedMsg = self.__mqttEncoder.ecode(pubRelMsg)
        self.__sendall(encodedMsg)
    
    def __resetInitSockNConnect(self):
        if(self.__sockInit):
            self.__log(MQTT_LOG_LEVEL_INFO, '[MqttClient]:: Resetting connection due to socket error...')
            self.__closeSocket()
            if(self.__onDisconnectCallBack): self.__onDisconnectCallBack()
        self.__sockInit = 0
        self.__connected = 0
        self.__connecting = 0
        
    
    def __initSock(self):
        t = time.time()
#         if (self.__sockInit is 0 and self.__nextConnTry - t > 0): raise SocketError('Last connection failed. Waiting before retry.')
        waitFor = self.__nextConnTry - t
        if (self.__sockInit is 0 and waitFor > 0): 
            if(not self.__waitingReconnect):
                self.__waitingReconnect = 1
                self.__log(MQTT_LOG_LEVEL_DEBUG, '[MqttClient]:: Last connection failed. Waiting  for %d seconds before retry...' % int(waitFor))
        if (self.__sockInit is 0 and waitFor <= 0):
            self.__nextConnTry = t + self.reconnectTimer
            if(self.__sock is not None):
                self.__closeSocket()
                self.__log(MQTT_LOG_LEVEL_INFO, '[MqttClient]:: Opening socket to %s:%s' % (self.host, str(self.port)))
            self.__sock = Socket(self.MQTT_SOCKET_TIMEOUT, self.keepAlive)
            self.__sock.connect((self.host, self.port))
            self.__sockInit = 1
            self.__waitingReconnect = 0
            self.__log(MQTT_LOG_LEVEL_INFO, '[MqttClient]:: Socket opened to %s:%s' % (self.host, str(self.port)))   
            
    
    def __closeSocket(self):
        try:
            self.__log(MQTT_LOG_LEVEL_INFO, '[MqttClient]:: Closing socket...')
            if(self.__sock):
                self.__sock.close()
                self.__sock = None
        except:
            pass 
    
    def __generateMessageId(self): 
        if self.__messageId == mqttcodec.MQTT_MAX_INT:
            self.__messageId = 0
        self.__messageId = self.__messageId + 1
        return self.__messageId
    
    def __processHandlersTimeout(self):
        for key, value in self.__resultHandlers.items():
            if((time.time() - value['time']) >= value['timeout']):
                resultHandler = value['handler']
                if(resultHandler):
                    timeOutMsg = value['timeOutMsg']
                    resultHandler(Result(None, 0, (MQTT_ERROR_TIMEOUT, timeOutMsg)))
                    value['handler'] = None
                del self.__resultHandlers[key]
                
    def __sendPingReq(self):
        fixedHeader = MqttFixedHeader(mqttcodec.PINGREQ)
        pingReqMsg = self.__mqttMsgFactory.message(fixedHeader)
        encodedMsg = self.__mqttEncoder.ecode(pingReqMsg)
        self.__sendall(encodedMsg)
        self.__nextPingReqTime = time.time() + self.keepAliveTimer
    

class MqttClientError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)