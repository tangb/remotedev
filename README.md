# remotedev
This utility helps you developping with any language on your local environment and push your changes on a remote device such as Raspberry pi.

It does not help you debugging but it can returns your application output logs. It can also be embedded directly in your python application.

## Installation
Install it from pip
> pip install remotedev

This will install pyremotedev python module and pyremotedev binary.

## Compatibility
Pyremotedev has been tested on:
* Development environment on:
  * Debian/Raspbian
  * Windows (please make sure to add ```<python install dir>/scripts``` dir in your path)
* Application execution environment on:
  * Debian/Raspbian

Your remote host must have ssh server installed and running.

## How it works
This utility is supposed to be imported in your python application but you can launch it manually (in this case you can't get output logs) to synchronize your directories.

Remotedev opens a tunnel between your computer and your remote host. Then it opens sockets to transfer requests and retrieve logs. Files are sync on both sides (from local to remote and from remote to local).

### Profiles
This application is based on profiles (different profiles on DevEnv and ExecEnv).

DevEnv profile holds ip and port of your remote host while DevEnv profile holds directory mappings (and symlink) and log file path to watch.

An interactive console wizard can help you to create your profiles (both DevEnv and ExecEnv)

Typical usage: I'm developping my python application on my desktop computer from my cloned repository and want to test my code on my raspberry pi:
*  Python files from ```<repo>/sources/``` local dir can be mapped to ```/usr/lib/python2.7/dist-packages/<mypythonmodule>/```
*  Html files from ```<repo>/html``` local dir can be mapped to ```/opt/<mypythonapp>/html```
*  Binaries from ```<repo>/bin``` local dir can be mapped to ```/usr/local/bin/```
*  ...

You can also create symbolic links to uploaded files into another path. Typically python files from ```/usr/share/pyshared/<mypythonmodule>/``` can be symlinked to ```/usr/lib/python2.7/dist-packages/<mypythonmodule>/```

#### DevEnv profile example
```
[myapp]
  local_dir = /home/me/myapp/
  ssh_username = pi
  remote_host = 192.168.1.XX
  ssh_password = ******
  remote_port = 22
```

#### ExecEnv profile example
```
[myapp]
  mypython/ = /usr/share/pyshared/myapp/$_$/usr/lib/python2.7/dist-packages/myapp/
  mybin/ = /usr/bin/$_$
  log_file_path = /var/log/myapp.log
  myhtml/ = /opt/myapp/html/$_$
```

##### Joker
source path can contains ```*``` to match a default path to copy file if not mapping is found.

### Log handling
Remotedev is able to watch for application logs and write them in new dev env log file.

The local log file is called ```remote_<host>.log```.
 
If you embed pyremodev python module directly on your application, it can catches your application log messages (using new loghandler).

It also can watch for local file changes. To configure this case, simply fill log file entry in your profile.

Finally you can disable this feature.

Follow your remote logs using ```tail -f``` on the new remote log file or simply open the log file on your code editor.

## Manual launch
```
Usage: remotedev -E|--execenv -D|--devenv -f|--folder "folder to watch" <-c|--conf "config filepath"> <-p|--prof "profile name"> <-d|--debug> <-h|--help>
  -E|--execenv: launch remotedev with execution env behavior, send updated files from mapped directories to development env and send log messages.
  -D|--devenv: launch remotedev with development env behavior, send files from your cloned repo to remote.
  -c|--conf: configuration filepath. If not specify use user home dir one.
  -p|--prof: profile name to launch (doesn't launch wizard)
  -d|--debug: enable debug.
  -v|--version: display version.
  -h|--help: display this help.
```

### On development environment
To manage profiles or choose one:
> pyremotedev --devenv

To directly launch application and bypass wizard
> pyremotedev --devenv --prof "myprofile"

### On application execution environment
To manage profiles or choose one:
> pyremotedev --execenv

To directly launch application and bypass wizard
> pyremotedev --execenv --prof "myprofile"

## Embed PyRemoteDev in your application (execution env side)
Example of how to embed pyremotedev in your code to 
```
from pyremotedev import pyremotedev
from threading import Thread
import logging

#create profile
PROFILE = {
    u'raspiot/': {
        u'dest': u'/usr/share/pyshared/raspiot/',
        u'link': u'/usr/lib/python2.7/dist-packages/raspiot/'
    },
    u'html/': {
        u'dest': u'/opt/raspiot/html/',
        u'link': None
    },
    u'bin/': {
        u'dest': u'/usr/bin/',
        u'link': None
    }
}

class MyPyRemoteDev(Thread):
  def __init__(self):
    Thread.__init__(self)
    self.running = True
    
  def stop(self):
    self.running = False
    
  def run(self):
    slave = None
    try:
      #start pyremotedev with internal remote logging (catch all message from app logger)
      slave = pyremotedev.PyRemoteDevSlave(PROFILE, remote_logging=True)
      slave.start()

      while self.running:
        time.sleep(0.25)

    except:
      logging.exception(u'Exception occured during pyremotedev execution:')

    finally:
      slave.stop()

    slave.join()
```

## RemoteDev as service
You can launch remotedev as service (only available on linux env).
```
With systemd:
systemctl start remotedev.service

With init:
/etc/init.d/remotedev start
```

### Configuration
By default remotedev service will load your first profile and start with execution env behavior, but you can override this behavior specifying the profile to launch on /etc/default/remotedev.conf.
