# -*- coding: utf-8 -*-
import exceptions

MQTT_PROTOCOL_VERSION = 3
MQTT_PROTOCOL_NAME = "MQIsdp"
MQTT_MAX_INT = 65535
MQTT_MAX_TOPIC_LEN = 32767
MQTT_MAX_PAYLOAD_SIZE = 10240
MQTT_SOCKET_TIMEOUT = 10
# Mqtt Message Types
CONNECT = 0x10
CONNACK = 0x20
PUBLISH = 0x30
PUBACK = 0x40
PUBREC = 0x50
PUBREL = 0x60
PUBCOMP = 0x70
SUBSCRIBE = 0x80
SUBACK = 0x90
UNSUBSCRIBE = 0xA0
UNSUBACK = 0xB0
PINGREQ = 0xC0
PINGRESP = 0xD0
DISCONNECT = 0xE0
# CONNACK codes
CONNECTION_ACCEPTED = 0x00
CONNECTION_REFUSED_UNACCEPTABLE_PROTOCOL_VERSION = 0X01
CONNECTION_REFUSED_IDENTIFIER_REJECTED = 0x02
CONNECTION_REFUSED_SERVER_UNAVAILABLE = 0x03
CONNECTION_REFUSED_BAD_USERNAME_OR_PASSWORD = 0x04
CONNECTION_REFUSED_NOT_AUTHORIZED = 0x05;
# QOS codes
MQTT_QOS0 = 0
MQTT_QOS1 = 1
MQTT_QOS2 = 2
    
class MqttDecoder:
    READING_FIXED_HEADER_FIRST = 0
    READING_FIXED_HEADER_REMAINING = 1
    READING_VARIABLE_HEADER = 2
    READING_PAYLOAD = 3
    DISCARDING_MESSAGE = 4
    MESSAGE_READY = 5
    BAD = 6
    
    def __init__(self):
        self.__data = ''
        self.__init()
        self.__msgFactory = MqttMsgFactory()
        
    def __state(self):
        return self.__state
    
    def decode(self, data):
        if(data):
            self.__data = self.__data + data
            if(self.__state == self.READING_FIXED_HEADER_FIRST):
                self.__decodeFixedHeaderFirstByte(self.__getByteStr())
                self.__state = self.READING_FIXED_HEADER_REMAINING
            if(self.__state == self.READING_FIXED_HEADER_REMAINING):
                self.__decodeFixedHeaderRemainingLength()
                if (self.__fixedHeader.messageType == MqttClient.PUBLISH and not self.__variableHeader):
                    self.__initPubVariableHeader()
            if(self.__state == self.READING_VARIABLE_HEADER):
                self.__decodeVariableHeader()
            if(self.__state == self.READING_PAYLOAD):
                bytesRemaining = self.__remainingLength - (self.__bytesConsumedCounter - self.__remainingLengthCounter - 1)
                self.__decodePayload(bytesRemaining)
            if(self.__state == self.DISCARDING_MESSAGE):
                bytesLeftToDiscard = self.__remainingLength - self.__bytesDiscardedCounter
                if (bytesLeftToDiscard <= len(self.__data)):
                    bytesToDiscard = bytesLeftToDiscard
                else: bytesToDiscard = len(self.__data)
                self.__bytesDiscardedCounter = self.__bytesDiscardedCounter + bytesToDiscard
                self.__data = self.__data[0:(bytesToDiscard - 1)] 
                if(self.__bytesDiscardedCounter == self.__remainingLength):
                    e = self.__error
                    self.__init()
                    raise MqttDecoderError(e) 
            if(self.__state == self.MESSAGE_READY):
                # returns a tuple of (mqttMessage, dataRemaining)
                mqttMsg = self.__msgFactory.message(self.__fixedHeader, self.__variableHeader, self.__payload)
                self.__init()
                return mqttMsg
            if(self.__state == self.BAD):
                # do not decode until disconnection.
                raise MqttFrameError(self.__error)  
        return None 
            
    def __decodeFixedHeaderFirstByte(self, byteStr):
        byte = ord(byteStr)
        self.__fixedHeader.messageType = (byte & 0xF0)
        self.__fixedHeader.dup = (byte & 0x08) >> 3
        self.__fixedHeader.qos = (byte & 0x06) >> 1
        self.__fixedHeader.retain = (byte & 0x01)
    
    def __decodeFixedHeaderRemainingLength(self):
            while (1 and self.__data):
                byte = ord(self.__getByteStr())
                self.__remainingLength = self.__remainingLength + (byte & 127) * self.__multiplier
                self.__multiplier = self.__multiplier * 128
                self.__remainingLengthCounter = self.__remainingLengthCounter + 1
                if(self.__remainingLengthCounter > 4):
                    self.__state = self.BAD
                    self.__error = ('MqttDecoder: Error in decoding remaining length in message fixed header.') 
                    break
                if((byte & 128) == 0):
                    self.__state = self.READING_VARIABLE_HEADER
                    self.__fixedHeader.remainingLength = self.__remainingLength
                    break
                
    def __initPubVariableHeader(self):
        self.__variableHeader['topicLength'] = None
        self.__variableHeader['messageId'] = None
        self.__variableHeader['topic'] = None
        

    def __decodeVariableHeader(self):  
        if self.__fixedHeader.messageType in [MqttClient.CONNECT, MqttClient.SUBSCRIBE, MqttClient.UNSUBSCRIBE, MqttClient.PINGREQ]:
            self.__state = self.DISCARDING_MESSAGE
            self.__error = ('MqttDecoder: Client cannot receive CONNECT, SUBSCRIBE, UNSUBSCRIBE, PINGREQ message type.') 
        elif self.__fixedHeader.messageType == MqttClient.CONNACK:
            if(self.__fixedHeader.remainingLength != 2):
                self.__state = self.BAD
                self.__error = ('MqttDecoder: Mqtt CONNACK message should have remaining length 2 received %s.' % self.__fixedHeader.remainingLength) 
            elif(len(self.__data) < 2):
                pass  # let for more bytes come
            else:
                self.__getByteStr()  # discard reserved byte
                self.__variableHeader['connectReturnCode'] = ord(self.__getByteStr())
                self.__state = self.MESSAGE_READY
        elif self.__fixedHeader.messageType == MqttClient.SUBACK:
            messageId = self.__decodeMsbLsb()
            if(messageId is not None):
                self.__variableHeader['messageId'] = messageId
                self.__state = self.READING_PAYLOAD
        elif self.__fixedHeader.messageType in [MqttClient.UNSUBACK, MqttClient.PUBACK, MqttClient.PUBREC, MqttClient.PUBCOMP, MqttClient.PUBREL]:
            messageId = self.__decodeMsbLsb()
            if(messageId is not None):
                self.__variableHeader['messageId'] = messageId
                self.__state = self.MESSAGE_READY
        elif self.__fixedHeader.messageType == MqttClient.PUBLISH:
            if(self.__variableHeader['topic'] is None):
                self.__decodeTopic()
            if (self.__fixedHeader.qos > MqttClient.MQTT_QOS0 and self.__variableHeader['topic'] is not None and self.__variableHeader['messageId'] is None):
                self.__variableHeader['messageId'] = self.__decodeMsbLsb()
            if (self.__variableHeader['topic'] is not None and (self.__fixedHeader.qos == MqttClient.MQTT_QOS0 or self.__variableHeader['messageId'] is not None)):
                self.__state = self.READING_PAYLOAD
        elif self.__fixedHeader.messageType in [MqttClient.PINGRESP, MqttClient.DISCONNECT]:
            self.__mqttMsg = self.__msgFactory.message(self.__fixedHeader)
            self.__state = self.MESSAGE_READY
        else:
            self.__state = self.DISCARDING_MESSAGE
            self.__error = ('MqttDecoder: Unrecognised message type.') 
            
    def __decodePayload(self, bytesRemaining):
        paloadBytes = self.__getNBytesStr(bytesRemaining)
        if(paloadBytes is not None):
            if self.__fixedHeader.messageType == MqttClient.SUBACK:
                grantedQos = []
                numberOfBytesConsumed = 0
                while (numberOfBytesConsumed < bytesRemaining):
                    qos = int(ord(paloadBytes[numberOfBytesConsumed]) & 0x03)
                    numberOfBytesConsumed = numberOfBytesConsumed + 1
                    grantedQos.append(qos)
                self.__payload = grantedQos
                self.__state = self.MESSAGE_READY
            elif self.__fixedHeader.messageType == MqttClient.PUBLISH:
                self.__payload = paloadBytes
                self.__state = self.MESSAGE_READY
    
    def __decodeTopic(self):
        stringLength = self.__variableHeader['topicLength']
        if(stringLength is None):
            stringLength = self.__decodeMsbLsb()
            self.__variableHeader['topicLength'] = stringLength
        if (self.__data and stringLength and (len(self.__data) < stringLength)):
            return None  # wait for more bytes
        else:
            self.__variableHeader['topic'] = self.__getNBytesStr(stringLength)
    
    def __decodeMsbLsb(self):
        if(len(self.__data) < 2):
            return None  # wait for 2 bytes
        else:
            msb = self.__getByteStr()
            lsb = self.__getByteStr()
            intMsbLsb = ord(msb) << 8 | ord(lsb)
        if (intMsbLsb < 0 or intMsbLsb > MqttClient.MQTT_MAX_INT):
            return -1
        else:
            return intMsbLsb
        
    
    def __getByteStr(self):
        return self.__getNBytesStr(1)
    
    def __getNBytesStr(self, n):
        # gets n or less bytes
        nBytes = self.__data[0:n]
        self.__data = self.__data[n:len(self.__data)]
        self.__bytesConsumedCounter = self.__bytesConsumedCounter + n
        return nBytes
    
    def __init(self):   
        self.__state = self.READING_FIXED_HEADER_FIRST
        self.__remainingLength = 0
        self.__multiplier = 1
        self.__remainingLengthCounter = 0
        self.__bytesConsumedCounter = 0
        self.__payloadCounter = 0
        self.__fixedHeader = MqttFixedHeader()
        self.__variableHeader = {}
        self.__payload = None
        self.__mqttMsg = None
        self.__bytesDiscardedCounter = 0 
        self.__error = 'MqttDecoder: Unrecognized __error'

class MqttEncoder:
    def __init__(self):
        pass
    
    def ecode(self, mqttMessage):
        msgType = mqttMessage.fixedHeader.messageType
        if msgType == MqttClient.CONNECT:
            return self.__encodeConnectMsg(mqttMessage) 
        elif msgType == MqttClient.CONNACK:
            return self.__encodeConnAckMsg(mqttMessage)
        elif msgType == MqttClient.PUBLISH:
            return self.__encodePublishMsg(mqttMessage)
        elif msgType == MqttClient.SUBSCRIBE:
            return self.__encodeSubscribeMsg(mqttMessage)
        elif msgType == MqttClient.UNSUBSCRIBE:
            return self.__encodeUnsubscribeMsg(mqttMessage)
        elif msgType == MqttClient.SUBACK:
            return self.__encodeSubAckMsg(mqttMessage)
        elif msgType in [MqttClient.UNSUBACK, MqttClient.PUBACK, MqttClient.PUBREC, MqttClient.PUBCOMP, MqttClient.PUBREL]:
            return self.__encodeFixedHeaderAndMessageIdOnlyMsg(mqttMessage)
        elif msgType in [MqttClient.PINGREQ, MqttClient.PINGRESP, MqttClient.DISCONNECT]:
            return self.__encodeFixedHeaderOnlyMsg(mqttMessage)
        else:
            raise MqttEncoderError('MqttEncoder: Unknown message type.') 
    
    def __encodeConnectMsg(self, mqttConnectMessage):
        if(isinstance(mqttConnectMessage, MqttConnectMsg)):
            variableHeaderSize = 12
            fixedHeader = mqttConnectMessage.fixedHeader
            # Encode Payload
            clientId = self.__encodeStringUtf8(mqttConnectMessage.clientId)
            if(not self.__isValidClientId(clientId)):
                raise ValueError("MqttEncoder: invalid clientId: " + clientId + " should be less than 23 chars in length.")
            encodedPayload = self.__encodeIntShort(len(clientId)) + clientId
            if(mqttConnectMessage.isWillFlag):
                encodedPayload = encodedPayload + self.__encodeIntShort(len(mqttConnectMessage.willTopic)) + self.__encodeStringUtf8(mqttConnectMessage.willTopic)
                encodedPayload = encodedPayload + self.__encodeIntShort(len(mqttConnectMessage.willMessage)) + self.__encodeStringUtf8(mqttConnectMessage.willMessage)
            if(mqttConnectMessage.hasUserName):
                encodedPayload = encodedPayload + self.__encodeIntShort(len(mqttConnectMessage.username)) + self.__encodeStringUtf8(mqttConnectMessage.username)
            if(mqttConnectMessage.hasPassword):
                encodedPayload = encodedPayload + self.__encodeIntShort(len(mqttConnectMessage.password)) + self.__encodeStringUtf8(mqttConnectMessage.password)
            # Encode Variable Header
            connectFlagsByte = 0;
            if (mqttConnectMessage.hasUserName): 
                connectFlagsByte = connectFlagsByte | 0x80
            if (mqttConnectMessage.hasPassword):
                connectFlagsByte = connectFlagsByte | 0x40
            if (mqttConnectMessage.isWillRetain):
                connectFlagsByte = connectFlagsByte | 0x20
            connectFlagsByte = connectFlagsByte | ((mqttConnectMessage.willQos & 0x03) << 3)
            if (mqttConnectMessage.isWillFlag):
                connectFlagsByte = connectFlagsByte | 0x04
            if (mqttConnectMessage.isCleanSession):
                connectFlagsByte = connectFlagsByte | 0x02;
            encodedVariableHeader = self.__encodeIntShort(len(mqttConnectMessage.protocolName)) + mqttConnectMessage.protocolName + chr(mqttConnectMessage.version) + chr(connectFlagsByte) + self.__encodeIntShort(mqttConnectMessage.keepAliveTimer)
            return self.__encodeFixedHeader(fixedHeader, variableHeaderSize, encodedPayload) + encodedVariableHeader + encodedPayload
        else:
            raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttConnectMsg.__name__, mqttConnectMessage.__class__.__name__)) 
            
    def __encodeConnAckMsg(self, mqttConnAckMsg):
        if(isinstance(mqttConnAckMsg, MqttConnAckMsg)):
            fixedHeader = mqttConnAckMsg.fixedHeader
            encodedVariableHeader = mqttConnAckMsg.connectReturnCode
            return self.__encodeFixedHeader(fixedHeader, 2, None) + encodedVariableHeader
        else:
            raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttConnAckMsg.__name__, mqttConnAckMsg.__class__.__name__)) 

    def __encodePublishMsg(self, mqttPublishMsg):
        if(isinstance(mqttPublishMsg, MqttPublishMsg)):
            fixedHeader = mqttPublishMsg.fixedHeader
            topic = mqttPublishMsg.topic
            variableHeaderSize = 2 + len(topic) 
            if(fixedHeader.qos > 0):
                variableHeaderSize = variableHeaderSize + 2 
            encodedPayload = mqttPublishMsg.payload
            # Encode Variable Header
            encodedVariableHeader = self.__encodeIntShort(len(topic)) + self.__encodeStringUtf8(topic)
            if (fixedHeader.qos > 0): 
                encodedVariableHeader = encodedVariableHeader + self.__encodeIntShort(mqttPublishMsg.messageId)
            return self.__encodeFixedHeader(fixedHeader, variableHeaderSize, encodedPayload) + encodedVariableHeader + str(encodedPayload)
        else:
            raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttPublishMsg.__name__, mqttPublishMsg.__class__.__name__)) 
    
    def __encodeSubscribeMsg(self, mqttSubscribeMsg):
        if(isinstance(mqttSubscribeMsg, MqttSubscribeMsg)):
            fixedHeader = mqttSubscribeMsg.fixedHeader
            variableHeaderSize = 2
            # Encode Payload
            encodedPayload = ''
            topic = mqttSubscribeMsg.payload.get('topic')
            qos = mqttSubscribeMsg.payload.get('qos')
            encodedPayload = encodedPayload + self.__encodeIntShort(len(topic)) + self.__encodeStringUtf8(topic) + str(qos)
            # Encode Variable Header
            encodedVariableHeader = self.__encodeIntShort(mqttSubscribeMsg.messageId)
            return self.__encodeFixedHeader(fixedHeader, variableHeaderSize, encodedPayload) + encodedVariableHeader + encodedPayload
                
        else:
            raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttSubscribeMsg.__name__, mqttSubscribeMsg.__class__.__name__))
    
    def __encodeUnsubscribeMsg(self, mqttUnsubscribeMsg):
        if(isinstance(mqttUnsubscribeMsg, MqttUnsubscribeMsg)):
            fixedHeader = mqttUnsubscribeMsg.fixedHeader
            variableHeaderSize = 2
            # Encode Payload
            encodedPayload = ''
            for topic in mqttUnsubscribeMsg.payload:
                encodedPayload = encodedPayload + self.__encodeIntShort(len(topic)) + self.__encodeStringUtf8(topic)
            # Encode Variable Header
            encodedVariableHeader = self.__encodeIntShort(mqttUnsubscribeMsg.messageId)
            return self.__encodeFixedHeader(fixedHeader, variableHeaderSize, encodedPayload) + encodedVariableHeader + encodedPayload
        else:
            raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttUnsubscribeMsg.__name__, mqttUnsubscribeMsg.__class__.__name__))
    
    def __encodeSubAckMsg(self, mqttSubAckMsg):
        if(isinstance(mqttSubAckMsg, MqttSubAckMsg)):
            fixedHeader = mqttSubAckMsg.fixedHeader
            variableHeaderSize = 2
            # Encode Payload
            encodedPayload = ''
            for qos in mqttSubAckMsg.payload:
                encodedPayload = encodedPayload + str(qos)
            # Encode Variable Header
            encodedVariableHeader = self.__encodeIntShort(mqttSubAckMsg.messageId)
            return self.__encodeFixedHeader(fixedHeader, variableHeaderSize, encodedPayload) + encodedVariableHeader + encodedPayload
            
        else:
            raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttSubAckMsg.__name__, mqttSubAckMsg.__class__.__name__))
    
    def __encodeFixedHeaderAndMessageIdOnlyMsg(self, mqttMessage):
        msgType = mqttMessage.fixedHeader.messageType
        if(isinstance(mqttMessage, MqttUnsubscribeMsg) or isinstance(mqttMessage, MqttPubAckMsg) or isinstance(mqttMessage, MqttPubRecMsg) or isinstance(mqttMessage, MqttPubCompMsg) or isinstance(mqttMessage, MqttPubRelMsg)):
            fixedHeader = mqttMessage.fixedHeader
            variableHeaderSize = 2
            # Encode Variable Header
            encodedVariableHeader = self.__encodeIntShort(mqttMessage.messageId)
            return self.__encodeFixedHeader(fixedHeader, variableHeaderSize, None) + encodedVariableHeader
        else:
            if msgType == MqttClient.UNSUBACK: raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttUnsubAckMsg.__name__, mqttMessage.__class__.__name__))
            if msgType == MqttClient.PUBACK: raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttPubAckMsg.__name__, mqttMessage.__class__.__name__))
            if msgType == MqttClient.PUBREC: raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttPubRecMsg.__name__, mqttMessage.__class__.__name__))
            if msgType == MqttClient.PUBCOMP: raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttPubCompMsg.__name__, mqttMessage.__class__.__name__))
            if msgType == MqttClient.PUBREL: raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttPubRelMsg.__name__, mqttMessage.__class__.__name__))
    
    def __encodeFixedHeaderOnlyMsg(self, mqttMessage):
        msgType = mqttMessage.fixedHeader.messageType
        if(isinstance(mqttMessage, MqttPingReqMsg) or isinstance(mqttMessage, MqttPingRespMsg) or isinstance(mqttMessage, MqttDisconnetMsg)):
            return self.__encodeFixedHeader(mqttMessage.fixedHeader, 0, None)
        else:
            if msgType == MqttClient.PINGREQ: raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttPingReqMsg.__name__, mqttMessage.__class__.__name__))
            if msgType == MqttClient.PINGRESP: raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttPingRespMsg.__name__, mqttMessage.__class__.__name__))
            if msgType == MqttClient.DISCONNECT: raise TypeError('MqttEncoder: Expecting message object of type %s got %s' % (MqttDisconnetMsg.__name__, mqttMessage.__class__.__name__))
    
    def __encodeFixedHeader(self, fixedHeader, variableHeaderSize, encodedPayload):
        if encodedPayload is None:
            length = 0
        else: length = len(encodedPayload)
        encodedRemainingLength = self.__encodeRemainingLength(variableHeaderSize + length)
        return chr(self.__getFixedHeaderFirstByte(fixedHeader)) + encodedRemainingLength
    
    def __getFixedHeaderFirstByte(self, fixedHeader):
        firstByte = fixedHeader.messageType
        if (fixedHeader.dup):
            firstByte = firstByte | 0x08;
        firstByte = firstByte | (fixedHeader.qos << 1)
        if (fixedHeader.retain):
            firstByte = firstByte | 0x01
        return firstByte;
    
    def __encodeRemainingLength(self, num):
        remainingLength = ''
        while 1:
            digit = num % 128
            num = num / 128
            if (num > 0):
                digit = digit | 0x80
            remainingLength = remainingLength + chr(digit) 
            if(num == 0):
                    break
        return  remainingLength   
    
    def __encodeIntShort(self, number):  
        return chr(number / 256) + chr(number % 256)
    
    def __encodeStringUtf8(self, s):
        return str(s)
    
    def __isValidClientId(self, clientId):   
        if (clientId is None):
            return 0
        length = len(clientId)
        return length >= 1 and length <= 23
                     
        
class MqttFixedHeader:
    def __init__(self, messageType=None, qos=0, dup=0, retain=0, remainingLength=0):
        self.messageType = messageType or None
        self.dup = dup or 0
        self.qos = qos or 0
        self.retain = retain or 0
        self.remainingLength = remainingLength or 0
    
    def toString(self):
        return 'fixedHeader=[messageType=%s, dup=%d, qos=%d, retain=%d, remainingLength=%d]' % (str(self.messageType), self.dup, self.qos, self.retain, self.remainingLength)
        
class MqttMsg:
    def __init__(self, fixedHeader, variableHeader=None, payload=None):
        self.fixedHeader = fixedHeader
        self.variableHeader = variableHeader
        self.payload = payload
        
    def toString(self):
        return '%s[[%s] [variableHeader= %s] [payload= %s]]' % (self.__class__.__name__, self.fixedHeader.toString(), str(self.variableHeader), str(self.payload))
        

class MqttConnectMsg(MqttMsg):
    def __init__(self, fixedHeader, variableHeader, payload):
        MqttMsg.__init__(self, fixedHeader, variableHeader, payload)
        self.fixedHeader = fixedHeader
        self.protocolName = MqttClient.MQTT_PROTOCOL_NAME
        self.version = MqttClient.MQTT_PROTOCOL_VERSION
        self.hasUserName = variableHeader.get('hasUserName')
        self.hasPassword = variableHeader.get('hasPassword')
        self.clientId = payload.get('clientId')
        self.username = payload.get('username')
        self.password = payload.get('password')
        self.isWillRetain = variableHeader.get('isWillRetain')
        self.willQos = variableHeader.get('willQos')
        self.isWillFlag = variableHeader.get('isWillFlag')
        self.isCleanSession = variableHeader.get('isCleanSession')
        self.keepAliveTimer = variableHeader.get('keepAliveTimer')
        self.willTopic = payload.get('willTopic')
        self.willMessage = payload.get('willMessage')
        
class MqttConnAckMsg(MqttMsg):
    def __init__(self, fixedHeader, variableHeader):
        MqttMsg.__init__(self, fixedHeader, variableHeader)
        self.fixedHeader = fixedHeader
        self.__variableHeader = variableHeader
        self.connectReturnCode = variableHeader.get('connectReturnCode')
        self.payload = None
        
class MqttPingReqMsg(MqttMsg):
    def __init__(self, fixedHeader):
        MqttMsg.__init__(self, fixedHeader)
        self.fixedHeader = fixedHeader
        
class MqttPingRespMsg(MqttMsg):
    def __init__(self, fixedHeader):
        MqttMsg.__init__(self, fixedHeader)
        self.fixedHeader = fixedHeader
        
class MqttDisconnetMsg(MqttMsg):
    def __init__(self, fixedHeader):
        MqttMsg.__init__(self, fixedHeader)
        self.fixedHeader = fixedHeader
        
class MqttPubAckMsg(MqttMsg):
    def __init__(self, fixedHeader, variableHeader):
        MqttMsg.__init__(self, fixedHeader, variableHeader)
        self.fixedHeader = fixedHeader
        self.messageId = variableHeader.get('messageId')
        
class MqttPubRecMsg(MqttMsg):
    def __init__(self, fixedHeader, variableHeader):
        MqttMsg.__init__(self, fixedHeader, variableHeader)
        self.fixedHeader = fixedHeader
        self.messageId = variableHeader.get('messageId')
        
class MqttPubRelMsg(MqttMsg):
    def __init__(self, fixedHeader, variableHeader):
        MqttMsg.__init__(self, fixedHeader, variableHeader)
        self.fixedHeader = fixedHeader
        self.messageId = variableHeader.get('messageId')

class MqttPubCompMsg(MqttMsg):
    def __init__(self, fixedHeader, variableHeader):
        MqttMsg.__init__(self, fixedHeader, variableHeader)
        self.fixedHeader = fixedHeader
        self.messageId = variableHeader.get('messageId')

class MqttPublishMsg(MqttMsg):
    def __init__(self, fixedHeader, variableHeader, payload):
        MqttMsg.__init__(self, fixedHeader, variableHeader, payload)
        self.fixedHeader = fixedHeader
        self.messageId = variableHeader.get('messageId')
        self.topic = variableHeader.get('topic')
        # __payload bytes
        self.payload = payload

class MqttSubscribeMsg(MqttMsg):
    def __init__(self, fixedHeader, variableHeader, payload=[]):
        MqttMsg.__init__(self, fixedHeader, variableHeader, payload)
        self.fixedHeader = fixedHeader
        self.messageId = variableHeader.get('messageId')
        # __payload = [{"topic":"a/b","qos":1}]
        self.payload = payload

class MqttSubAckMsg(MqttMsg):
    def __init__(self, fixedHeader, variableHeader, payload=[]):
        MqttMsg.__init__(self, fixedHeader, variableHeader, payload)
        self.fixedHeader = fixedHeader
        self.messageId = variableHeader.get('messageId')
        # __payload = [0,1,2]
        self.payload = payload

class MqttUnsubscribeMsg(MqttMsg):
    def __init__(self, fixedHeader, variableHeader, payload=[]):
        MqttMsg.__init__(self, fixedHeader, variableHeader, payload)
        self.fixedHeader = fixedHeader
        self.messageId = variableHeader.get('messageId')
        # __payload = [topic0,topic1,topic2]
        self.payload = payload
        
class MqttUnsubAckMsg(MqttMsg):
    def __init__(self, fixedHeader, variableHeader):
        MqttMsg.__init__(self, fixedHeader, variableHeader)
        self.fixedHeader = fixedHeader
        self.messageId = variableHeader.get('messageId')

class MqttMsgFactory:
  
    def message(self, fixedHeader, variableHeader=None, payload=None):
        if fixedHeader.messageType == MqttClient.PINGREQ: 
            return MqttPingReqMsg(fixedHeader)
        elif fixedHeader.messageType == MqttClient.PINGRESP: 
            return MqttPingRespMsg(fixedHeader)
        elif fixedHeader.messageType == MqttClient.DISCONNECT: 
            return MqttDisconnetMsg(fixedHeader)
        elif fixedHeader.messageType == MqttClient.CONNECT:
            return MqttConnectMsg(fixedHeader, variableHeader, payload)
        elif fixedHeader.messageType == MqttClient.CONNACK: 
            return MqttConnAckMsg(fixedHeader, variableHeader)
        elif fixedHeader.messageType == MqttClient.PUBLISH: 
            return MqttPublishMsg(fixedHeader, variableHeader, payload)
        elif fixedHeader.messageType == MqttClient.SUBACK: 
            return MqttPubAckMsg(fixedHeader, variableHeader)
        elif fixedHeader.messageType == MqttClient.PUBREC: 
            return MqttPubRecMsg(fixedHeader, variableHeader)
        elif fixedHeader.messageType == MqttClient.PUBREL: 
            return MqttPubRelMsg(fixedHeader, variableHeader)
        elif fixedHeader.messageType == MqttClient.PUBCOMP: 
            return MqttPubCompMsg(fixedHeader, variableHeader)
        elif fixedHeader.messageType == MqttClient.SUBSCRIBE: 
            return MqttSubscribeMsg(fixedHeader, variableHeader, payload)
        elif fixedHeader.messageType == MqttClient.UNSUBSCRIBE: 
            return MqttUnsubscribeMsg(fixedHeader, variableHeader, payload)
        elif fixedHeader.messageType == MqttClient.SUBACK: 
            return MqttSubAckMsg(fixedHeader, variableHeader, payload)
        elif fixedHeader.messageType == MqttClient.UNSUBACK: 
            return MqttUnsubAckMsg(fixedHeader, variableHeader)
        else:
            return None

class MqttFrameError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class MqttDecoderError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)

class MqttEncoderError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)