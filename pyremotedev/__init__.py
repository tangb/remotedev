from .version import __version__ as VERSION
try:
    #trick for install, some modules are not installed
    from .pyremotedev import PyRemoteDev, PyRemoteExec
    from .config import *
except:
    pass
