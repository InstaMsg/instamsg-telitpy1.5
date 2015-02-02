# -*- coding: utf-8 -*-
import socket

class HTTPResponseError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class HTTPClientError(Exception):
    def __init__(self, value=''):
        self.value = value
    def __str__(self):
        return repr(self.value)
    
class HTTPResponse:
    __blanklines = ('\r\n', '\n', '') 
    __crlf = '\r\n'
    __continuationChar = '\t'
    __whitespace = " " 
    __readingStatusline = 0
    __readingHeaders = 1
    __readingBody = 2
    __ok = 3
    __continue = 100
    
    def __init__(self, sock, f=None):
        self.__sock = sock
        self.f = f

        
    def response(self):  
        try:
            self.__init()
#             data_block = self.__sock.recv()
            data_block = self.__sock.recv(1500)
            while(data_block):
                self.__lines = self.__lines + data_block.split(self.__crlf)
                if(len(self.__lines) > 0):
                    if(self.state == self.__readingStatusline):
                        self.__readStatus()
                        # read till we get a non conitnue (100) response
                        if(self.__state == self.__continue): 
                            self.__state = self.__readingStatusline
                            break
#                             data_block = self.__sock.recv(1500)
                    if(self.__state == self.__readingHeaders):
                        self.__readHeaders()
                    if(self.__readingBody):
                        self.__readBody() 
                        break
                if(self.__sock is not None):
#                     data_block = self.__sock.recv()
                    data_block = self.__sock.recv(1500)
                if not data_block:
                    break
        except Exception, e:
            raise HTTPResponseError(str(e))
        return self

    def end(self):
        try:
            if(self.__sock):
                self.__sock.close()
                self.__sock = None
        except:
            pass
        
    def __init(self):
        self.protocol = None
        self.version = None
        self.status = None
        self.reason = None
        self.length = None
        self.close = None 
        self.headers = {}
        self.body = ""  
        self.state = self.__readingStatusline
        self.__lines = []
        self.__lastHeader = None
        
    def __readStatus(self):
        try:
            statusLine = self.__lines.pop(0)
            [version, status, reason] = statusLine.split(None, 2)
        except ValueError:
            try:
                [version, status] = statusLine.split(None, 1)
                reason = ""
            except ValueError:
                version = ""
        if not version.startswith('HTTP/'):
            raise HTTPResponseError("Invalid HTTP version in response")
        try:
            status = int(status)
            if status < 100 or status > 999:
                raise HTTPResponseError("HTTP status code out of range 100-999.")
        except ValueError:
            raise HTTPResponseError("Invalid HTTP status code.")
        self.status = status
        self.reason = reason.strip()
        try:
            [protocol, ver] = version.split("/", 2)
        except ValueError:
            raise HTTPResponseError("Invalid HTTP version.")
        self.protocol = protocol
        self.version = ver
        if(self.status == self.__continue): 
            self.__state = self.__continue
        else:
            self.__state = self.__readingHeaders
            
        
    def __readHeaders(self):
        n = len(self.__lines)
        i = 0
        while i < n:
            line = self.__lines.pop(0)
            if(self.__islastLine(line)):
                self.state = self.__readingBody
                break
            if(self.__isContinuationLine(line)):
                [a, b] = line.split(self.__continuationChar, 2)
                self.headers[self.__lastHeader].append(b.strip()) 
            else:
                headerTuple = self.__getHeader(line)
                if(headerTuple):
                    self.headers[headerTuple[0]] = headerTuple[1]
                    self.__lastHeader = headerTuple[0]
            i = i + 1
            
    def __islastLine(self, line):
        return line in self.__blanklines
    
    def __isContinuationLine(self, line):
        if(line.find(self.__continuationChar) > 0): return 1
        else: return 0
    
    def __getHeader(self, line):
        i = line.find(':')
        if i > 0:
            header = line[0:i].lower()
            if(i == len(line)):
                headerValue = []
            else:
                headerValue = line[(i + 1):len(line)].strip()
            if(header == 'content-length' and headerValue):
                try:
                    self.length = int(headerValue)
                except ValueError:
                    self.length = None
                else:
                    if self.length < 0:
                        self.length = None   
            return (header, headerValue)
        return None
    
    def __readBody(self):
        try:
            try:
                if(self.length and self.length != 0 and (self.__lines or self.__sock)):
        #             datablock = self.__sock.recv()
                    if(self.__lines):
                        datablock = self.__lines
                        self.__lines = None
                    else:
                        datablock = self.__sock.recv(1500)
                    length = 0
                    while(datablock and length < self.length):
                        if(isinstance(datablock, list)):
                            datablock = ''.join(datablock)
                        length = length + len(datablock)
                        # Only download body to file if status 200
                        if (self.status == 200 and self.f and hasattr(self.f, 'write')):  
                            self.f.write(datablock)
                        else:
                            self.body = self.body + datablock
    #                     datablock = self.__sock.recv()
                        if(length < self.length):
                            datablock = self.__sock.recv(1500)
                        else: break
                    self.end()
                else:
                    self.end()
            except Exception, e:
                raise Exception(str(e))
        finally:
            self.end()
    
class HTTPClient:
        
    def __init__(self, host, port, userAgent='InstaMsg'):
        self.version = '1.1'
        self.__userAgent = userAgent
        self.__addr = (host, port)
        self.__sock = None
        self.__checkAddress()
        self.__boundary = '-----------ThIs_Is_tHe_bouNdaRY_78564$!@'
        self.__tcpBufferSize = 1500
        
    def get(self, url, params={}, headers={}, body=None, timeout=10):
        return self.__request('GET', url, params, headers, body, timeout)
    
    def put(self, url, params={}, headers={}, body=None, timeout=10):
        return self.__request('PUT', url, params, headers, body, timeout)
    
    def post(self, url, params={}, headers={}, body=None, timeout=10):
        return self.__request('POST', url, params, headers, body, timeout)  
    
    def delete(self, url, params={}, headers={}, body=None, timeout=10):
        return self.__request('DELETE', url, params, headers, body, timeout) 
        
    def uploadFile(self, url, filename, params={}, headers={}, timeout=10):
        if(not isinstance(filename, str)): raise ValueError('HTTPClient:: upload filename should be of type str.')
        f = None
        try:
            try:
                headers['Content-Type'] = 'multipart/form-data; boundary=%s' % self.__boundary
                form = self.__encode_multipart_fileupload("file", filename)
                fileSize = self.__getFileSize(filename)
                headers['Content-Length'] = len(''.join(form)) + fileSize
                f = open(filename, 'rb')
                return self.__request('POST', url, params, headers, f, timeout, form)  
            except Exception, e:
                if(e.__class__.__name__ == 'HTTPResponseError'):
                    raise HTTPResponseError(str(e))
                raise HTTPClientError("HTTPClient:: %s" % str(e))
        finally:
            self.__closeFile(f)  
    
    def downloadFile(self, url, filename, params={}, headers={}, timeout=10):  
        if(not isinstance(filename, str)): raise ValueError('HTTPClient:: download filename should be of type str.')
        f = None
        response = None
        try:
            try:
                tempFileName = '~' + filename
                f = open(tempFileName, 'wb')
                response = self.__request('GET', url, params, headers, timeout=timeout, fileObject=f)
                f.close()
                if(response.status == 200):
                    rename(tempFileName, filename)
                else:
                    unlink(tempFileName)
            except Exception, e:
                if(e.__class__.__name__ == 'HTTPResponseError'):
                    raise HTTPResponseError(str(e))
                raise HTTPClientError("HTTPClient:: %s" % str(e))
        finally:
            self.__closeFile(f)
        return response
            
    def __closeFile(self, f):   
        try:
            if(f and hasattr(f, 'close')):
                f.close() 
                f = None      
        except:
            pass 
          
    def __getFileSize(self, filename):
        fileSize = None
        try:
            try:
                f = open(filename, 'ab')
                f.seek(0, 2)
                fileSize = f.tell()
            except Exception, e:
                raise Exception(str(e))
        finally:
            if(f and hasattr(f, 'close')):
                f.close()
                f = None
        if(fileSize): return fileSize
        else: raise Exception("HTTPClient:: Unable to determine file size.")
            
    
    def __request(self, method, url, params, headers, body=None, timeout=10, fileUploadForm=None, fileObject=None):
        if(not isinstance(url, str)): raise ValueError('HTTPClient:: url should be of type str.')
        if(not isinstance(params, dict)): raise ValueError('HTTPClient:: params should be of type dictionary.')
        if(not isinstance(headers, dict)): raise ValueError('HTTPClient:: headers should be of type dictionary.')
        if(not isinstance(timeout, int)): raise ValueError('HTTPClient:: timeout should be of type int.')
        if(not(isinstance(body, str) or isinstance(body, file) or body is None)):raise ValueError('HTTPClient:: body should be of type string or file object.')
        try:
            try:
                request = self.__createHttpRequest(method, url, params, headers)
                sizeHint = None
                if(headers.has_key('Content-Length') and isinstance(body, file)):
                    sizeHint = len(request) + headers.get('Content-Length')
                self._sock = socket.Socket(timeout, 0)
                self._sock.connect(self.__addr)
                expect = None
                if(headers.has_key('Expect')):
                    expect = headers['Expect']
                elif(headers.has_key('expect')):
                    expect = headers['expect']
                if(expect and (expect.lower() == '100-continue')):
                    self._sock.sendall(request)
                    httpResponse = HTTPResponse(self._sock, fileObject).response()
                    # Send the remaining body if status 100 received or server that send nothing
                    if(httpResponse.status == 100 or httpResponse.status is None):
                        request = ""
                        self.__send(request, body, fileUploadForm, fileObject, sizeHint)
                        return httpResponse.response()
                    else:
                        raise HTTPResponseError("Expecting status 100, recieved %s" % request.status)
                else:
                    self.__send(request, body, fileUploadForm, fileObject, sizeHint)
                    return HTTPResponse(self._sock, fileObject).response()
            except Exception, e:
                if(e.__class__.__name__ == 'HTTPResponseError'):
                    raise HTTPResponseError(str(e))
                raise HTTPClientError("HTTPClient:: %s" % str(e))
        finally:
            try:
                if(self.__sock):
                    self.__sock.close()
                    self.__sock = None
            except:
                pass
    
    def __send(self, request, body=None, fileUploadForm=None, fileObject=None, sizeHint=None):
        if (isinstance(body, str) or body is None): 
            request = request + (body or "")
            if(request):
                self._sock.sendall(request)
        else:
            if(fileUploadForm and len(fileUploadForm) == 2):
                blocksize = 1500    
                if(sizeHint <= self.__tcpBufferSize):
                    if hasattr(body, 'read'): 
                        request = request + ''.join(fileUploadForm[0]) + ''.join(body.read(blocksize)) + ''.join(fileUploadForm[1])
                        self._sock.sendall(request)
                else:
                    request = request + ''.join(fileUploadForm[0])
                    self._sock.sendall(request)
                    partNumber = 1
                    if hasattr(body, 'read'): 
                        partData = body.read(blocksize)
                        while partData:
        #                             self._sock.sendMultiPart(partData, partNumber)
                            self._sock.sendall(partData)
                            partData = body.read(blocksize)
                    if(fileUploadForm and len(fileUploadForm) == 2):
        #                         self._sock.sendMultiPart(fileUploadForm[1], partNumber + 1)
                        self._sock.sendall(fileUploadForm[1])
        #                 self._sock.sendHTTP(self.__addr, request)
    
    def __createHttpRequest(self, method, url, params={}, headers={}):
        url = url + self.__createQueryString(params)
        headers = self.__createHeaderString(headers)
        request = "%s %s %s" % (method, url, headers)
        return request
        
    def __createQueryString(self, params={}):
        i = 0
        query = ''
        for key, value in params.items():
            if(i == 0): 
                query = query + '?%s=%s' % (str(key), str(value))
                i = 1
            else:
                query = query + "&%s=%s" % (str(key), str(value))
        return query
    
    def __createHeaderString(self, headers={}): 
            headerStr = "HTTP/%s\r\nHost: %s\r\n" % (self.version, self.__addr[0])
            headers['Connection'] = 'close'  # Only close is supported
            headers['User-Agent'] = self.__userAgent
            for header, values in headers.items():
                x = []
                if(isinstance(values, list)):
                    for v in values:
                        x.append(str(v))
                    headerStr = headerStr + "%s: %s\r\n" % (header, '\r\n\t'.join(x))
                else:
                    headerStr = headerStr + "%s: %s\r\n" % (str(header), str(values))
            return headerStr + "\r\n"
        
    def __encode_multipart_fileupload(self, fieldname, filename, contentType='application/octet-stream'):
        formPrefix = []
        crlf = '\r\n'
        formPrefix.append("--" + self.__boundary)
        formPrefix.append('Content-Disposition: form-data; name="%s"; filename="%s"' % (fieldname, filename))
        formPrefix.append('Content-Type: %s' % contentType)
        formPrefix.append('')
        formPrefix.append('')
        return (crlf.join(formPrefix), (crlf + '--' + self.__boundary + '--' + crlf))
            
    def __checkAddress(self):
        if (not self.__addr[0] and not self.__addr[1] and not isinstance(self._addr[1], int)):
            raise ValueError("HTTPClient:: Not a valid HTTP host or port value: %s, %d" % (self.__addr[0], self.__addr[1]))
            
