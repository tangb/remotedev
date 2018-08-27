#!/usr/bin/env python
# -*- coding: utf-8 -*-

from threading import Thread
from collections import deque
import logging
from sshtunnel import SSHTunnelForwarder
import socket
from .consts import TEST_REQUEST
import time
import bson
bson.patch_socket()
from .request import REQUEST_FILE, REQUEST_GOODBYE, REQUEST_LOG, REQUEST_PING, REQUEST_UNKNOW, REQUEST_PONG, RequestFile, RequestGoodbye, RequestLog, RequestPing, RequestPong
from .file import RequestFileExecutor
from .logs import RequestLogExecutor, RequestLogCreator

try:
    _unicode = unicode
except NameError:
    _unicode = str

class SynchronizerExecEnv(Thread):
    def __init__(self, ip, port, clientsocket, mappings, log_file_path, debug):
        """
        Constructor
        """
        Thread.__init__(self)
        Thread.daemon = True

        #members
        self.logger = logging.getLogger(self.__class__.__name__)
        if debug:
            self.logger.setLevel(logging.DEBUG)
        self.running = True
        self.ip = ip
        self.port = port
        self.socket = clientsocket
        self.__socket_connected = False
        self.__send_socket_attemps = 0
        self.mappings = mappings
        self.log_file_path = log_file_path
        self.request_file_executor = None
        self.request_log_creator = None
        self.__history = deque(maxlen=4)

    def __del__(self):
        """
        Destructor
        """
        self.stop()

    def __disconnect_socket(self):
        """
        Disconnect socket
        """
        if self.socket:
            self.socket.close()
        self.__socket_connected = False

    def disconnect(self):
        """
        Disconnect from remote both tunnel and socket)
        """
        self.__disconnect_socket()

    def __request_file_already_sent(self, request):
        """
        Check if request has been already sent using history

        Returns:
            bool: True if already sent
        """
        for history in list(self.__history):
            if request.action == history.action and request.src == history.src and len(request.content) == len(history.content):
                return True

        return False

    def add_request(self, request):
        """
        Add request to queue. The request will be processed as soon as possible

        Args:
            request (Request): request instance
        """
        self.logger.debug(u'Request received, send it to remote: %s' % request)

        #avoid infinite loop with RequestFile requests
        if self.__request_file_already_sent(request):
            self.logger.debug(u' ==> Request dropped to avoid infinite loop: %s' % request)
            return

        self.__send_request_to_remote(request)

    def __send_request_to_remote(self, request):
        """
        Send request to remote

        Args:
            request (Request): request instance

        Return:
            bool: False if remote is not connected
        """
        try:
            #send bsonified request
            self.socket.sendobj(request.to_dict())
            self.__send_socket_attemps = 0

            self.logger.info(request.log_str())

            return True

        except Exception:
            logging.exception(u'Send request exception:')

            #sending problem watchdog
            self.__send_socket_attemps += 1
            if self.__send_socket_attemps > 10:
                self.logger.critical('Too many sending attempts. Surely a unhandled bug, Please relaunch application with debug enabled and add new issue in repository joining debug output. Thank you very much.')
                self.stop()

            #disconnect all, it will reconnect after next try
            self.disconnect()

        return False

    def stop(self):
        """
        Stop synchronizer
        """
        self.running = False

        if self.request_file_executor:
            self.request_file_executor.stop()

        if self.request_log_creator:
            self.request_log_creator.stop()

    def run(self):
        """
        Main process: read data from socket and rebuild request.
        Then it send it to request executor instance
        """
        self.logger.debug(u'SynchronizerExecEnv started for %s:%s' % (self.ip, self.port))
        self.__socket_connected = True

        #create RequestFileExecutor
        self.request_file_executor = RequestFileExecutor(self.mappings)
        self.request_file_executor.start()

        #create RequestLogCreator
        self.request_log_creator = RequestLogCreator(self.__send_request_to_remote, self.log_file_path)
        self.request_log_creator.start()

        receive_attempts = 0
        while self.running:
            #receive data
            try:
                #receive de bsonified request
                req = self.socket.recvobj()
                if req:
                    self.logger.debug('Received request %s' % req)

                    #process request type
                    if req[u'_type'] == REQUEST_UNKNOW:
                        #invalid request
                        self.logger.error(u'Invalid request received')

                    elif req[u'_type'] == REQUEST_PING:
                        #received ping request, answer pong
                        self.logger.error(u'Receive ping request, answer pong')
                        request = RequestPong()
                        self.socket.sendobj(request.to_dict())

                    elif req[u'_type'] == REQUEST_LOG:
                        #received log request
                        self.logger.debug(u'Not supposed receiving RequestLog :s. Request droped')
            
                    elif req[u'_type'] == REQUEST_FILE:
                        #received file request
                        request = RequestFile()
                        request.from_dict(req)

                        #append to history
                        self.__history.append(request)

                        self.logger.debug('Process RequestFile action')
                        self.request_file_executor.add_request(request)

                    elif req[u'_type'] == REQUEST_GOODBYE:
                        #client disconnect, force server disconnection to allow new connection
                        #here no need to create new RequestGoodbye object
                        self.logger.debug('Process RequestGoodbye request')
                        self.logger.info(u'Remote is disconnected')
                        self.stop()

                else:
                    #nothing received, pause
                    receive_attempts += 1
                    time.sleep(0.25)

                    if receive_attempts>=8:
                        #problem with connection, close it
                        raise Exception(u'Connection with remote seems to be lost. Disconnect.')

            except socket.timeout:
                pass

            except:
                #error on socket. disconnect
                if self.logger.getEffectiveLevel() == logging.DEBUG:
                    self.logger.exception('Exception on execution env process:')
                self.stop()

        self.logger.debug(u'SynchronizerExecEnv terminated for %s:%s' % (self.ip, self.port))






class SynchronizerDevEnv(Thread):
    """
    Synchronizer is in charge to send requests to remote throught ssh tunnel.
    It handles connection and reconnection with remote.
    A buffer keeps track of changes when remote is disconnected.
    """
    def __init__(self, remote_host, remote_port, ssh_username, ssh_password, source_code_dir, debug, forward_port=52666):
        """
        Constructor

        Args:
            remote_host (string): remote ip address
            remote_port (int): remote port
            ssh_username (string): ssh username
            ssh_password (string): ssh password
            source_code_dir (string): source code directory
            debug (bool): debug instance or not
            forward_port (int): forwarded port (default is 52666)
        """
        Thread.__init__(self)
        Thread.daemon = True

        #members
        self.logger = logging.getLogger(self.__class__.__name__)
        if debug:
            self.logger.setLevel(logging.DEBUG)
        self.running = True
        self.__tunnel_opened = False
        self.__socket_connected = False
        self.remote_host = remote_host
        self.remote_port = remote_port
        self.ssh_username = ssh_username
        self.ssh_password = ssh_password
        self.forward_port = forward_port
        self.__queue = deque(maxlen=200)
        self.tunnel = None
        self.socket = None
        self.__send_socket_attemps = 0
        self.source_code_dir = source_code_dir
        self.debug = debug
        self.__history = deque(maxlen=4)

    def __del__(self):
        """
        Destructor
        """
        self.stop()

    def __open_tunnel(self):
        """
        Open tunnel

        Return:
            bool: True if tunnel opened successfully
        """
        try:
            self.logger.debug('opening tunnel on %s:%s with username=%s pwd=%s forward_port=%d' % (self.remote_host, self.remote_port, self.ssh_username, self.ssh_password, self.forward_port))
            self.tunnel = SSHTunnelForwarder(
                (self.remote_host, self.remote_port),
                ssh_username=self.ssh_username,
                ssh_password=self.ssh_password,
                remote_bind_address=(u'127.0.0.1', self.forward_port)
            )
            self.tunnel.start()
            self.__tunnel_opened = True

            return True

        except Exception:
            self.logger.exception(u'Tunnel exception:')
            self.__tunnel_opened = False

        return False

    def __connect_socket(self):
        """
        Connect socket

        Return:
            bool: True if socket connected successfully
        """
        try:
            if self.tunnel and self.tunnel.is_active:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(0.5)
                self.socket.connect((u'127.0.0.1', self.tunnel.local_bind_port))

                #test if remote service is really running
                self.logger.debug(u'Testing connection sending PING...')
                ping = RequestPing()
                self.socket.sendobj(ping.to_dict())
                req = self.socket.recvobj()
                if req and req[u'_type'] == REQUEST_PONG:
                    self.logger.debug(u'Received PONG, connection is ok')
                    self.__socket_connected = True

            else:
                #disconnected tunnel ?
                return False

        except Exception:
            if self.logger.getEffectiveLevel() == logging.DEBUG:
                self.logger.exception(u'Socket exception:')
            self.__socket_connected = False

        return self.__socket_connected

    def connect(self):
        """
        Connect to remote

        Return:
            bool: True if connection is successful
        """
        if not self.__tunnel_opened:
            #open tunnel
            if self.__open_tunnel():
                #connect socket
                if self.__connect_socket():
                    self.logger.debug(u'Socket connected')
                    return True

            #unable to open tunnel or connect socket
            self.logger.debug(u'Unable to open tunnel or connect socket (please check your credentials)')
            return False

        else:
            #tunnel opened, connect socket
            if self.__connect_socket():
                return True

            #unable to connect socket
            self.logger.debug(u'Unable to connect socket')
            return False

    def __close_tunnel(self):
        """
        Close tunnel
        """
        if self.tunnel:
            self.tunnel.stop()
        self.__tunnel_opened = False

    def __disconnect_socket(self):
        """
        Disconnect socket
        """
        if self.socket:
            self.socket.close()
        self.__socket_connected = False

    def disconnect(self):
        """
        Disconnect from remote both tunnel and socket)
        """
        self.__disconnect_socket()
        self.__close_tunnel()

    def is_connected(self):
        """
        Return connection status

        Return:
            bool: True if connected to remote
        """
        return self.__tunnel_opened and self.__socket_connected

    def __request_file_already_sent(self, request):
        """
        Check if request has been already sent using history

        Returns:
            bool: True if already sent
        """
        for history in list(self.__history):
            if request.action == history.action and request.src == history.src and len(request.content) == len(history.content):
                return True

        return False

    def add_request(self, request):
        """
        Add request to queue. The request will be processed as soon as possible

        Args:
            request (Request): request instance
        """
        self.logger.debug(u'Request added %s' % request)

        #avoid infinite loop with RequestFile requests
        if self.__request_file_already_sent(request):
            self.logger.debug(u' ==> Request dropped to avoid infinite loop: %s' % request)
            return

        #self.__queue.appendleft(request)
        self.__send_request_to_remote(request)

    def __send_request_to_remote(self, request):
        """
        Send request to remote

        Args:
            request (Request): request instance

        Return:
            bool: False if remote is not connected
        """
        try:
            #send bsonified request
            self.socket.sendobj(request.to_dict())
            self.__send_socket_attemps = 0

            self.logger.debug(u'Request sent: %s' % request.log_str())

            return True

        except:
            logging.exception(u'Send request exception:')

            #sending problem watchdog
            self.__send_socket_attemps += 1
            if self.__send_socket_attemps > 10:
                self.logger.critical('Too many sending attempts. Surely a unhandled bug, Please relaunch application with debug enabled and add new issue in repository joining debug output. Thank you very much.')
                self.stop()

            #disconnect all, it will reconnect after next try
            self.disconnect()

        return False

    def stop(self):
        """
        Stop synchronizer
        """
        self.running = False

    def run(self):
        """
        Main process
        """
        self.logger.debug(u'SynchronizerDevEnv started')

        #create RequestFileExecutor
        self.request_file_executor = RequestFileExecutor(self.source_code_dir)
        self.request_file_executor.start()

        #create RequestFileExecutor
        self.request_log_executor = RequestLogExecutor(self.remote_host)
        self.request_log_executor.start()

        receive_attempts = 0
        while self.running:
            can_send = False
            if not self.is_connected():
                if self.connect():
                    can_send = True
                    self.logger.info(u'------------------------------------------------------')
                    self.logger.info(u'Connected. Ready to synchronize files (CTRL-C to stop)')
                    self.logger.info(u'------------------------------------------------------')
            else:
                #already connected
                can_send = True

            if not can_send:
                #not connected, retry
                self.logger.debug(u'Not connected, retry in 2 seconds')
                time.sleep(2.0)
                continue

            if not self.running:
                break

            #try:
            #    req = self.__queue.pop()
            #    if not self.__send_request_to_remote(req):
            #        #failed to send request, insert again the request for further retry
            #        self.__queue.append(req)
            #except IndexError:
            #    #no request available
            #    pass

            #receive data
            try:
                #receive request
                req = self.socket.recvobj()
                if req:
                    self.logger.debug('Received request %s' % req)

                    #process request type
                    if req[u'_type'] == REQUEST_UNKNOW:
                        #invalid request
                        self.logger.error(u'Invalid request received')

                    elif req[u'_type'] == REQUEST_LOG:
                        #received log request
                        request = RequestLog()
                        request.from_dict(req)

                        self.logger.debug(u'Process RequestLog request')
                        self.request_log_executor.add_request(request)
            
                    elif req[u'_type'] == REQUEST_FILE:
                        #received file request
                        request = RequestFile()
                        request.from_dict(req)

                        #append to history
                        self.__history.append(request)

                        self.logger.debug('Process RequestFile request')
                        self.request_file_executor.add_request(request)

                    elif req[u'_type'] == REQUEST_GOODBYE:
                        #client disconnect, force server disconnection to allow new connection
                        #here no need to create new RequestGoodbye object
                        self.logger.debug('Process RequestGoodbye request')
                        self.logger.info(u'Remote is disconnected')
                        self.disconnect()

                else:
                    #nothing received, pause
                    receive_attempts += 1
                    time.sleep(0.25)

                    if receive_attempts>=8:
                        #problem with connection, close it
                        raise Exception(u'Connection with remote seems to be lost. Disconnect.')

            except socket.timeout:
                pass

            except Exception:
                #error on socket. disconnect
                if self.logger.getEffectiveLevel() == logging.DEBUG:
                    self.logger.exception('Exception on server process:')
                self.disconnect()

        #clear queue content
        #self.__queue.clear()

        #disconnect
        self.disconnect()

        #stop executors
        if self.request_file_executor:
            self.request_file_executor.stop()
        if self.request_log_executor:
            self.request_log_executor.stop()

        self.logger.debug(u'SynchronizerDevEnv terminated')
