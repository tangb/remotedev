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
            mappings (dict|string): directory mappings (src<=>dst) if dict, local dir if string
            debug (bool): enable debug
        """
        Thread.__init__(self)
        Thread.daemon = True

        #members
        self.logger = logging.getLogger(self.__class__.__name__)
        if debug:
            self.logger.setLevel(logging.DEBUG)
        self.running = True
        self.__queue = deque(maxlen=200)

        if isinstance(mappings, str) or isinstance(mappings, _unicode):
            #mappings on development environment
            self.source_code_dir = mappings
            self.exec_mappings = None

        elif isinstance(mappings, dict):
            #mappings on execution environment
            self.mappings = mappings
            
            #build new mappings for process convenience
            self.exec_mappings = {}
            for src in list(self.mappings.keys()):
                src_parts = self.split_path(src)
                new_src = SEPARATOR.join(src_parts)
                link_parts = self.split_path(self.mappings[src][u'link'])
                new_link = SEPARATOR.join(link_parts)

                #always end new src path by separator to protect substitution
                new_src += SEPARATOR

                #save new mappings
                self.exec_mappings[new_src] = {
                    u'original_src': src,
                    u'original_dest': self.mappings[src][u'dest'],
                    u'original_link': self.mappings[src][u'link'],
                    u'link': new_link
                }
            self.logger.debug('New mappings: %s' % self.exec_mappings)
        
        else:
            #invalid mapping content
            self.logger.fatal(u'Invalid mapping variable content. Must be str/unicode in dev env or dict in exec env')

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

    def split_path(self, path):
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

    def __apply_development_env_mapping(self, path):
        """
        Apply mapping on development environment

        Args:
            path (string): path to map

        Return:
            dict or None: None if mapping not found, or mapped dir and link::
                {
                    'path': mapped path
                    'link': link
                }
        """
        return {
            u'path': os.path.join(self.source_code_dir, path),
            u'link': None
        }

    def __apply_execution_env_mapping(self, path):
        """
        Apply mapping on execution environment

        Args:
            path (string): path to map

        Return:
            dict or None: None if mapping not found, or mapped dir and link::
                {
                    'path': mapped path
                    'link': link
                }
        """
        if len(self.mappings) == 0:
            #no mapping configured, copy to current path
            return {
                u'path': path,
                u'link': None
            }

        else:
            #mappings configured, try to find valid one

            #make path useable for processing
            parts = self.split_path(path)
            if len(parts) > 0 and parts[0] == u'.':
                parts = parts[1:]
            path = os.path.sep.join(parts)
            new_path = SEPARATOR.join(parts)
            self.logger.debug('path=%s new_path=%s' % (path, new_path))

            #look for valid mapping
            found = None
            joker = None
            for mapping_src in list(self.exec_mappings.keys()):

                self.logger.debug(' --> %s startswith %s' % (mapping_src, u'.'))
                if mapping_src.startswith(u'*'):
                    #found joker, it will return this joker only if no mapping found
                    self.logger.debug('  Joker found!')
                    joker = {
                        u'src': self.exec_mappings[mapping_src][u'original_src'],
                        u'dest': self.exec_mappings[mapping_src][u'original_dest'],
                        u'link': self.exec_mappings[mapping_src][u'original_link']
                    }

                self.logger.debug(' --> %s startswith %s' % (new_path, mapping_src))
                if new_path.startswith(mapping_src):
                    #found mapping
                    self.logger.debug('  Found!')
                    found = {
                        u'src': self.exec_mappings[mapping_src][u'original_src'],
                        u'dest': self.exec_mappings[mapping_src][u'original_dest'],
                        u'link': self.exec_mappings[mapping_src][u'original_link']
                    }

            #switch to joker if no mapping found
            if joker and not found:
                found = joker

            #build final result if mapping found
            if found:
                self.logger.debug('Found mapping: %s' % found)
                if found[u'src'] == u'*':
                    new_path = os.path.join(found[u'dest'], path)
                else:
                    new_path = path.replace(found[u'src'], found[u'dest'], 1)
                link = None
                if found[u'link']:
                    link = path.replace(found[u'src'], found[u'link'], 1)

                return {
                    u'path': new_path,
                    u'link': link
                }

            #no mapping found
            return None

    def __apply_mapping(self, path):
        """
        Apply mapping to specified path according to current mappings configuration

        Args:
            path (string): path to map

        Return:
            dict or None: None if mapping not found, or mapped dir and link::
                {
                    'path': mapped path
                    'link': link
                }
        """
        if self.exec_mappings:
            return self.__apply_execution_env_mapping(path)
        else:
            return self.__apply_development_env_mapping(path)

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
                src_mapping = self.__apply_mapping(request.src)
                self.logger.debug('Src mapping: %s <==> %s' % (request.src, src_mapping))
                if src_mapping is None:
                    self.logger.debug(u'Unmapped src %s directory. Drop request' % request.src)
                    return False
                src = src_mapping[u'path']
                link_src = src_mapping[u'link']

            #apply mapping on destination
            if request.dest:
                dest_mapping = self.__apply_mapping(request.dest)
                self.logger.debug('Dest mapping: %s <==> %s' % (request.dest, dest_mapping))
                if dest_mapping is None:
                    self.logger.debug(u'Unmapped dest %s directory. Drop request' % request.dest)
                    return False
                dest = dest_mapping[u'path']
                link_dest = dest_mapping[u'link']

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

                    #create link
                    if link_src and not os.path.exists(link_src):
                        if not os.path.exists(os.path.dirname(link_src)):
                            #create non existing link path
                            os.makedirs(os.path.dirname(link_src))
                        #create symlink
                        os.symlink(src, link_src)

            elif request.action == RequestFile.ACTION_DELETE:
                self.logger.debug('Process request DELETE for src=%s' % (src))
                if is_dir:
                    #delete directory
                    if os.path.exists(src):
                        shutil.rmtree(src)
                else:
                    #remove associated symlink firstly
                    if link_src:
                        if os.path.exists(link_src):
                            self.logger.debug('Remove link_src: %s' % link_src)
                            os.remove(link_src)

                    #delete file
                    if os.path.exists(src):
                        os.remove(src)

            elif request.action == RequestFile.ACTION_MOVE:
                self.logger.debug('Process request MOVE for src=%s dest=%s' % (src, dest))

                #remove link firstly
                if not is_dir:
                    if link_src and os.path.exists(link_src):
                        self.logger.debug(u'Remove src symlink %s' % link_src)
                        os.remove(link_src)
                        self.logger.debug(u'Create dest symlink %s==>%s' % (dest, link_dest))
                        os.symlink(dest, link_dest)

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
                    #if os.path.exists(src):
                    fd = io.open(src, u'wb')
                    fd.write(request.content)
                    fd.close()

                    #create link
                    if link_src and not os.path.exists(link_src):
                        self.logger.debug(u'Create symlink %s' % link_src)
                        os.symlink(src, link_src)

            else:
                #unhandled case
                self.logger.warning(u'Unhandled command in request %s' % request)
                return False

            return True

        except:
            self.logger.exception(u'Exception during request processing %s:' % request)
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
