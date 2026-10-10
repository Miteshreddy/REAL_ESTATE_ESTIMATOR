"""Windows stand-in for the Unix-only 'pwd' module (SearXNG only uses it to log the user name when Valkey fails)."""
import getpass
from collections import namedtuple

struct_passwd = namedtuple("struct_passwd", "pw_name pw_passwd pw_uid pw_gid pw_gecos pw_dir pw_shell")


def getpwuid(uid=0):
    return struct_passwd(getpass.getuser(), "x", 0, 0, "", "", "")
