#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import logging
import getopt
import sys
import time
import platform
from appdirs import user_data_dir
from pyremotedev import pyremotedev, VERSION
from pyremotedev import config

logging.basicConfig(level=logging.INFO, format=u'%(asctime)s %(levelname)s [%(name)s:%(lineno)d]: %(message)s')

APP_NAME = u'remotedev'
APP_AUTHOR = u'tangb'

#main logger
logger = logging.getLogger(u'main')

#default config (linux only)
DAEMON_PROFILE_NAME = None
DAEMON_MODE = None
if platform.system() == 'Linux' and os.path.exists('/etc/default/remotedev.conf'):
    exec(open('/etc/default/remotedev.conf').read(), globals())


def reset_logging(level, to_file=None):
    """
    Reset main logging
    """
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    if to_file:
        logging.basicConfig(filename=to_file, level=level, format=u'%(asctime)s %(levelname)s [%(name)s:%(lineno)d]: %(message)s')
    else:
        logging.basicConfig(level=level, format=u'%(asctime)s %(levelname)s [%(name)s:%(lineno)d]: %(message)s')

def usage(error=''):
    """
    Application usage
    Args:
        error (string): error message to display
    """
    if len(error) > 0:
        print(u'Error: %s' % error)
        print(u'')

    print(u'Usage: remotedev -E|--execenv -D|--devenv <-c|--conf "config filepath"> <-p|--prof "profile name"> <-d|--debug> <-h|--help>')
    print(u' -E|--execenv: launch remotedev with execution env behavior, send updated files from mapped directories to development env and send log messages.')
    print(u' -D|--devenv: launch remotedev with development env behavior, send files from your cloned repo to remote.')
    print(u' -c|--conf: configuration filepath. If not specify use user home dir one')
    print(u' -p|--prof: profile name to launch (doesn\'t launch wizard)')
    print(u' -d|--debug: enable debug.')
    print(u' -v|--version: display version.')
    print(u' -h|--help: display this help.')

def version():
    """
    Display version
    """
    print(u'%s version %s' % (os.path.splitext(__file__)[0], version.VERSION))

def application_parameters():
    """
    Parse command line and return list of application parameters

    Return:
        dict: list of application parameters::
            {
                execenv (bool): True if application is launched in execution environment
                devenv (bool): True if application is launched in development environment
                debug (bool): True if debug enabled
                conf (string): Path of config file to open
                prof (string): profile name to launch (drop startup select wizard)
            }
    """
    params = {
        u'execenv': False,
        u'devenv': False,
        u'conf' : None,
        u'prof': None,
        u'first_prof': False,
        u'log_level': logging.INFO,
        u'log_file': None
    }

    try:
        opts, args = getopt.getopt(sys.argv[1:], u'EDhdc:vp:S', [u'execenv', u'devenv', u'help', u'debug', u'conf=', u'version', u'prof=', u'service'])

        for opt, arg in opts:
            if opt in (u'-E', u'--execenv'):
                if params[u'devenv']:
                    raise Exception(u'You can\'t enable both execenv and devenv mode')
                params[u'execenv'] = True
            elif opt in (u'-D', u'--devenv'):
                if params['execenv']:
                    raise Exception(u'You can\'t enable both execenv and devenv mode')
                params[u'devenv'] = True
            elif opt in (u'-h', u'--help'):
                usage()
                sys.exit(2)
            elif opt in (u'-d', u'--debug'):
                params[u'log_level'] = logging.DEBUG
            elif opt in (u'-c', u'--conf'):
                params[u'conf'] = arg
                if not os.path.exists(params[u'conf']):
                    raise Exception(u'Specified config file does not exist (%s)' % params[u'conf'])
            elif opt in (u'-v', u'--version'):
                version()
                sys.exit(2)
            elif opt in (u'-p', u'--prof'):
                params[u'prof'] = arg
                #profile existence will be checked later
            elif opt in (u'-S', u'--service'):
                #daemon mode, use config from /etc/default/remotedev.conf
                params[u'log_file'] = u'/var/log/remotedev.log'
                if DAEMON_MODE == u'execenv':
                    params[u'execenv'] = True
                    params[u'devenv'] = False
                else:
                    params[u'execenv'] = False
                    params[u'devenv'] = True
                if DAEMON_PROFILE_NAME:
                    params[u'prof'] = DAEMON_PROFILE_NAME
                    params[u'first_prof'] = False
                else:
                    params[u'first_prof'] = True

        #check some parameters
        if not params[u'execenv'] and not params[u'devenv']:
            #select devenv by default
            params[u'devenv'] = True
            params[u'execenv'] = False

        #default config path
        if params[u'conf'] is None:
            path = user_data_dir(APP_NAME, APP_AUTHOR)
            if params[u'execenv']:
                params[u'conf'] = os.path.join(path, u'execenv.conf')
            else:
                params[u'conf'] = os.path.join(path, u'devenv.conf')

    except Exception as e:
        #logger.exception('Error parsing command line arguments:')
        usage(str(e))
        sys.exit(1)

    return params

def load_profile(params):
    """
    Load profile to run

    Args:
        params (dict): application parameters
    """
    #load conf according to execenv/devenv switch
    if params[u'execenv']:
        conf = config.ExecEnvConfigFile(params[u'conf'])
    else:
        conf = config.DevEnvConfigFile(params[u'conf'])

    profile = None
    if params[u'first_prof']:
        #load first profile
        profiles = conf.load()
        if len(profiles) == 0:
            logger.fatal(u'No profile exists. Unable to start.')
            sys.exit(1)
        profile = profiles[profiles.keys()[0]]

    elif params[u'prof'] is None:
        #show profile wizard
        profile = conf.select_profile()

    else:
        #profile selected from command line
        profiles = conf.load()
        if params[u'prof'] not in profiles.keys():
            logger.fatal(u'Profile "%s" does not exist.' % params[u'prof'])
            sys.exit(1)
        profile = profiles[params[u'prof']]

    logger.debug(u'Selected profile: %s' % profile)
    return profile

#get application parameters
params = application_parameters()

#reset logging
reset_logging(params[u'log_level'], params[u'log_file'])

#load application profile
profile = load_profile(params)
logger.debug('Using profile %s' % profile)

if params[u'execenv']:
    logger.info(u'Starting remotedev in ExecEnv mode')
    try:
        execenv = pyremotedev.PyRemoteExec(profile)
        execenv.start()
        while execenv.isAlive():
            execenv.join(1.0)

    except KeyboardInterrupt:
        pass

    except:
        logger.exception(u'Exception occured during execenv process:')

    finally:
        logger.info(u'Stopping application...')
        execenv.stop()

    execenv.join()

else:
    logger.info(u'Starting remotedev in DevEnv mode')
    try:
        devenv = pyremotedev.PyRemoteDev(profile)
        devenv.start()
        while True:
            time.sleep(1.0)

    except KeyboardInterrupt:
        pass

    except:
        logger.exception(u'Exception occured during devenv process:')

    finally:
        logger.info(u'Stopping application...')
        devenv.stop()

    devenv.join()
