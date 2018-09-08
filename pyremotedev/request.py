#!/usr/bin/env python
# -*- coding: utf-8 -*-

from hashlib import md5

REQUEST_UNKNOW = 0
REQUEST_GOODBYE = 1
REQUEST_FILE = 2
REQUEST_LOG = 3
REQUEST_PING = 4
REQUEST_PONG = 5

class Request(object):
    """
    Base request class
    """

    def __init__(self):
        """
        Constructor
        """
        self._type = REQUEST_UNKNOW

    def get_type(self):
        """
        Return request type

        Returns:
            int: request type
        """
        return self._type

    def __str__(self):
        """
        To string method
        """
        raise NotImplementedError('Method __str__ is not implemented!')

    def log_str(self):
        """
        To log
        """
        return self.__str__()

    def from_dict(self, request):
        """
        Fill request with specified dict

        Args:
            request (dict): request under dict format
        """
        raise NotImplementedError('Method from_dict is not implemented!')

    def to_dict(self):
        """
        Convert object to dict for easier json/bson conversion

        Return:
            dict: class member onto dict
        """
        return {
            u'_type': self._type
        }





class RequestGoodbye(Request):
    def __init__(self):
        """
        Constructor
        """
        self._type = REQUEST_GOODBYE

    def __str__(self):
        """
        To string method
        """
        return u'RequestGoodbye()'

    def from_dict(self, request):
        """
        Fill request with specified dict

        Args:
            request (dict): request under dict format
        """
        return {}





class RequestPing(Request):
    def __init__(self):
        """
        Constructor
        """
        self._type = REQUEST_PING

    def __str__(self):
        """
        To string method
        """
        return u'RequestPing()'

    def from_dict(self, request):
        """
        Fill request with specified dict

        Args:
            request (dict): request under dict format
        """
        return {}




class RequestPong(Request):
    def __init__(self):
        """
        Constructor
        """
        self._type = REQUEST_PONG

    def __str__(self):
        """
        To string method
        """
        return u'RequestPong()'

    def from_dict(self, request):
        """
        Fill request with specified dict

        Args:
            request (dict): request under dict format
        """
        return {}





class RequestFile(Request):
    """
    Request for file changes
    """

    ACTION_UPDATE = 0
    ACTION_MOVE = 1
    ACTION_CREATE = 2
    ACTION_DELETE = 3

    TYPE_FILE = 0
    TYPE_FILE_STR = u'FILE'
    TYPE_DIR = 1
    TYPE_DIR_STR = u'DIR'

    def __init__(self):
        """
        Constructor
        """
        #request type
        self._type = REQUEST_FILE
        #file action
        self.action = None
        #mode: file or directory
        self.mode = None
        #source file path
        self.src = None
        #destination file path 
        self.dest = None
        #file content for some actions (create, update)
        self.content = u''
        #file content md5 needed to avoid circular copy
        self.md5 = None

    def __str__(self):
        """
        To string method
        """
        action = None
        if self.action == self.ACTION_UPDATE:
            action = u'UPDATE'
        elif self.action == self.ACTION_MOVE:
            action = u'MOVE'
        elif self.action == self.ACTION_CREATE:
            action = u'CREATE'
        elif self.action == self.ACTION_DELETE:
            action = u'DELETE'

        type = None
        if self.type == self.TYPE_DIR:
            type = self.TYPE_DIR_STR
        else:
            type = self.TYPE_FILE_STR

        return u'RequestFile(action:%s, type:%s, src:%s, dest:%s, content:%d bytes md5:%s)' % (action, type, self.src, self.dest, len(self.content), self.md5)

    def log_str(self):
        """
        Return log string

        Returns:
            string
        """
        action = None
        if self.action == self.ACTION_UPDATE:
            action = u'Update'
        elif self.action == self.ACTION_MOVE:
            action = u'Move'
        elif self.action == self.ACTION_CREATE:
            action = u'Create'
        elif self.action == self.ACTION_DELETE:
            action = u'Delete'

        type_ = None
        if self.type == self.TYPE_DIR:
            type_ = self.TYPE_DIR_STR
        else:
            type_ = self.TYPE_FILE_STR

        if self.action in (self.ACTION_UPDATE, self.ACTION_CREATE):
            return u'%s %s %s (%d bytes md5:%s)' % (action, type_, self.src, len(self.content), self.md5)
        elif self.action == self.ACTION_DELETE:
            return u'%s %s %s' % (action, type_, self.src)
        else:
            return u'%s %s %s to %s' % (action, type_, self.src, self.dest)

    def from_dict(self, request):
        """
        Fill request with specified dict

        Args:
            request (dict): request under dict format
        """
        for key in list(request.keys()):
            if key == u'action':
                self.action = request[key]
            elif key == u'type':
                self.type = request[key]
            elif key == u'src':
                self.src = request[key]
            elif key == u'dest':
                self.dest = request[key]
            if key == u'content':
                self.content = request[key]
            if key == u'md5':
                self.md5 = request[key]

    def to_dict(self):
        """
        Convert object to dict for easier json/bson conversion

        Return:
            dict: class member onto dict
        """
        out = {
            u'_type': self._type,
            u'action': self.action,
            u'type': self.type,
            u'src': self.src,
            u'md5': self.md5
        }
        if self.dest:
            out[u'dest'] = self.dest
        if len(self.content) > 0:
            out[u'content'] = self.content

        return out






class RequestLog(Request):
    """
    Request for log changes
    """
    def __init__(self):
        """
        Constructor
        """
        #request type
        self._type = REQUEST_LOG
        #contain exception record
        self.log_record = None
        #contain log message
        self.log_message = None

    def __str__(self):
        """
        To string
        """
        if self.log_record:
            return u'RequestLog(log_record: %s)' % self.log_record['msg']
        elif self.log_message:
            return u'RequestLog(log_message: %s)' % self.log_message
        else:
            return u'RequestLog(empty)'

    def is_empty(self):
        """
        Return True if empty

        Returns:
            bool
        """
        if self.log_record or self.log_message:
            return False

        return True

    def from_dict(self, request):
        """
        Fill request with specified dict

        Args:
            request (dict): request under dict format
        """
        for key in list(request.keys()):
            if key == u'log_record':
                self.log_record = request[key]
            elif key == u'log_message':
                self.log_message = request[key]

    def to_dict(self):
        """
        Convert object to dict for easier json/bson conversion

        Return:
            dict: class member onto dict
        """
        out = {
            u'_type': self._type,
            u'log_record': self.log_record,
            u'log_message': self.log_message
        }

        return out

