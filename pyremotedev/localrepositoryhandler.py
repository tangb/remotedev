#!/usr/bin/env python
# -*- coding: utf-8 -*-

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
import logging
from .request import RequestFile
import os
import io

class LocalRepositoryHandler(FileSystemEventHandler):
    """
    Local repository changes handler.
    It watches for filesystem changes, filter event if necessary and post request
    """

    REJECTED_FILENAMES = [
        u'4913', #vim furtive temp file to check user permissions
        u'.gitignore'
    ]
    REJECTED_EXTENSIONS = [
        u'.swp', #vim
        u'.swpx', #vim
        u'.swx', #vim
        u'.tmp', #generic?
        u'.offset' #pygtail
    ]
    REJECTED_PREFIXES = [
        u'~'
    ]
    REJECTED_SUFFIXES = [
        u'~'
    ]
    REJECTED_DIRS = [
        u'.git',
        u'.vscode',
        u'.editor'
    ]

    def __init__(self, synchronizer, base_dir, drop_files):
        """
        Constructor

        Args:
            synchronizer (Synchronizer): synchronizer instance
            base_dir (string): base dir (scanned one)
            drop_files (list): list of file (fullpath) to not observe
        """
        self.sync = synchronizer
        self.logger = logging.getLogger(self.__class__.__name__)
        self.base_dir = base_dir
        self.drop_files = drop_files
        
    def __clean_path(self, path):
        """
        Get valid path making it relative to scanned dir and removing first path separator
        """
        path = path.replace(self.base_dir, '')
        if path.startswith(os.path.sep):
            path = path[1:]

        return path

    def __get_type(self, event):
        """
        Return event type

        Return:
            int: event type as declared in Request class
        """
        if event and event.is_directory:
            return RequestFile.TYPE_DIR

        return RequestFile.TYPE_FILE

    def __filter_event(self, event):
        """
        Analyse event and return True if event must be filtered

        Return:
            bool: True if event must be filtered
        """
        #filter invalid event
        if not event:
            return True

        #filter event on current script
        if event.src_path == u'.%s' % __file__:
            return True

        #filter root event
        if event.src_path == u'.':
            return True

        #dropped files
        if event.src_path in self.drop_files:
            return True

        #filter invalid extension
        src_ext = os.path.splitext(event.src_path)[1]
        if src_ext in self.REJECTED_EXTENSIONS:
            return True

        #filter by prefix
        for prefix in self.REJECTED_PREFIXES:
            if event.src_path.startswith(prefix):
                return True
            if getattr(event, u'dest_path', None) and event.dest_path.startswith(prefix):
                return True

        #filter by suffix
        for suffix in self.REJECTED_SUFFIXES:
            if event.src_path.endswith(suffix):
                return True
            if getattr(event, u'dest_path', None) and event.dest_path.endswith(prefix):
                return True

        #filter by filename
        for filename in self.REJECTED_FILENAMES:
            if event.src_path.endswith(filename):
                return True

        #filter by dir
        parts = event.src_path.split(os.path.sep)
        for dir in self.REJECTED_DIRS:
            if dir in parts:
                return True

        return False

    def send_request(self, request):
        """
        Send specified request to remote

        Args:
            request (Request): request instance
        """
        self.logger.debug(u'Request: %s' % request)
        if self.sync.running:
            self.sync.add_request(request)

    def on_modified(self, event):
        self.logger.debug(u'on_modified: %s' % event)
        if self.__filter_event(event):
            self.logger.debug(u' -> Filter event')
            return
        req = RequestFile()
        req.action = RequestFile.ACTION_UPDATE
        req.type = self.__get_type(event)
        req.src = self.__clean_path(event.src_path)
        if req.type == RequestFile.TYPE_DIR:
            self.logger.debug(u'Drop update on directory')
            return
        if req.type == RequestFile.TYPE_FILE:
            #send file content
            try:
                with io.open(event.src_path, u'rb') as src:
                    req.content = src.read()
                if len(req.content) == 0:
                    self.logger.debug('Drop empty file update')
                    return
            except Exception:
                self.logger.exception(u'Unable to read src file "%s"' % event.src_path)
                return
        self.send_request(req)

    def on_moved(self, event):
        self.logger.debug(u'on_moved: %s' % event)
        if self.__filter_event(event):
            self.logger.debug(u' -> Filter event')
            return
        req = RequestFile()
        req.action = RequestFile.ACTION_MOVE
        req.type = self.__get_type(event)
        req.src = self.__clean_path(event.src_path)
        req.dest = self.__clean_path(event.dest_path)
        self.send_request(req)

    def on_created(self, event):
        self.logger.debug(u'on_created: %s' % event)
        if self.__filter_event(event):
            self.logger.debug(u' -> Filter event')
            return
        req = RequestFile()
        req.action = RequestFile.ACTION_CREATE
        req.type = self.__get_type(event)
        req.src = self.__clean_path(event.src_path)
        if req.type == RequestFile.TYPE_FILE:
            #send file content
            try:
                with io.open(event.src_path, u'rb') as src:
                    req.content = src.read()
            except Exception:
                self.logger.exception(u'Unable to read src file "%s"' % event.src_path)
                return
        self.send_request(req)

    def on_deleted(self, event):
        self.logger.debug(u'on_deleted: %s' % event)
        if self.__filter_event(event):
            self.logger.debug(u' -> Filter event')
            return
        req = RequestFile()
        req.action = RequestFile.ACTION_DELETE
        req.type = self.__get_type(event)
        req.src = self.__clean_path(event.src_path)
        self.send_request(req)
