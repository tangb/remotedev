#!/usr/bin/env python
# -*- coding: utf-8 -*-

from threading import Thread
import logging
from collections import deque
from .consts import SEPARATOR
import os
from .request import RequestFile
import shutil
import io
import time
import re
import copy
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer
from .request import RequestFile
from hashlib import md5
try:
    _unicode = unicode
except NameError:
    _unicode = str



class RequestFileExecutor(Thread):
    """
    This class executes received RequestFile on filesystem
    It is in charge to perform file synchronisation between both filesystem using received requests
    """

    def __init__(self, mappings, debug=False):
        """
        Constructor

        Args:
            mappings (dict|string): directory mappings if dict, sources dir if string
            debug (bool): enable debug
        """
        Thread.__init__(self)
        Thread.daemon = True

        #members
        self.logger = logging.getLogger(self.__class__.__name__)
        #if debug:
        self.logger.setLevel(logging.DEBUG)
        self.running = True
        self.__queue = deque(maxlen=200)

        #filepath converter
        self.file_path_converter = FilepathConverter(mappings)

    def stop(self):
        """
        Stop process
        """
        self.running = False

    def add_request(self, request):
        """
        Add specified request to queue

        Args:
            request (Request): request instance
        """
        self.logger.debug(u'Request added %s' % request)
        self.__queue.appendleft(request)

    def __process_request(self, request):
        """
        Process request

        Args:
            request (Request): request to process

        Return:
            bool: True if request processed succesfully
        """
        try:
            #set is_dir
            is_dir = False
            if request.type == RequestFile.TYPE_DIR:
                is_dir = True

            #apply mapping on source
            if request.src:
                src_mapping = self.file_path_converter.transform_received_path(request.src)
                self.logger.debug('Src mapping: %s <==> %s' % (request.src, src_mapping))
                if src_mapping is None:
                    self.logger.debug(u'Unmapped src %s directory. Drop request' % request.src)
                    return False
                src = src_mapping[u'path']

            #apply mapping on destination
            if request.dest:
                dest_mapping = self.file_path_converter.transform_received_path(request.dest)
                self.logger.debug('Dest mapping: %s <==> %s' % (request.dest, dest_mapping))
                if dest_mapping is None:
                    self.logger.debug(u'Unmapped dest %s directory. Drop request' % request.dest)
                    return False
                dest = dest_mapping[u'path']

            #execute request
            if request.action == RequestFile.ACTION_CREATE:
                self.logger.debug('Process request CREATE for src=%s' % (src))
                if is_dir:
                    #create new directory
                    if not os.path.exists(src):
                        os.makedirs(src)
                else:
                    if not os.path.exists(os.path.dirname(src)):
                        #create non existing file path
                        os.makedirs(os.path.dirname(src))

                    #create new file
                    fd = io.open(src, u'wb')
                    fd.write(request.content)
                    fd.close()

            elif request.action == RequestFile.ACTION_DELETE:
                self.logger.debug('Process request DELETE for src=%s' % (src))
                if is_dir:
                    #delete directory
                    if os.path.exists(src):
                        shutil.rmtree(src)
                else:
                    #delete file
                    if os.path.exists(src):
                        os.remove(src)

            elif request.action == RequestFile.ACTION_MOVE:
                self.logger.debug('Process request MOVE for src=%s dest=%s' % (src, dest))

                #move directory or file
                if os.path.exists(src):
                    os.rename(src, dest)

            elif request.action == RequestFile.ACTION_UPDATE:
                self.logger.debug('Process request UPDATE for src=%s' % (src))
                if is_dir:
                    #update directory
                    self.logger.debug(u'Update request dropped for directories (useless command)')
                else:
                    #update file content
                    fd = io.open(src, u'wb')
                    fd.write(request.content)
                    fd.close()

            else:
                #unhandled case
                self.logger.warning(u'Unhandled command in request %s' % request)
                return False

            return True

        except:
            self.logger.exception(u'Exception occured processing request %s:' % request)
            return False

    def run(self):
        """
        Main process: unqueue request and process it
        """
        while self.running:
            try:
                request = self.__queue.pop()
                if not self.__process_request(request):
                    #failed to process request
                    #TODO what to do ?
                    pass

            except IndexError:
                #no request available
                time.sleep(0.25)





class RequestFileCreator(FileSystemEventHandler):
    """
    Filesystem changes handler.
    It watches for filesystem changes, filter event if necessary, prepare and post request
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

    def __init__(self, send_request_callback, path, mappings=None, drop_files=[]):
        """
        Constructor

        Args:
            synchronizer (Synchronizer): synchronizer instance
            path (string): path to watch for
            drop_files (list): list of file (fullpath) to not observe
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)
        self.path = path
        self.drop_files = drop_files
        self.send_request_callback = send_request_callback

        if mappings:
            self.file_path_converter = FilepathConverter(mappings)
        else:
            self.file_path_converter = FilepathConverter(path)

    def __get_event_type(self, event):
        """
        Return event type

        Return:
            int: event type as declared in Request class
        """
        if event and event.is_directory:
            return RequestFile.TYPE_DIR

        return RequestFile.TYPE_FILE

    def __is_event_dropped(self, event):
        """
        Analyse event and return True if event must be dropped

        Return:
            bool: True if event must be dropped
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

    def on_modified(self, event):
        """
        Update detected on filesystem, process event
        """
        self.logger.debug(u'on_modified: %s' % event)

        #drop event
        if self.__is_event_dropped(event):
            self.logger.debug(u' -> Event dropped (filter)')
            return
        event_type = self.__get_event_type(event)
        if event_type == RequestFile.TYPE_DIR:
            self.logger.debug(u' -> Event dropped (update on directory)')
            return
        new_src = self.file_path_converter.transform_path_to_send(event.src_path)
        if new_src is None:
            self.logger.debug(u' -> Event dropped (src path not mapped)')
            return

        #build request file
        req = RequestFile()
        req.action = RequestFile.ACTION_UPDATE
        req.type = event_type
        req.src = new_src[u'path']
        try:
            with io.open(event.src_path, u'rb') as src:
                req.content = src.read()
                req.md5 = md5(req.content).hexdigest()
            if len(req.content) == 0:
                self.logger.debug(' -> Event dropped (empty file)')
                return
        except Exception:
            self.logger.exception(u'Unable to read src file "%s"' % event.src_path)
            return
        
        #send request
        self.send_request_callback(req)

    def on_moved(self, event):
        """
        Move detected on filesystem, process event
        """
        self.logger.debug(u'on_moved: %s' % event)

        #drop event
        if self.__is_event_dropped(event):
            self.logger.debug(u' -> Event dropped (filter)')
            return
        new_src = self.file_path_converter.transform_path_to_send(event.src_path)
        if new_src is None:
            self.logger.debug(u' -> Event dropped (src path not mapped)')
            return
        new_dest = self.file_path_converter.transform_path_to_send(event.dest_path)
        if new_dest is None:
            self.logger.debug(u' -> Event dropped (dest path not mapped)')
            return

        #build request file
        req = RequestFile()
        req.action = RequestFile.ACTION_MOVE
        req.type = self.__get_event_type(event)
        req.src = new_src[u'path']
        req.dest = new_dest[u'path']

        #send request
        self.send_request_callback(req)

    def on_created(self, event):
        """
        Creation detected on filesystem, process event
        """
        self.logger.debug(u'on_created: %s' % event)

        #drop event
        if self.__is_event_dropped(event):
            self.logger.debug(u' -> Event dropped (filter)')
            return
        new_src = self.file_path_converter.transform_path_to_send(event.src_path)
        if new_src is None:
            self.logger.debug(u' -> Event dropped (src path not mapped)')
            return

        #build request file
        req = RequestFile()
        req.action = RequestFile.ACTION_CREATE
        req.type = self.__get_event_type(event)
        req.src = new_src[u'path']
        if req.type == RequestFile.TYPE_FILE:
            #send file content
            try:
                with io.open(event.src_path, u'rb') as src:
                    req.content = src.read()
                    req.md5 = md5(req.content).hexdigest()
            except Exception:
                self.logger.exception(u'Unable to read src file "%s"' % event.src_path)
                return

        #send request
        self.send_request_callback(req)

    def on_deleted(self, event):
        """
        Deletion detected on filesystem, process event
        """
        self.logger.debug(u'on_deleted: %s' % event)

        #drop event
        if self.__is_event_dropped(event):
            self.logger.debug(u' -> Event dropped (filter)')
            return
        new_src = self.file_path_converter.transform_path_to_send(event.src_path)
        if new_src is None:
            self.logger.debug(u' -> Event dropped (src path not mapped)')
            return

        #build request file
        req = RequestFile()
        req.action = RequestFile.ACTION_DELETE
        req.type = self.__get_event_type(event)
        req.src = new_src[u'path']

        #send request
        self.send_request_callback(req)





class FilepathConverter():
    """
    Lib to convert path from or to different environments
    """
    def __init__(self, path_or_mappings):
        """
        Constructor

        Args:
            path_or_mappings (string|dict): path or mappings
        """
        self.logger = logging.getLogger(self.__class__.__name__)
        self.logger.setLevel(logging.DEBUG)
        self.mappings = None
        self.path = None

        if isinstance(path_or_mappings, dict):
            #mappings provided, format it to useable format
            self.mappings = []
            for key in list(path_or_mappings.keys()):

                #add final separator if missing on src or dest
                src = copy.copy(key)
                if not src.endswith(os.path.sep):
                    src = src + os.path.sep
                dest = path_or_mappings[key][u'dest']
                if not dest.endswith(os.path.sep):
                    dest = dest + os.path.sep

                #save new mappings
                entry = {
                    u'src': src,
                    u'dest': dest,
                    u'compiled_src': re.compile(src, re.UNICODE | re.DOTALL)
                }
                entry.update(self.__revert_mappings(src, dest))
                self.mappings.append(entry)

            self.logger.debug('Old mappings: %s' % path_or_mappings)
            self.logger.debug('New mappings: %s' % self.mappings)

        else:
            #path provided
            self.path = path_or_mappings

    def __revert_mappings(self, src, dest):
        """
        Revert provided src and dest pattern to be able to restore initial path before sending file request
        to development env

        Args:
            src (string): source path
            dest (string): destination path
        """
    	reverted_src = src
    	reverted_dest = dest

    	matches_src = re.finditer('\(\?P<(.*?)>.*?\)', src)
    	for _, match_src in enumerate(matches_src):
            pattern_src = match_src.group()
            fieldname = match_src.groups()[0]
    
            matches_dest = re.finditer('\%\(' + fieldname +'\)[diouxXeEfFgGcrsa]', dest)
            for _, match_dest in enumerate(matches_dest):
                pattern_dest = match_dest.group()

                #revert in dest each field
                reverted_dest = reverted_dest.replace(pattern_dest, pattern_src)
                reverted_src = reverted_src.replace(pattern_src, pattern_dest)

        return {
            u'reverted_src': reverted_src,
            u'reverted_dest': reverted_dest,
            u'compiled_reverted_dest': re.compile(reverted_dest, re.UNICODE | re.DOTALL)
        }

    def __full_path_split(self, path):
        """
        Explode path into dir/dir/.../filename

        Source:
            https://stackoverflow.com/a/27065945

        Args:
            path (string): path to split

        Return:
            list: list of path parts
        """
        if path is None:
            path = u''
        parts = []
        (path, tail) = os.path.split(path)
        while path and tail:
            parts.append(tail)
            (path, tail) = os.path.split(path)
        parts.append(os.path.join(path, tail))

        out = list(map(os.path.normpath, parts))[::-1]
        if len(out) > 0 and out[0] == u'.':
            #remove starting .
            return out[1:]
            
        return out

    def __from_dev_env(self, path):
        self.logger.debug(' -> from_dev_env')
        for mapping in self.mappings:
            found = False
            matches = re.finditer(mapping[u'compiled_src'], path)
            for _, match in enumerate(matches):
                found = True
                fullmatch = match.group()
                substitutions = match.groupdict()
                remaining = path.replace(fullmatch, u'')
                new_path = os.path.join(mapping[u'dest'] % substitutions, remaining)

            if found:
                return {
                    u'path': new_path
                }

        return None

    def __to_dev_env(self, path):
        self.logger.debug(' -> to_dev_env')
        for mapping in self.mappings:
            found = False
            matches = re.finditer(mapping[u'compiled_reverted_dest'], path)
            for _, match in enumerate(matches):
                found = True
                fullmatch = match.group()
                substitutions = match.groupdict()
                remaining = path.replace(fullmatch, u'')
                new_path = os.path.join(mapping[u'reverted_src'] % substitutions, remaining)

            if found:
                if new_path.startswith('/'):
                    new_path = new_path[1:]

                return {
                    u'path': new_path
                }

        return None

    def __to_exec_env(self, path):
        """
        Returns path before sending it to execution environment
        Remove base path from specified full path
        """
        self.logger.debug(' -> to_exec_env')
        new_path = path.replace(self.path, u'')
        if new_path.startswith('/'):
            new_path = new_path[1:]

        return {
            u'path': new_path
        }

    def __from_exec_env(self, path):
        """
        Return path when receiving it from execution environment
        Append base path to specified absolute path
        """
        self.logger.debug(' -> from_exec_env')
        new_path = os.path.join(self.path, path)

        return {
            u'path': new_path
        }

    def transform_path_to_send(self, path):
        """
        Get path that need to be sent
        """
        self.logger.debug('Path before transformation: %s' % path)
        if self.mappings is not None:
            res = self.__to_dev_env(path)
        else:
            res = self.__to_exec_env(path)
        self.logger.debug('Path after transformation: %s' % res)
        return res

    def transform_received_path(self, path):
        """
        Get path that was received
        """
        self.logger.debug('Path before transformation: %s' % path)
        if self.mappings is not None:
            res = self.__from_dev_env(path)
        else:
            res = self.__from_exec_env(path)
        self.logger.debug('Path after transformation: %s' % res)
        return res
