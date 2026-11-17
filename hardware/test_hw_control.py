import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("control", Path(__file__).with_name("wdnas_hw_control.py"))
control = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control)


class FanPolicyTests(unittest.TestCase):
    def test_thresholds(self):
        for cpu, disk, expected in [(55, 35, 0), (60, 35, 1), (70, 35, 2),
                                     (80, 35, 3), (55, 40, 1), (55, 45, 2), (55, 50, 3)]:
            with self.subTest(cpu=cpu, disk=disk):
                self.assertEqual(control.fan_level(cpu, [disk], 0), expected)

    def test_cooling_requires_both_sensors_and_hysteresis(self):
        self.assertEqual(control.fan_level(68, [42], 2), 2)
        self.assertEqual(control.fan_level(65, [44], 2), 2)
        self.assertEqual(control.fan_level(67, [43], 2), 1)

    def test_cooling_lowers_one_step(self):
        self.assertEqual(control.fan_level(40, [25], 3), 2)

    def test_sleeping_disks_are_not_zero_measurements(self):
        self.assertEqual(control.fan_level(75, [None, None], 0), 2)


class DiskSensorTests(unittest.TestCase):
    def test_active_temperature(self):
        result = subprocess.CompletedProcess([], 0, json.dumps({"temperature": {"current": 46}}))
        self.assertEqual(control.disk_temperature(result), 46)

    def test_sleeping_disk(self):
        data = {"smartctl": {"messages": [{"string": "Device is in STANDBY mode, exit(2)"}]}}
        result = subprocess.CompletedProcess([], 2, json.dumps(data))
        self.assertIsNone(control.disk_temperature(result))

    def test_missing_or_implausible_temperature_fails(self):
        for data in [{}, {"temperature": {"current": 200}}, {"temperature": {"current": True}}]:
            with self.assertRaises(ValueError):
                control.disk_temperature(subprocess.CompletedProcess([], 2, json.dumps(data)))


class ProtocolTests(unittest.TestCase):
    def test_temperature_response_and_ack(self):
        controller = control.Microcontroller(1)
        response = bytes.fromhex("fa020100007efb")
        with patch.object(controller, "read_frame", side_effect=[response, control.ACK]), \
                patch.object(control.termios, "tcflush"), \
                patch.object(control.os, "write", return_value=1), \
                patch.object(control.time, "sleep"):
            self.assertEqual(controller.fan_rpm(), 2381)

    def test_ack_is_required(self):
        controller = control.Microcontroller(1)
        with patch.object(controller, "read_frame", return_value=b"invalid"), \
                patch.object(control.termios, "tcflush"), \
                patch.object(control.os, "write", return_value=1), \
                patch.object(control.time, "sleep"):
            with self.assertRaises(ValueError):
                controller.set_fan(192)

    def test_fan_cannot_be_stopped(self):
        with self.assertRaises(ValueError):
            control.Microcontroller(1).set_fan(0)


class FailSafeTests(unittest.TestCase):
    def run_cycle(self, controller, disk_error=None):
        with patch.object(control, "STOP") as stop, \
                patch.object(control, "cpu_temperature", return_value=75), \
                patch.object(control, "disk_temperatures", return_value={"sdb": 45, "sdc": 46},
                             side_effect=disk_error), \
                patch.object(control, "publish_state") as publish:
            stop.is_set.side_effect = [False, True]
            stop.wait.return_value = False
            control.run(controller)
            return publish.call_args.args[0]

    def test_sensor_failure_uses_maximum(self):
        controller = unittest.mock.Mock()
        state = self.run_cycle(controller, ValueError("sensor failed"))
        self.assertEqual(state["pwm"], 255)
        self.assertEqual(state["error"], "sensor failed")
        controller.set_fan.assert_called_with(255)

    def test_stalled_fan_uses_maximum(self):
        controller = unittest.mock.Mock()
        controller.fan_rpm.return_value = 0
        state = self.run_cycle(controller)
        self.assertEqual(state["pwm"], 255)
        self.assertIn("zero RPM", state["error"])

    def test_successful_start_checks_tachometer_at_maximum(self):
        controller = unittest.mock.Mock()
        controller.fan_rpm.return_value = 4000
        state = self.run_cycle(controller)
        self.assertIsNone(state["error"])
        self.assertEqual(state["pwm"], 255)
        controller.ready.assert_called_once()


if __name__ == "__main__":
    unittest.main()
