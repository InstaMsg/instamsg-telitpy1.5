# -*- coding: utf-8 -*-
import MOD
import MDM
import MDM2
import sys 
import mqtt
import http
import exceptions

####InstaMsg ###############################################################################
# Logging Levels
INSTAMSG_LOG_LEVEL_DISABLED = 0
INSTAMSG_LOG_LEVEL_INFO = 1
INSTAMSG_LOG_LEVEL_ERROR = 2
INSTAMSG_LOG_LEVEL_DEBUG = 3
# Logging Level String
INSTAMSG_LOG_LEVEL = {0:"DISABLED", 1:"INFO", 2:"ERROR", 3:"DEBUG"}
# Error codes
INSTAMSG_ERROR_TIMEOUT = 0
INSTAMSG_ERROR_NO_HANDLERS = 1
INSTAMSG_ERROR_SOCKET = 2
INSTAMSG_ERROR_AUTHENTICATION = 3
# Message QOS
INSTAMSG_QOS0 = 0
INSTAMSG_QOS1 = 1
INSTAMSG_QOS2 = 2

class InstaMsg:
    INSTAMSG_MAX_BYTES_IN_MSG = 10240
    INSTAMSG_KEEP_ALIVE_TIMER = 60
    INSTAMSG_RECONNECT_TIMER = 90
    INSTAMSG_HOST = "test.ioeye.com"
    # INSTAMSG_HOST = "api.instamsg.io"
    INSTAMSG_PORT = 1883
    INSTAMSG_PORT_SSL = 8883
    INSTAMSG_HTTP_HOST = "localhost"
    # INSTAMSG_HTTP_HOST = 'test.ioeye.com'
    INSTAMSG_HTTP_PORT = 8600
    # INSTAMSG_HTTP_PORT = 80
    INSTAMSG_HTTPS_PORT = 443
    INSTAMSG_API_VERSION = "beta"
    INSTAMSG_RESULT_HANDLER_TIMEOUT = 10    
    INSTAMSG_MSG_REPLY_HANDLER_TIMEOUT = 10
    
    def __init__(self, clientId, authKey, connectHandler, disConnectHandler, oneToOneMessageHandler, options={}):
        if(not callable(connectHandler)): raise ValueError('connectHandler should be a callable object.')
        if(not callable(disConnectHandler)): raise ValueError('disConnectHandler should be a callable object.')
        if(not callable(oneToOneMessageHandler)): raise ValueError('oneToOneMessageHandler should be a callable object.')
        self.__clientId = clientId
        self.__authKey = authKey 
        self.__options = options
        self.__onConnectCallBack = connectHandler   
        self.__onDisConnectCallBack = disConnectHandler  
        self.__oneToOneMessageHandler = oneToOneMessageHandler
        self.__filesTopic = "instamsg/clients/" + clientId + "/files";
        self.__fileUploadUrl = "/api/%s/clients/%s/files" % (self.INSTAMSG_API_VERSION, clientId)
        self.__defaultReplyTimeout = self.INSTAMSG_RESULT_HANDLER_TIMEOUT
        self.__msgHandlers = {}
        self.__sendMsgReplyHandlers = {}  # {handlerId:{time:122334,handler:replyHandler, timeout:10, timeOutMsg:"Timed out"}}
        self.__initOptions(options)
        if(self.__enableTcp):
            clientIdAndUsername = self.__getClientIdAndUsername(clientId)
            mqttoptions = self.__mqttClientOptions(clientIdAndUsername[1], authKey, self.__keepAliveTimer)
            self.__mqttClient = mqtt.MqttClient(self.INSTAMSG_HOST, self.__port, clientIdAndUsername[0], mqttoptions)
            self.__mqttClient.onConnect(self.__onConnect)
            self.__mqttClient.onDisconnect(self.__onDisConnect)
            self.__mqttClient.onDebugMessage(self.__handleDebugMessage)
            self.__mqttClient.onMessage(self.__handleMessage)
            self.__mqttClient.connect()
        else:
            self.__mqttClient = None
        self.__httpClient = http.HTTPClient(self.INSTAMSG_HTTP_HOST, self.__httpPort)
        
    def __initOptions(self, options):
        if(self.__options.has_key('enableSocket')):
            self.__enableTcp = options.get('enableSocket')
        else: self.__enableTcp = 1
        if(self.__options.has_key('enableLogToServer')):
            self.__enableLogToServer = options.get('enableLogToServer')
        else: self.__enableLogToServer = 0
        if(self.__options.has_key('logLevel')):
            self.__logLevel = options.get('logLevel')
            if(self.__logLevel < INSTAMSG_LOG_LEVEL_DISABLED or self.__logLevel > INSTAMSG_LOG_LEVEL_DEBUG):
                raise ValueError("logLevel option should be in between %d and %d" % (INSTAMSG_LOG_LEVEL_DISABLED, INSTAMSG_LOG_LEVEL_DEBUG))
        else: self.__logLevel = INSTAMSG_LOG_LEVEL_DISABLED
        if(options.has_key('keepAliveTimer')):
            self.__keepAliveTimer = options.get('keepAliveTimer')
        else:
            self.__keepAliveTimer = self.INSTAMSG_KEEP_ALIVE_TIMER
        if(options.has_key('enableSsl') and options.get('enableSsl')): 
            self.__port = self.INSTAMSG_PORT_SSL 
            self.__httpPort = self.INSTAMSG_HTTPS_PORT
        else: 
            self.__port = self.INSTAMSG_PORT
            self.__httpPort = self.INSTAMSG_HTTP_PORT
        
    def process(self):
        try:
            if(self.__mqttClient):
                self.__processHandlersTimeout()
                self.__mqttClient.process()
        except Exception, e:
            self.__handleDebugMessage(INSTAMSG_LOG_LEVEL_ERROR, "[InstaMsgClientError, method = process]- %s" % (str(e)))
    
    def close(self):
        try:
            self.__mqttClient.disconnect()
            self.__mqttClient = None
            self.__sendMsgReplyHandlers = None
            self.__msgHandlers = None
            self.__subscribers = None
            return 1
        except:
            return -1
    
    def publish(self, topic, msg, qos=INSTAMSG_QOS0, dup=0, resultHandler=None, timeout=INSTAMSG_RESULT_HANDLER_TIMEOUT):
        if(topic):
            try:
                self.__mqttClient.publish(topic, msg, qos, dup, resultHandler, timeout)
            except Exception, e:
                raise InstaMsgPubError(str(e))
        else: raise ValueError("Topic cannot be null or empty string.")
    
    def subscribe(self, topic, qos, msgHandler, resultHandler, timeout=INSTAMSG_RESULT_HANDLER_TIMEOUT):
        if(self.__mqttClient):
            try:
                if(not callable(msgHandler)): raise ValueError('msgHandler should be a callable object.')
                self.__msgHandlers[topic] = msgHandler
                if(topic == self.__clientId):
                    raise ValueError("Canot subscribe to clientId. Instead set oneToOneMessageHandler.")
                self.__mqttClient.subscribe(topic, qos, resultHandler, timeout)
            except Exception, e:
                self.__handleDebugMessage(INSTAMSG_LOG_LEVEL_ERROR, "[InstaMsgClientError, method = subscribe][%s]:: %s" % (e.__class__.__name__ , str(e)))
                raise InstaMsgSubError(str(e))
        else:
            self.__handleDebugMessage(INSTAMSG_LOG_LEVEL_ERROR, "[InstaMsgClientError, method = subscribe][%s]:: %s" % ("InstaMsgSubError" + str(e)))
            raise InstaMsgSubError("Cannot subscribe as TCP is not enabled. Two way messaging only possible on TCP and not HTTP")
            

    def unsubscribe(self, topics, resultHandler, timeout=INSTAMSG_RESULT_HANDLER_TIMEOUT):
        if(self.__mqttClient):
            try:
                self.__mqttClient.unsubscribe(topics, resultHandler, timeout)
            except Exception, e:
                self.__handleDebugMessage(INSTAMSG_LOG_LEVEL_ERROR, "[InstaMsgClientError, method = unsubscribe][%s]:: %s" % (e.__class__.__name__ , str(e)))
                raise InstaMsgUnSubError(str(e))
        else:
            self.__handleDebugMessage(INSTAMSG_LOG_LEVEL_ERROR, "[InstaMsgClientError, method = unsubscribe][%s]:: %s" % ("InstaMsgUnSubError" , str(e)))
            raise InstaMsgUnSubError("Cannot unsubscribe as TCP is not enabled. Two way messaging only possible on TCP and not HTTP")
    
    def send(self, clienId, msg, qos=INSTAMSG_QOS0, dup=0, replyHandler=None, timeout=INSTAMSG_MSG_REPLY_HANDLER_TIMEOUT):
        try:
            messageId = self._generateMessageId()
            msg = Message(messageId, clienId, msg, qos, dup, replyTopic=self.__clientId, instaMsg=self)._sendMsgJsonString()
            self._send(messageId, clienId, msg, qos, dup, replyHandler, timeout)
        except Exception, e:
            self.__handleDebugMessage(INSTAMSG_LOG_LEVEL_ERROR, "[InstaMsgClientError, method = send][%s]:: %s" % (e.__class__.__name__ , str(e)))
            raise InstaMsgSendError(str(e))
        
    def log(self, level, message):
        pass
    
    def _send(self, messageId, clienId, msg, qos, dup, replyHandler, timeout):
        try:
            if(replyHandler):
                timeOutMsg = "Sending message[%s] %s to %s timed out." % (str(messageId), str(msg), str(clienId))
                self.__sendMsgReplyHandlers[messageId] = {'time':time.time(), 'timeout': timeout, 'handler':replyHandler, 'timeOutMsg':timeOutMsg}
                def _resultHandler(result):
                    if(result.failed()):
                        replyHandler(result)
                        del self.__sendMsgReplyHandlers[messageId]
            else:
                _resultHandler = None
            self.publish(clienId, msg, qos, dup, _resultHandler)
        except Exception, e:
            if(self.__sendMsgReplyHandlers.has_key(messageId)):
                del self.__sendMsgReplyHandlers[messageId]
            raise Exception(str(e))
            
    def _generateMessageId(self):
        messageId = self.__clientId + "-" + str(int(time.time() * 1000))
        while(self.__sendMsgReplyHandlers.has_key(messageId)):
            messageId = time.time()
        return messageId;
    
    def __onConnect(self, mqttClient):
        self.__handleDebugMessage(INSTAMSG_LOG_LEVEL_INFO, "[InstaMsg]:: Client connected to InstaMsg IOT cloud service.")
        if(self.__onConnectCallBack): self.__onConnectCallBack(self)  
        
    def __onDisConnect(self):
        self.__handleDebugMessage(INSTAMSG_LOG_LEVEL_INFO, "[InstaMsg]:: Client disconnected from InstaMsg IOT cloud service.")
        if(self.__onDisConnectCallBack): self.__onDisConnectCallBack()  
        
    def __handleDebugMessage(self, level, msg):
        if(level <= self.__logLevel):
            if(self.__enableLogToServer):
                self.log(level, msg)
            else:
                print "[%s]%s" % (INSTAMSG_LOG_LEVEL[level], msg)
    
    def __handleMessage(self, mqttMsg):
        if(mqttMsg.topic == self.__clientId):
            self.__handleOneToOneMessage(mqttMsg)
        elif(mqttMsg.topic == self.__filesTopic):
            self.__handleFileTransferMessage(mqttMsg)
        else:
            msg = Message(mqttMsg.messageId, mqttMsg.topic, mqttMsg.payload, mqttMsg.fixedHeader.qos, mqttMsg.fixedHeader.dup)
            msgHandler = self.__msgHandlers.get(mqttMsg.topic)
            if(msgHandler):
                msgHandler(msg)
                
    def __handleFileTransferMessage(self, mqttMsg):
        msgJson = self.__parseJson(mqttMsg.payload)
        qos, dup = mqttMsg.fixedHeader.qos, mqttMsg.fixedHeader.dup
        messageId, replyTopic, method, url, filename = None, None, None, None, None
        if(msgJson.has_key('reply_to')):
            replyTopic = msgJson['reply_to']
        else:
            raise ValueError("File transfer message json should have reply_to address.")   
        if(msgJson.has_key('message_id')):
            messageId = msgJson['message_id']
        else: 
            raise ValueError("File transfer message json should have a message_id.") 
        if(msgJson.has_key('method')):
            method = msgJson['method']
        else: 
            raise ValueError("File transfer message json should have a method.") 
        if(msgJson.has_key('url')):
            url = msgJson['url']
        if(msgJson.has_key('filename')):
            filename = msgJson['filename']
        if(replyTopic):
            if(method == "GET" and not filename):
                filelist = self.__getFileList()
                msg = '{"response_id": "%s", "status": 1, "files": %s}' % (messageId, filelist)
                self.publish(replyTopic, msg, qos, dup)
            elif (method == "GET" and filename):
                httpResponse = self.__httpClient.uploadFile(self.__fileUploadUrl, filename, headers={"Authorization":self.__authKey})
                if(httpResponse and httpResponse.status == 200):
                    msg = '{"response_id": "%s", "status": 1, "url":"%s"}' % (messageId, httpResponse.body)
                else:
                    msg = '{"response_id": "%s", "status": 0}' % (messageId)
                self.publish(replyTopic, msg, qos, dup)
            elif ((method == "POST" or method == "PUT") and filename and url):
                httpResponse = self.__httpClient.downloadFile(url, filename)
                if(httpResponse and httpResponse.status == 200):
                    msg = '{"response_id": "%s", "status": 1}' % (messageId)
                else:
                    msg = '{"response_id": "%s", "status": 0}' % (messageId)
                self.publish(replyTopic, msg, qos, dup)
            elif ((method == "DELETE") and filename):
                try:
                    msg = '{"response_id": "%s", "status": 1}' % (messageId)
                    self.__deleteFile(filename)
                    self.publish(replyTopic, msg, qos, dup)
                except Exception, e:
                    msg = '{"response_id": "%s", "status": 0, "error_msg":"%s"}' % (messageId, str(e))
                    self.publish(replyTopic, msg, qos, dup)
                    
            
    def __getFileList(self):
        return '{"test.py":100}'
#         path = os.getcwd()
#         fileList = ""
#         for root, dirs, files in os.walk(path):
#             for name in files:
#                 filename = os.path.join(root, name)
#                 size = os.stat(filename).st_size
#                 if(fileList):
#                     fileList = fileList + ","
#                 fileList = fileList + '"%s":%d' % (name, size)
#         return '{%s}' % fileList      
    
    def __deleteFile(self, filename):
        unlink(filename)
        
    def __handleOneToOneMessage(self, mqttMsg):
        msgJson = self.__parseJson(mqttMsg.payload)
        messageId, responseId, replyTopic, status = None, None, None, 1
        if(msgJson.has_key('reply_to')):
            replyTopic = msgJson['reply_to']
        else:
            raise ValueError("Send message json should have reply_to address.")   
        if(msgJson.has_key('message_id')):
            messageId = msgJson['message_id']
        else: 
            raise ValueError("Send message json should have a message_id.") 
        if(msgJson.has_key('response_id')):
            responseId = msgJson['response_id']
        if(msgJson.has_key('body')):
            body = msgJson['body']
        if(msgJson.has_key('status')):
            status = int(msgJson['status'])
        qos, dup = mqttMsg.fixedHeader.qos, mqttMsg.fixedHeader.dup
        if(responseId):
            # This is a response to existing message
            if(status == 0):
                errorCode, errorMsg = None, None
                if(isinstance(body, dict)):
                    if(body.has_key("error_code")):
                        errorCode = body.get("error_code")
                    if(body.has_key("error_msg")):
                        errorMsg = body.get("error_msg")
                result = Result(None, 0, (errorCode, errorMsg))
            else:
                msg = Message(messageId, self.__clientId, body, qos, dup, replyTopic=replyTopic, instaMsg=self)
                result = Result(msg, 1)
            
            if(self.__sendMsgReplyHandlers.has_key(responseId)):
                msgHandler = self.__sendMsgReplyHandlers.get(responseId).get('handler')
            else:
                msgHandler = None
                self.__handleDebugMessage(INSTAMSG_LOG_LEVEL_INFO, "[InstaMsg]:: No handler for message [messageId=%s responseId=%s]" % (str(messageId), str(responseId)))
            if(msgHandler):
                msgHandler(result)
                del self.__sendMsgReplyHandlers[responseId]
        else:
            if(self.__oneToOneMessageHandler):
                msg = Message(messageId, self.__clientId, body, qos, dup, replyTopic=replyTopic, instaMsg=self)
                self.__oneToOneMessageHandler(msg)
        
    def __mqttClientOptions(self, username, password, keepAliveTimer):
        if(len(password) > self.INSTAMSG_MAX_BYTES_IN_MSG): raise ValueError("Password length cannot be more than %d bytes." % self.INSTAMSG_MAX_BYTES_IN_MSG)
        if(keepAliveTimer > 32768 or keepAliveTimer < self.INSTAMSG_KEEP_ALIVE_TIMER): raise ValueError("keepAliveTimer should be between %d and 32768" % self.INSTAMSG_KEEP_ALIVE_TIMER)
        options = {}
        options['hasUserName'] = 1
        options['hasPassword'] = 1
        options['username'] = username
        options['password'] = password
        options['isCleanSession'] = 1
        options['keepAliveTimer'] = keepAliveTimer
        options['isWillFlag'] = 0
        options['willQos'] = 0
        options['isWillRetain'] = 0
        options['willTopic'] = ""
        options['willMessage'] = ""
        options['logLevel'] = self.__logLevel
        options['reconnectTimer'] = self.INSTAMSG_RECONNECT_TIMER
        return options
    
    def __getClientIdAndUsername(self, clientId):
        errMsg = 'clientId is not a valid uuid e.g. cbf7d550-7204-11e4-a2ad-543530e3bc65'
        if(clientId is None): raise ValueError('clientId cannot be null.')
        if(len(clientId) != 36): raise ValueError(errMsg)
        c = clientId.split('-')
        if(len(c) != 5): raise ValueError(errMsg)
        cId = '-'.join(c[0:4])
        userName = c[4 ]
        if(len(userName) != 12): raise ValueError(errMsg)
        return (cId, userName)
    
    def __parseJson(self, jsonString):
        return eval(jsonString)  # Hack as not implemented Json Library
    
    def __processHandlersTimeout(self): 
        for key, value in self.__sendMsgReplyHandlers.items():
            if((time.time() - value['time']) >= value['timeout']):
                resultHandler = value['handler']
                if(resultHandler):
                    timeOutMsg = value['timeOutMsg']
                    resultHandler(Result(None, 0, (INSTAMSG_ERROR_TIMEOUT, timeOutMsg)))
                    value['handler'] = None
                del self.__sendMsgReplyHandlers[key]
                
class Message:
    def __init__(self, messageId, topic, body, qos=INSTAMSG_QOS0, dup=0, replyTopic=None, instaMsg=None):
        self.__instaMsg = instaMsg
        self.__id = messageId
        self.__topic = topic
        self.__body = body
        self.__replyTopic = replyTopic
        self.__responseId = None
        self.__dup = dup
        self.__qos = qos
        
    def id(self):
        return self.__id
    
    def topic(self):
        return self.__topic
    
    def qos(self):
        return self.__qos
    
    def isDublicate(self):
        return self.__dup
    
    def body(self):
        return self.__body
    
    def replyTopic(self):
        return self.__replyTopic
        
    def reply(self, msg, dup=0, replyHandler=None, timeout=InstaMsg.INSTAMSG_RESULT_HANDLER_TIMEOUT):
        if(self.__instaMsg and self.__replyTopic):
            msgId = self.__instaMsg._generateMessageId()
            replyMsgJsonString = ('{"message_id": "%s", "response_id": "%s", "reply_to": "%s", "body": "%s", "status": 1}') % (msgId, self.__id, self.__topic, msg)
            self.__instaMsg._send(msgId, self.__replyTopic, replyMsgJsonString, self.__qos, dup, replyHandler, timeout)
    
    def fail(self, errorCode, errorMsg):
        if(self.__instaMsg and self.__replyTopic):
            msgId = self.__instaMsg._generateMessageId()
            failReplyMsgJsonString = ('{"message_id": "%s", "response_id": "%s", "reply_to": "%s", "body": {"error_code":%d, "error_msg":%s}, "status": 0}') % (msgId, self.__id, self.__topic, errorCode, errorMsg)
            self.__instaMsg._send(msgId, self.__replyTopic, failReplyMsgJsonString, self.__qos, 0, None, 0)
    
    def sendFile(self, fileName, resultHandler, timeout):
        pass
    
    def _sendMsgJsonString(self):
        return ('{"message_id": "%s", "reply_to": "%s", "body": "%s"}') % (self.__id, self.__replyTopic, self.__body)
    
    def toString(self):
        return ('[ id=%s, topic=%s, body=%s, qos=%s, dup=%s, replyTopic=%s]') % (str(self.__id), str(self.__topic), str(self.__body), str(self.__qos), str(self.__dup), str(self.__replyTopic))
    
    def __sendReply(self, msg, replyHandler):
        pass
    
class Result:
    def __init__(self, result, succeeded=1, cause=None):
        self.__result = result
        self.__succeeded = 1
        self.__cause = cause
        
    def result(self):
        return self.__result
    
    def failed(self):
        return not self.__succeeded
    
    def succeeded(self):
        return self.__succeeded
    
    def cause(self):
        return self.__cause
    
class InstaMsgError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class InstaMsgSubError(InstaMsgError):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class InstaMsgUnSubError(InstaMsgError):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class InstaMsgPubError(InstaMsgError):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class InstaMsgSendError(InstaMsgError):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
