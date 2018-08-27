#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
from logging.handlers import RotatingFileHandler
import io
import os
import time
import socket
import sys
import getpass
import platform
import subprocess
from pygtail import Pygtail
try:
    import configparser
except:
    import ConfigParser as configparser
import shutil
import traceback
from .version import __version__
from appdirs import user_data_dir
from threading import Thread
from collections import deque
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from sshtunnel import SSHTunnelForwarder
import bson
try:
    # pylint: disable=E0602
    input = raw_input
except Exception:
    pass
try:
    _unicode = unicode
except NameError:
    _unicode = str
from .localrepositoryhandler import LocalRepositoryHandler
from .synchronizer import SynchronizerDevEnv, SynchronizerExecEnv


class PyRemoteDev(Thread):
    """
    Pyremotedev client running on development machine (it connects to server)

    Args:
        profile: profile to use
    """
    def __init__(self, profile, debug=False):
        """
        Constructor
        """
        Thread.__init__(self)
        Thread.daemon = True

        #members
        self.logger = logging.getLogger(self.__class__.__name__)
        self.profile = profile
        self.running = True
        self.debug = debug
        
    def stop(self):
        """
        Stop devenv process
        """
        self.running = False

    def run(self):
        """
        Main process
        """
        if not os.path.exists(self.profile[u'local_dir']):
            raise Exception(u'Directory "%s" does not exist. Please update the loaded profile' % self.profile[u'local_dir'])

        #start synchronizer
        synchronizer = SynchronizerDevEnv(
            self.profile[u'remote_host'],
            self.profile[u'remote_port'],
            self.profile[u'ssh_username'],
            self.profile[u'ssh_password'],
            self.profile[u'local_dir'],
            self.debug
        )
        synchronizer.start()

        #create filesystem watchdog
        observer = Observer()
        observer.schedule(LocalRepositoryHandler(synchronizer, self.profile[u'local_dir'], []), path=self.profile[u'local_dir'], recursive=True)
        observer.start()

        #main loop
        try:
            while self.running:
                if not synchronizer.running:
                    break
                time.sleep(0.25)

        except:
            self.logger.exception(u'Exception:')

        finally:
            observer.stop()
            synchronizer.stop()

        #close properly application
        observer.join()
        synchronizer.join()





class PyRemoteExec(Thread):
    """
    Pyremotedev server running on execution machine (implements own server)
    """
    def __init__(self, profile, remote_logging=True, debug=False):
        """
        Constructor

        Args:
            profile (dict): profile to use
            remote_logging (bool): enable or disable internal remote logging
            debug (bool): enable debug
        """
        Thread.__init__(self)
        Thread.daemon = True

        #members
        self.profile = profile
        self.running = True
        self.logger = logging.getLogger(self.__class__.__name__)
        self.debug = debug
        self.remote_logging = remote_logging
        self.__observers = []
        if debug:
            self.logger.setLevel(logging.DEBUG)

    def stop(self):
        """
        Stop execenv process
        """
        self.running = False

    def __start_client(self, clientsocket, ip, port):
        """
        Start client launching a synchronizer and all necessary file observer

        Args:
            clientsocket (socket): client connection
            ip: client ip
            port: connection port

        Returns:
            SynchronizerExecEnv
        """
        #create synchronizer
        if self.profile[u'log_file_path']:
            self.logger.debug(u'Create synchronizer with log file "%s" handling' % self.profile[u'log_file_path'])
            synchronizer = SynchronizerExecEnv(ip, port, clientsocket, self.profile[u'mappings'], self.profile[u'log_file_path'], self.debug)
        elif self.remote_logging:
            self.logger.debug(u'Create synchronizer with internal application log (lib mode) handling')
            synchronizer = SynchronizerExecEnv(ip, port, clientsocket, self.profile[u'mappings'], None, self.debug)
        else:
            self.logger.debug(u'Create synchronizer with no log handling')
            synchronizer = SynchronizerExecEnv(ip, port, clientsocket, self.profile[u'mappings'], False, self.debug)
        synchronizer.start()

        #create filesystem watchdogs on each mappings
        for src in list(self.profile[u'mappings'].keys()):
            dest = self.profile[u'mappings'][src][u'dest']
            drop_files = [self.profile[u'log_file_path']]
            self.logger.debug(u'Create filesystem observer for dir "%s"' % dest)
            observer = Observer()
            observer.schedule(LocalRepositoryHandler(synchronizer, dest, drop_files), path=dest, recursive=True)
            observer.start()

            self.__observers.append(observer)

        return synchronizer

    def __stop_client(self, client):
        """
        Stop client terminating processes joined with client process
        """
        #stop all of client observers
        while len(self.__observers) > 0:
            observer = self.__observers.pop()
            observer.stop()

        #and stop client process itself (synchronizer)
        client.stop()

    def run(self):
        """
        Main process
        """
        #main loop
        last_client = None
        try:
            #create communication server
            server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server.settimeout(1.0)
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(('', 52666))

            self.logger.debug(u'Listening for connections...')
            while self.running:
                try:
                    server.listen(10)
                    (clientsocket, (ip, port)) = server.accept()
                    self.logger.debug(u'New client connection')

                    #stop last remote (only one client at once)
                    if last_client:
                        self.logger.debug(u'Stop current running client process and start new one')
                        self.__stop_client(last_client)

                    #instanciate new remote client
                    self.logger.debug(u'New client connection')
                    last_client = self.__start_client(clientsocket, ip, port)

                except socket.timeout:
                    pass

        except:
            self.logger.exception(u'Exception:')

        finally:
            #stop last connected client
            if last_client:
                self.__stop_client(last_client)
                