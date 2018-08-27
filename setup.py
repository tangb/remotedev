import platform
import os
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup
from pyremotedev import VERSION
from setuptools.command.install import install
import subprocess

SYSTEMD_SERVICE = """[Unit]
Description=RemoteDev
After=network-online.target
Requires=network-online.target

[Service]
ExecStart=/usr/bin/remotedev --service
WorkingDirectory=/usr/local/bin
StandardOutput=syslog
StandardError=syslog
Restart=always
RestartSec=10
User=root
[Install]
WantedBy=multi-user.target"""

SYSVINIT_SERVICE = """#!/bin/sh
### BEGIN INIT INFO
# Provides: remotedev
# Required-Start:   $syslog $local_fs 
# Required-Stop:    $syslog $local_fs 
# Default-Start:    2 3 4 5
# Default-Stop:     0 1 6
# Short-Description: Sync your dev env with execution env
### END INIT INFO

. /lib/lsb/init-functions

BIN_PATH=/usr/local/bin/
PID_PATH=/var/run/
DAEMON_USER=root
DAEMON_GROUP=root
APP=remotedev
DESC=Sync your dev env with execution env

start_module() {
    start-stop-daemon --start --quiet --background --chuid $DAEMON_USER:$DAEMON_GROUP --pidfile "$3" --make-pidfile --exec "$2" -- "$4"
    if [ $? -ne 0 ]; then
        log_failure_msg "Failed"
        exit 1
    fi
    if [ $? -eq 0 ]; then
        log_success_msg "Done"
    fi
}

start() {
    echo "Starting $DESC..."
    if [ -f "$BIN_PATH$APP" ]
    then
        start_module "$APP" "$BIN_PATH$APP" "$PID_PATH$APP.pid" "--service"
    fi
}

stop_module() {
    start-stop-daemon --stop --quiet --oknodo --pidfile "$3"
    if [ $? -ne 0 ]; then
        log_failure_msg "Failed"
        exit 1
    fi
    if [ $? -eq 0 ]; then
        log_success_msg "Done"
    fi
}

stop() {
    echo "Stopping $DESC..."
    if [ -f "$BIN_PATH$APP" ]
    then
        stop_module "$APP" "$BIN_PATH$APP" "$PID_PATH$APP.pid"
    fi
}

force_reload() {
    stop
    start
}

status() {
    run=`pgrep -f $BIN_PATH$APP | wc -l`
    if [ $run -eq 1 ]
    then
        echo "$APP is running"
    else
        echo "$APP is NOT running"
    fi
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    force-reload)
        force_reload
        ;;
    restart)
        stop
        start
        ;;
    status)
        status
        ;;
    *)
        echo "Usage: $DESC {start|stop|force-reload|restart}"
        exit 2
esac
"""

DEFAULT_CONFIG = """DAEMON_PROFILE_NAME=None
DAEMON_MODE='execenv'
"""

class InstallExtraFiles(install):
    def run(self):
        #call parent 
        install.run(self)

        #install service only on raspbian
        if platform.system()!='Linux':
            return
        res = subprocess.Popen(u'cat /etc/os-release | grep -i raspbian | wc -l', stdout=subprocess.PIPE, shell=True)
        stdout = res.communicate()[0]
        if stdout.strip()=='0':
            return

        #create service file
        if os.path.exists('/lib/systemd/system/'):
            #systemd service
            fd = open('/lib/systemd/system/remotedev.service', 'w+')
            fd.write(SYSTEMD_SERVICE)
            fd.close()

        else:
            #sysvinit service
            fd = open('/etc/init.d/remotedev', 'w+')
            fd.write(SYSVINIT_SERVICE)
            fd.close()

        #default config
        if os.path.exists('/etc/default'):
            fd = open('/etc/default/remotedev.conf', 'w+')
            fd.write(DEFAULT_CONFIG)
            fd.close()

setup(
    name = 'remotedev',
    version = VERSION,
    description = 'Sync your development env to your application execution env',
    author = 'Tanguy Bonneau',
    author_email = 'tanguy.bonneau@gmail.com',
    maintainer = 'Tanguy Bonneau',
    maintainer_email = 'tanguy.bonneau@gmail.com',
    url = 'http://www.github.com/tangb/remotedev/',
    packages = ['remotedev'],
    include_package_data = True,
    install_requires = ['watchdog>=0.8.3', 'bson>=0.5.6', 'sshtunnel>=0.1.4', 'appdirs>=1.4.3', 'pygtail>=0.8.0'],
    scripts = ['bin/remotedev', 'bin/remotedev.py'],
    cmdclass = {'install': InstallExtraFiles}
)
