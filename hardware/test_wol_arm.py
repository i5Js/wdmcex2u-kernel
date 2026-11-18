import ctypes
import json
import struct
import unittest
from unittest.mock import patch

import wdnas_wol_arm as wol


class WolArmTests(unittest.TestCase):
    def exercise(self, enabled, initial=wol.WAKE_MAGIC, supported=33,
                 fail_first_enable=False):
        calls = []
        hardware_updates = []
        state = initial
        enable_failed = False

        def ioctl(fd, operation, request):
            nonlocal state, enable_failed
            self.assertEqual(operation, wol.SIOCETHTOOL)
            address = struct.unpack_from("@P", request, 16)[0]
            info = ctypes.cast(address, ctypes.POINTER(wol.WolInfo)).contents
            calls.append(info.cmd)
            if info.cmd == wol.ETHTOOL_GWOL:
                info.supported = supported
                info.wolopts = state
            else:
                if fail_first_enable and not enable_failed and info.wolopts & wol.WAKE_MAGIC:
                    enable_failed = True
                    raise OSError("Simulated enable failure")
                if info.wolopts != state:
                    state = info.wolopts
                    hardware_updates.append(state)

        configuration = json.dumps([{"devicename": "eth0", "wol": enabled}])
        with patch.object(wol.subprocess, "check_output", return_value=configuration), \
                patch.object(wol.fcntl, "ioctl", side_effect=ioctl), \
                patch.object(wol.socket, "socket"), \
                patch.object(wol.Path, "read_text", return_value="02:00:00:00:00:01\n"), \
                patch("builtins.print"):
            if fail_first_enable:
                with self.assertRaisesRegex(OSError, "Simulated enable failure"):
                    wol.arm_wol()
            else:
                wol.arm_wol()
        return calls, state, hardware_updates

    def test_disabled_omv_setting_skips_ioctl(self):
        calls, _, hardware_updates = self.exercise(False)
        self.assertEqual(calls, [])
        self.assertEqual(hardware_updates, [])

    def test_existing_magic_setting_still_runs_setter(self):
        calls, state, hardware_updates = self.exercise(True)
        self.assertEqual(calls, [wol.ETHTOOL_GWOL, wol.ETHTOOL_SWOL, wol.ETHTOOL_GWOL,
                                 wol.ETHTOOL_SWOL, wol.ETHTOOL_GWOL])
        self.assertEqual(state, wol.WAKE_MAGIC)
        self.assertEqual(hardware_updates, [0, wol.WAKE_MAGIC])

    def test_arms_magic_from_disabled_phy_state(self):
        _, state, hardware_updates = self.exercise(True, initial=0)
        self.assertEqual(state, wol.WAKE_MAGIC)
        self.assertEqual(hardware_updates, [wol.WAKE_MAGIC])

    def test_unsupported_magic_fails(self):
        with self.assertRaises(RuntimeError):
            self.exercise(True, supported=1)

    def test_preserves_other_wake_options(self):
        _, state, hardware_updates = self.exercise(True, initial=33)
        self.assertEqual(state, 33)
        self.assertEqual(hardware_updates, [1, 33])

    def test_failed_enable_restores_desired_options(self):
        _, state, hardware_updates = self.exercise(True, fail_first_enable=True)
        self.assertEqual(state, wol.WAKE_MAGIC)
        self.assertEqual(hardware_updates, [0, wol.WAKE_MAGIC])
