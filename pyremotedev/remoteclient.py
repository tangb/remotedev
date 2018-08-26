#!/usr/bin/env python
# -*- coding: utf-8 -*-

from threading import Thread
import logging
from .models import RequestInfo, RequestCommand
import traceback
import socket
try:
    _unicode = unicode
except NameError:
    _unicode = str
import bson
import os
from .logs import RemoteLogHandler, LogFileWatcher
import io
import shutil

class RemoteClient(Thread):
    """
    Remote client thread handles request send by repository handler
    It will execute request commands on remote host.
    """

    LOG_HANDLER_DISABLED = 0
    LOG_HANDLER_INTERNAL = 1
    LOG_HANDLER_EXTERNAL = 2

    def __init__(self, ip, port, clientsocket, executor, debug, log_handler_mode=0, external_log_handler_file=None):
        """
        Constructor

        Args:
            ip (string): repository ip address
            port (int): repository connection port
            clientsocket (socket): socket instance returned by accept
            executor (RequestExecutor): RequestExecutor instance
            debug (bool): enable debug
            log_handler_mode (int): remote client log handler mode (default disabled). Use LOG_HANDLER_XXX modes
            external_log_handler_file (string): external log file to watch when LOG_HANDLER_EXTERNAL
        """
        Thread.__init__(self)
        Thread.daemon = True

        #members
        self.logger = logging.getLogger(self.__class__.__name__)
        if debug:
            self.logger.setLevel(logging.DEBUG)
        self.ip = ip
        self.port = port
        self.clientsocket = clientsocket
        self.clientsocket.settimeout(0.5)
        self.executor = executor
        self.buffer = Buffer(RequestCommand)
        self.running = True
        self.__log_handler = None
        self.log_handler_mode = log_handler_mode
        self.external_log_handler_file = external_log_handler_file
        self.__log_file_watcher = None

    def stop(self):
        """
        Stop process
        """
        self.logger.debug('Stop requested')
        self.running = False

    def send_log_record(self, record):
        """
        Send log to developper

        Args:
            record (LogRecord): log record to send
        """
        if self.clientsocket:
            #prepare request
            request = RequestInfo()
            if record.__dict__['exc_info']:
                msg = record.__dict__['msg'] + '\nTraceback (most recent call last):\n' + ''.join(traceback.format_tb(record.__dict__['exc_info'][2])) + type(record.__dict__['exc_info'][1]).__name__ + ': ' + record.__dict__['exc_info'][1].message
            else:
                msg = record.__dict__['msg']
            if len(msg)==0:
                #drop empty message
                self.logger.debug('Drop empty message')
                return
            request.log_record = {
                'name': record.__dict__['name'],
                'lvl': record.__dict__['levelno'],
                'fn': record.__dict__['filename'],
                'lno': record.__dict__['lineno'],
                'msg': msg,
                'args': None,
                'exc_info': None,
                'func': record.__dict__['funcName']
            }

            #send request
            try:
                if os.path.basename(__file__).startswith(record.filename):
                    #avoid infinite loop and useless logs from pyremotedev module
                    return

                #send log record
                #self.logger.debug('Send log from %s [%s]' % (record.name, record.filename))
                data = bson.dumps(request.to_dict())
                raw = '::LENGTH=%d::%s' % (len(data), data)
                #self.logger.debug('>>>>> socket send log record (%d bytes) %s' % (len(raw), request))
                if isinstance(raw, _unicode):
                    raw = raw.encode('utf-8')
                self.clientsocket.send(raw)

            except Exception:
                self.logger.exception(u'Exception during log sending:')
                #close remote client
                self.stop()

    def send_log_message(self, message):
        """
        Send log message

        Args:
            message (string): log message to send
        """
        if self.clientsocket and message and len(message)>0:
            #prepare request
            request = RequestInfo()
            request.log_message = message.strip()

            try:
                #send log message
                data = bson.dumps(request.to_dict())
                raw = '::LENGTH=%d::%s' % (len(data), data)
                if isinstance(raw, _unicode):
                    raw = raw.encode('utf-8')
                self.clientsocket.send(raw)

            except Exception:
                self.logger.exception(u'Exception during log sending:')
                #close remote client
                self.stop()

    def get_internal_log_handler(self):
        """
        Return logging.Handler instance to send log message to server

        Return:
            RemoteLogHandler: log handler
        """
        if not self.__log_handler:
            self.__log_handler = RemoteLogHandler(self.send_log_record)

        return self.__log_handler

    #def install_internal_remote_logging(self):
    #    """
    #    Install internal remote logging on root logger
    #    """
    #    root_logger = logging.getLogger()
    #    root_logger.addHandler(self.get_internal_log_handler())

    #def uninstall_internal_remote_logging(self):
    #    """
    #    Uninstall internal remote logging from root logger
    #    """
    #    if self.__log_handler:
    #        root_logger = logging.getLogger()
    #        root_logger.removeHandler(self.get_internal_log_handler())
        
    #def install_external_remote_logging(self):
    #    """
    #    Install external remote logging on root logger
    #    """
    #    self.__log_file_watcher = LogFileWatcher(self.external_log_handler_file, self.send_log_message)
    #    self.__log_file_watcher.start()
        
    #def uninstall_external_remote_logging(self):
    #    """
    #    Uninstall external remote logging from root logger
    #    """
    #    if self.__log_file_watcher:
    #        self.__log_file_watcher.stop()

    def run(self):
        """
        Main process: read data from socket and rebuild request.
        Then it send it to request executor instance
        """
        self.logger.debug(u'Connection of %s:%s' % (self.ip, self.port))

        #install log handler
        if self.log_handler_mode==self.LOG_HANDLER_INTERNAL:
            self.install_internal_remote_logging()

        elif self.log_handler_mode==self.LOG_HANDLER_EXTERNAL:
            if not os.path.exists(self.external_log_handler_file):
                raise Exception('Invalid log file specified (%s)' % self.external_log_handler_file)
            self.install_external_remote_logging()

        while self.running:
            try:
                raw = self.clientsocket.recv(1024)
                #self.logger.debug(u'<<<<< recv socket raw=%d bytes' % len(raw))

                #check end of connection
                if not raw:
                    self.logger.debug(u'Disconnection of %s:%s' % (self.ip, self.port))
                    break

                #process buffer with received raw data
                request = self.buffer.process(raw)
                if request:
                    self.executor.add_request(request)

            except socket.timeout:
                pass

            except Exception:
                self.logger.exception(u'Exception for %s:%s:' % (self.ip, self.port))

        #properly close server connection
        try:
            self.logger.debug(u'Send goodbye')
            request = RequestInfo()
            request.goodbye = True
            data = bson.dumps(request.to_dict())
            raw = '::LENGTH=%d::%s' % (len(data), data)
            #self.logger.debug('>>>>> socket send request (%d bytes) %s' % (len(raw), request))
            if isinstance(raw, _unicode):
                raw = raw.encode('utf-8')
            self.clientsocket.send(raw)

            #close socket
            if self.clientsocket:
                self.clientsocket.shutdown(socket.SHUT_WR)
                self.clientsocket.close()

        except Exception:
            pass

        #uninstall log handler
        if self.log_handler_mode==self.LOG_HANDLER_INTERNAL:
            self.uninstall_internal_remote_logging()

        elif self.log_handler_mode==self.LOG_HANDLER_EXTERNAL:
            self.uninstall_external_remote_logging()

        self.logger.debug(u'Thread stopped for %s:%s' % (self.ip, self.port))