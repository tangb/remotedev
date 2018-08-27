#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import time
try:
    import configparser
except:
    import ConfigParser as configparser
import platform
import sys
from .consts import DEFAULT_SSH_PORT, DEFAULT_SSH_USERNAME, DEFAULT_SSH_PASSWORD, SEPARATOR
import getpass
try:
    input = raw_input
except Exception:
    pass

class ConfigFile():
    """
    Base config class
    Holds base function for config proper file handling
    """
    def __init__(self, config_file):
        """
        Constructor

        Args:
            config_file (string): valid configuration file path (including filename)
        """
        self.config_file = config_file
        self.logger = logging.getLogger(self.__class__.__name__)

    def __load_config_parser(self):
        """
        Load config parser instance:
        """
        self.logger.debug('Loading config file: %s' % self.config_file)
        if not os.path.exists(os.path.dirname(self.config_file)):
            os.makedirs(os.path.dirname(self.config_file))

        if not os.path.exists(self.config_file):
            #file doesn't exist, create empty one
            with open(self.config_file, u'w') as fd:
                fd.write('')
            #make sure file is written
            time.sleep(1.0)
            self.logger.info(u'Config file written to "%s"' % self.config_file)

        #load config parser
        config = configparser.ConfigParser()
        config.read(self.config_file)

        return config

    def __save_config_parser(self, config):
        """
        Save config parser instance to file

        Args:
            config (ConfigParser): config parser instance
        """
        with open(self.config_file, u'w') as config_file:
            config.write(config_file)

    def clear_terminal(self):
        """
        Clear terminal
        """
        if self.logger.getEffectiveLevel() != logging.DEBUG:
            os.system(u'cls' if platform.system() == u'Windows' else u'clear')

    def load(self):
        """
        Load config file

        Return:
            dict: dictionnary of profiles
        """
        try:
            #get config parser
            config = self.__load_config_parser()

            #convert config parser to dict
            profiles = {}
            for profile_name in config.sections():
                profile = {}
                for option in config.options(profile_name):
                    profile[option] = config.get(profile_name, option)
                profiles[profile_name] = self._get_profile_values(profile_name, profile)

            return profiles

        except:
            self.logger.exception(u'Unable to read config file "%s"' % self.config_file)

    def _get_profile_values(self, profile_name, profile):
        """
        Return profile values

        Return:
            dict: dict of profile values
        """
        raise NotImplementedError('Method _get_profile_values must be implemented!')

    def select_profile(self):
        """
        Display profile selector
        """
        #load current conf
        conf = self.load()

        #iterate until profile index is selected
        profile_index = 0
        while True:
            (profile_index, conf) = self.__load_profile_menu(conf)
            if profile_index >= 0:
                #profile selected
                break

        #load profile
        return conf[list(conf.keys())[profile_index]]

    def __add_profile_menu(self, conf):
        """
        Show profile addition menu

        Args:
            conf (dict): current config (dict format as returned by load method)

        Return:
            dict: updated (or not) conf dict
        """
        self.clear_terminal()
        print(u'Follow this wizard to create new configuration profile.')
        print(u'Be careful if existing profile name already exists, it will be overwritten!')

        (profile_name, profile) = self._get_new_profile_values()
        self.add_profile(profile_name, profile)

        return self.load()

    def _get_new_profile_values(self):
        """
        Return new profile values

        Return:
            tuple::
                (
                    string: profile name
                    dict: dict of new profile values
                )
        """
        raise NotImplementedError('Method _get_new_profile_values must be implemented!')

    def __delete_profile_menu(self, conf):
        """
        Show profile deletion menu

        Args:
            conf (dict): current config (dict format as returned by load method)

        Return:
            dict: updated (or not) conf dict
        """
        self.clear_terminal()
        print('Type profile number to delete:')
        index = 0
        max_profiles = len(list(conf.keys()))
        for profile_name in list(conf.keys()):
            profile_string = self._get_profile_entry_string(profile_name, conf[profile_name])
            print(u' %d) %s' % (index, profile_string))
            index += 1
        print(u'Empty entry to return back')
        choice = ''
        while len(choice) == 0:
            choice = input(u'>> ')
            if choice.strip() == u'':
                #return back
                return conf
            else:
                try:
                    temp = int(choice)
                    if temp < 0 or temp >= max_profiles:
                        choice = u''
                except:
                    choice = u''

        #perform deletion
        profile_name = list(conf.keys())[int(choice)]
        self.delete_profile(profile_name)

        return self.load()

    def _get_profile_entry_string(self, profile_name, profile):
        """
        Return profile entry string

        Return:
            string: entry string
        """
        raise NotImplementedError('Method _get_profile_entry_string must be implemented!')

    def __load_profile_menu(self, conf):
        """
        Show load profiles menu

        Args:
            conf (dict): current config (dict format as returned by load method)

        Return:
            tuple: output values::
                (
                    int: profile index to load, or negative value if other action performed,
                    dict: current conf
                )
        """
        self.clear_terminal()
        print(u'Type profile number to load it:')
        index = 0
        max_profiles = len(list(conf.keys()))
        if len(list(conf.keys())) == 0:
            #no profile
            print(u'  No profile yet. Please add new one.')
        for profile_name in list(conf.keys()):
            profile_string = self._get_profile_entry_string(profile_name, conf[profile_name])
            print(u' %d) %s' % (index, profile_string))
            index += 1
        print(u'Type "a" to add new profile')
        print(u'Type "d" to delete existing profile')
        print(u'Type "q" to quit application')
        choice = ''
        while len(choice) == 0:
            choice = input(u'>> ')
            if choice.strip() == u'a':
                conf = self.__add_profile_menu(conf)
                return -1, conf
            elif choice.strip() == u'd':
                conf = self.__delete_profile_menu(conf)
                return -2, conf
            elif choice.strip() == u'q':
                print(u'Bye bye')
                sys.exit(0)
            else:
                try:
                    temp = int(choice)
                    if temp < 0 or temp >= max_profiles:
                        #out of bounds
                        choice = u''
                except:
                    #invalid index typed
                    choice = u''

        return int(choice), conf

    def add_profile(self, profile_name, profile):
        """
        Add new profile to config

        Args:
            profile_name (string): profile name
            profile (dict): profile content
        """
        try:
            #get config parser
            config = self.__load_config_parser()

            #append new profile
            config.add_section(profile_name)
            for key in profile:
                config.set(profile_name, key, profile[key])

            #save config
            self.__save_config_parser(config)

        except:
            self.logger.exception(u'Unable to add profile:')

    def delete_profile(self, profile_name):
        """
        Delete specified profile
        """
        try:
            #get config parser
            config = self.__load_config_parser()

            #append new profile
            if profile_name in config.sections():
                config.remove_section(profile_name)

            #save config
            self.__save_config_parser(config)

        except:
            self.logger.exception(u'Unable delete profile:')





class DevEnvConfigFile(ConfigFile):
    """
    Development environment config file handler
    """

    def __init__(self, config_file):
        """
        Constructor

        Args:
            config_file (string): config file path
        """
        ConfigFile.__init__(self, config_file)
        self.current_local_dir = os.getcwd()

    def _get_profile_values(self, profile_name, profile):
        """
        Return profile values

        Return:
            dict: dictionnary of devenv profile::
                {
                    'profile1': {
                        remote_host,
                        remote_port,
                        ssh_username,
                        ssh_password,
                        local_dir
                    },
                    ...
                }
        """
        return  {
            u'remote_host': profile[u'remote_host'],
            u'remote_port': int(profile[u'remote_port']),
            u'ssh_username': profile[u'ssh_username'],
            u'ssh_password': profile[u'ssh_password'].replace(u'%%', '%'),
            u'local_dir': profile[u'local_dir']
        }

    def _get_new_profile_values(self):
        """
        Return new profile values

        Return:
            tuple: profile tuple::
                (
                    profile name,
                    {
                        remote_host,
                        remote_port,
                        ssh_username,
                        ssh_password,
                        local_dir
                    }
                )
        """
        profile_name = u''
        while len(profile_name) == 0:
            profile_name = input(u'Profile name: ')

        remote_host = u''
        while len(remote_host) == 0:
            remote_host = input(u'Remote ip address: ')

        remote_port = u''
        error = True
        while error:
            remote_port = input(u'Remote ssh port (default %s): ' % DEFAULT_SSH_PORT)
            if len(remote_port) == 0:
                remote_port = DEFAULT_SSH_PORT
            try:
                int(remote_port)
                error = False
            except:
                remote_port = ''
                error = True

        ssh_username = u''
        while len(ssh_username) == 0:
            ssh_username = input(u'Remote ssh username (default %s): ' % DEFAULT_SSH_USERNAME)
            if len(ssh_username) == 0:
                ssh_username = DEFAULT_SSH_USERNAME

        ssh_password = u''
        while len(ssh_password) == 0:
            ssh_password = getpass.getpass(u'Remote ssh password (default %s): ' % DEFAULT_SSH_PASSWORD)
            if len(ssh_password) == 0:
                ssh_password = DEFAULT_SSH_PASSWORD
        ssh_password = ssh_password.replace(u'%', u'%%')

        local_dir = input(u'Local directory to watch (default %s): ' % self.current_local_dir)
        if len(local_dir) == 0:
            local_dir = self.current_local_dir

        #return new profile
        return (
            profile_name,
            {
                u'remote_host': remote_host,
                u'remote_port': remote_port,
                u'ssh_username': ssh_username,
                u'ssh_password': ssh_password,
                u'local_dir': local_dir
            }
        )

    def _get_profile_entry_string(self, profile_name, profile):
        """
        Return profile entry string

        Return:
            string: entry string
        """
        return u'%s [%s@%s:%s - %s]' % (profile_name, profile[u'ssh_username'], profile[u'remote_host'], profile[u'remote_port'], profile[u'local_dir'])





class ExecEnvConfigFile(ConfigFile):
    """
    Execution environment config file handler
    """

    KEY_LOG_FILE = u'log_file_path'

    def __init__(self, config_file):
        """
        Constructor

        Args:
            config_file (string): config file path
        """
        ConfigFile.__init__(self, config_file)

    def _get_profile_values(self, profile_name, profile):
        """
        Return profile values

        Return:
            dict: dictionnary of execenv profile::
                {
                    'log_file_path': 'path to log file',
                    'mappings': {
                        'src1': {
                            'dest: 'dest1',
                            'link': 'link'
                        },
                        'src2': {
                            'dest': 'dest2',
                            'link': ''
                        }
                    }
                }
        """
        conf = {
            self.KEY_LOG_FILE: None,
            u'mappings': {}
        }
        for src in profile:
            if src == self.KEY_LOG_FILE:
                #handle log file path
                conf[self.KEY_LOG_FILE] = profile[src]

            else:
                #handle dir mapping
                if profile[src].find(SEPARATOR) >= 0:
                    (dest, link) = profile[src].split(SEPARATOR)

                else:
                    dest = profile[src]
                    link = None

                conf[u'mappings'][src] = {
                    u'dest': dest,
                    u'link': link
                }

        return conf

    def _get_new_profile_values(self):
        """
        Return new profile values

        Return:
            tuple: profile tuple::
                (
                    profile name,
                    {
                        src1: dest1,
                        ...
                    }
                )
        """
        mappings = {}

        profile_name = u''
        while len(profile_name) == 0:
            profile_name = input(u'Profile name: ')

        file_ok = False
        while not file_ok:
            log_file = input(u'Log file absolute path to watch (empty if no log to watch): ')
            try:
                if len(log_file)==0:
                    break
                elif os.path.exists(log_file):
                    mappings[self.KEY_LOG_FILE] = log_file
                    file_ok = True
                else:
                    print(u' --> Specified file does not exist')
            except:
                pass

        print(u'')
        print(u'Now add mappings: source from repository root (local dir) <=> full destination path (remote dir)')
        print(u'Type "q" to stop adding mappings.')
        
        while True:
            print(u'')
            src = u''
            while len(src) == 0:
                src = input(u'Source directory (cannot be empty): ')
                if src == u'q':
                    break
            if src == u'q':
                break

            dest = u''
            while len(dest) == 0:
                dest = input(u'Destination directory (cannot be empty): ')
                if dest == u'q':
                    break
                if not os.path.exists(dest):
                    print(u' --> Specified path does not exist')
                    dest = u''
            if dest == u'q':
                break

            link = u''
            link_ok = False
            while not link_ok:
                link = input(u'Create symbolic link into directory (empty when no link): ')
                if link == u'q' or link == u'':
                    break
                if not os.path.exists(link):
                    print(u' --> Specified path does not exist')
                    link_ok = False
                link_ok = True
            if link == u'q':
                break

            #save new mapping
            mappings[src] = u'%s%s%s' % (dest, SEPARATOR, link)

        #return new profile
        return (
            profile_name,
            mappings
        )

    def _get_profile_entry_string(self, profile_name, profile):
        """
        Return profile entry string

        Return:
            string: entry string
        """
        mapping = u''
        log_file = u''

        #read log file path
        if self.KEY_LOG_FILE in list(profile.keys()):
            log_file = 'log file %s and ' % profile[self.KEY_LOG_FILE]

        #read mappings
        for src in list(profile[u'mappings'].keys()):
            dest = profile[u'mappings'][src][u'dest']
            link = u''
            if profile[u'mappings'][src][u'link']:
                link = u' & %s' % profile[u'mappings'][src][u'link']
                
            mapping += u'[%s=>%s%s]' % (src, dest, link)

        return u'%s: %s%d mappings %s' % (profile_name, log_file, len(profile), mapping)