#!/usr/bin/python3
"""Rearm the EX2 Ultra PHY when Wake-on-LAN is enabled in OMV."""

import ctypes
import fcntl
import json
from pathlib import Path
import socket
import struct
import subprocess


SIOCETHTOOL = 0x8946
ETHTOOL_GWOL = 0x00000005
ETHTOOL_SWOL = 0x00000006
WAKE_MAGIC = 1 << 5


class WolInfo(ctypes.Structure):
    _fields_ = [
        ("cmd", ctypes.c_uint32),
        ("supported", ctypes.c_uint32),
        ("wolopts", ctypes.c_uint32),
        ("sopass", ctypes.c_uint8 * 6),
    ]


def arm_wol():
    interfaces = json.loads(subprocess.check_output([
        "omv-confdbadm", "read", "conf.system.network.interface"
    ], text=True))
    interface = next(item for item in interfaces if item["devicename"] == "eth0")
    if not interface["wol"]:
        print("OMV Wake-on-LAN is disabled for eth0")
        return

    info = WolInfo(cmd=ETHTOOL_GWOL)
    request = bytearray(32 if ctypes.sizeof(ctypes.c_void_p) == 4 else 40)
    request[:16] = b"eth0".ljust(16, b"\0")
    struct.pack_into("@P", request, 16, ctypes.addressof(info))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as control:
        fcntl.ioctl(control.fileno(), SIOCETHTOOL, request)
        if not info.supported & WAKE_MAGIC:
            raise RuntimeError("eth0 PHY does not support magic-packet wakeup")
        desired = info.wolopts | WAKE_MAGIC
        # Both ioctl and netlink skip unchanged options. Toggle WAKE_MAGIC so
        # the PHY setter reprograms its MAC matcher and WOL interrupt.
        try:
            if info.wolopts & WAKE_MAGIC:
                info.cmd = ETHTOOL_SWOL
                info.wolopts = desired & ~WAKE_MAGIC
                fcntl.ioctl(control.fileno(), SIOCETHTOOL, request)
                info.cmd = ETHTOOL_GWOL
                fcntl.ioctl(control.fileno(), SIOCETHTOOL, request)
                if info.wolopts & WAKE_MAGIC:
                    raise RuntimeError("eth0 PHY did not clear magic-packet wakeup")
            info.cmd = ETHTOOL_SWOL
            info.wolopts = desired
            fcntl.ioctl(control.fileno(), SIOCETHTOOL, request)
            info.cmd = ETHTOOL_GWOL
            fcntl.ioctl(control.fileno(), SIOCETHTOOL, request)
            if not info.wolopts & WAKE_MAGIC:
                raise RuntimeError("eth0 PHY did not retain magic-packet wakeup")
        except (OSError, RuntimeError):
            info.cmd = ETHTOOL_SWOL
            info.wolopts = desired
            fcntl.ioctl(control.fileno(), SIOCETHTOOL, request)
            raise

    mac = Path("/sys/class/net/eth0/address").read_text().strip()
    print("WOL rearmed for eth0 with MAC " + mac)


if __name__ == "__main__":
    arm_wol()
