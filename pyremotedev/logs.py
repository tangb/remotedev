#!/usr/bin/env python
# -*- coding: utf-8 -*-

from threading import Thread
from pygtail import Pygtail
import logging
import time
from .request import RequestLog
import os
import traceback
from logging.handlers import RotatingFileHandler

class LogFileWatcher(Thread):
    """
    Log file watcher (kind of tailf on specified file)

    See:
        Code from http://www.dabeaz.com/generators/follow.py
    """

    def __init__(self, log_file_path, send_log_callback):
        """
        Constructor

        Args:
            log_file_path (string): path to file to watch
            send_log_callback (function): callback to send log message
        """
        Thread.__init__(self)
        Thread.daemon = True

        #members
        self.running = True
        self.log_file_path = log_file_path
        self.send_log_callback = send_log_callback
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)
        self.logger.debug('Tail on %s' % self.log_file_path)

    def stop(self):
        """
        Stop thread
        """
        self.running = False

    def run(self):
        """
        Main process
        """
        self.logger.debug('Thread started')
        try:
            #purge new lines
            Pygtail(self.log_file_path).readlines()

            #handle new lines
            while self.running:
                try:
                    for log_line in Pygtail(self.log_file_path):
                        if isinstance(log_line, str):
                            log_line = log_line.decode('utf-8')
                        log_line = log_line.strip()
                        self.logger.debug('New log line: %s' % log_line)
                        self.send_log_callback(log_line)
    
                    #pause 
                    time.sleep(0.5)

                except:
                    self.logger.exception(u'Exception on log watcher:')

        except:
            self.logger.exception(u'Fatal exception on log watcher:')

        self.logger.debug(u'Thread stopped')





class RemoteDevLogHandler(logging.Handler):
    """
    Catch logs and send them to developper console
    """
    def __init__(self, send_callback):
        """
        Constructor
        """
        logging.Handler.__init__(self)

        #members
        self.send_callback = send_callback

    def emit(self, record):
        """
        Emit log: send log record to developper environment

        Args:
            record (LogRecord): log record
        """
        self.send_callback(record)





class RequestLogCreator(Thread):
    """
    This class is in charge to create RequestLog requests.

    
    It is in charge to perform file synchronisation between both filesystem using received requests
    """

    MODE_DISABLED = 0
    MODE_INTERNAL = 1
    MODE_EXTERNAL = 2

    def __init__(self, send_request_callback, log_file_path=False, debug=False):
        """
        Constructor

        Args:
            send_request_callback (function): function to send request to client
            log_file_path (string): If False log handling is disabled, if None application log is handled, if path log file content is watched
            debug (bool): enable debug
        """
        Thread.__init__(self)
        Thread.daemon = True

        #members
        self.logger = logging.getLogger(self.__class__.__name__)
        if debug:
            self.logger.setLevel(logging.DEBUG)
        self.running = True
        self.log_file_path = log_file_path
        self.__log_file_watcher = None
        self.__log_handler = None
        self.__log_file_watcher = None
        self.send_request_callback = send_request_callback

    def send_log_record(self, record):
        """
        Send log record

        Args:
            record (LogRecord): log record to send
        """
        #prepare request
        request = RequestLog()
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
        self.send_request_callback(request)

    def send_log_message(self, message):
        """
        Send log message

        Args:
            message (string): log message to send
        """
        #prepare request
        request = RequestLog()
        request.log_message = message.strip()

        #drop message if empty
        if request.is_empty():
            self.logger.debug(u'Drop empty log request')
            return

        #send request
        self.send_request_callback(request)

    def __get_internal_log_handler(self):
        """
        Return logging.Handler instance to send log message to server

        Return:
            RemoteDevLogHandler: log handler
        """
        if not self.__log_handler:
            self.__log_handler = RemoteDevLogHandler(self.send_log_record)

        return self.__log_handler

    def __install_internal_remote_logging(self):
        """
        Install internal remote logging on root logger
        """
        root_logger = logging.getLogger()
        root_logger.addHandler(self.__get_internal_log_handler())

    def __uninstall_internal_remote_logging(self):
        """
        Uninstall internal remote logging from root logger
        """
        if self.__log_handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(self.__get_internal_log_handler())
        
    def __install_external_remote_logging(self, path):
        """
        Install external remote logging on root logger
        """
        self.__log_file_watcher = LogFileWatcher(path, self.send_log_message)
        self.__log_file_watcher.start()
        
    def __uninstall_external_remote_logging(self):
        """
        Uninstall external remote logging from root logger
        """
        if self.__log_file_watcher:
            self.__log_file_watcher.stop()

    def __install_log(self):
        """
        Method to configure log handler
        """
        if self.log_file_path == False:
            #log handling disabled
            self.__mode = self.MODE_DISABLED

        elif self.log_file_path == None:
            #handle log from application (libray mode)
            self.__mode = self.MODE_INTERNAL
            self.__install_internal_remote_logging()

        else:
            #check specified file path
            if not os.path.exists(self.log_file_path):
                self.logger.error(u'Specified log file "%s" doesn\'t exist. Log handling disabled.' % self.log_file_path)
                self.__mode = self.MODE_DISABLED
            else:
                self.__mode = self.MODE_EXTERNAL
                self.__install_external_remote_logging(self.log_file_path)

    def __uninstall_log(self):
        if self.__mode == self.MODE_INTERNAL:
            self.__uninstall_internal_remote_logging()
        elif self.__mode == self.MODE_EXTERNAL:
            self.__uninstall_external_remote_logging()

    def stop(self):
        """
        Stop process
        """
        self.logger.debug('Stop requested')
        self.running = False

    def run(self):
        #install log
        self.__install_log()

        while self.running:
            time.sleep(0.25)

        #install log
        self.__uninstall_log()





class RequestLogExecutor():
    """
    This class executes actions when receiving RequestLog
    """

    def __init__(self, base_dir, remote_host, debug=False):
        """
        Constructor

        Args:
            base_dir (string): directory of source (place used to store log file)
            remote_host (string): remote host
            debug (bool): enable debug
        """
        #members
        self.logger = logging.getLogger(self.__class__.__name__)
        if debug:
            self.logger.setLevel(logging.DEBUG)
        self.remote_logger = None
        self.remote_host = remote_host
        self.base_dir = base_dir

    def stop(self):
        """
        Stop process
        """
        self.logger.debug('Stop requested')

    def start(self):
        """
        Configure class
        """
        self.init_remote_logger()

    def init_remote_logger(self):
        """
        Init remote logger (logger on development env)
        """
        #create new handler
        path = os.path.join(self.base_dir, 'remote_%s.log' % self.remote_host)
        handler = RotatingFileHandler(path, maxBytes=2048000, backupCount=2, encoding='utf-8')
        formatter = logging.Formatter('%(message)s')
        handler.setFormatter(formatter)
        
        #create new remote logger
        self.remote_logger = logging.getLogger('RemoteLog')
        self.remote_logger.handlers = [handler]
        self.remote_logger.setLevel(logging.INFO)

    def add_request(self, request):
        """
        Add specified request to queue

        Args:
            request (Request): request instance
        """
        if request.log_record:
            #it's an exception record
            self.logger.debug('Process RequestLog log record')
            record = self.remote_logger.makeRecord(
                request.log_record['name'],
                request.log_record['lvl'],
                request.log_record['fn'],
                request.log_record['lno'],
                request.log_record['msg'],
                request.log_record['args'],
                request.log_record['exc_info'],
                request.log_record['func']
            )
            self.remote_logger.handle(record)

        elif request.log_message:
            #it's a log message
            self.logger.debug('Process RequestLog log message')
            self.remote_logger.info(request.log_message)

        else:
            #invalid log request
            self.logger.warning(u'Not supposed receiving empty log request')

