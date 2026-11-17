#!/usr/bin/python3
"""Power LED and temperature-based fan control for the WD EX2 Ultra.

Weltrend protocol reference: https://github.com/c-MM/mcm-daemon/blob/master/mcm.h
Uses only the Python standard library and smartctl. No network listener.
"""

import argparse
import contextlib
import copy
import fcntl
import json
import logging
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import termios
import threading
import time


ACK = bytes.fromhex("fa3000000000fb")
PWM_LEVELS = (96, 128, 192, 255)
TEMPERATURE_STEPS = ((60, 40), (70, 45), (80, 50))
STATE_PATH = Path("/run/wdnas-hw-control/status.json")
STOP = threading.Event()


class Microcontroller:
    def __init__(self, fd):
        self.fd = fd

    def read_frame(self):
        data = bytearray()
        deadline = time.monotonic() + 2
        while len(data) < 7:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([self.fd], [], [], remaining)[0]:
                raise TimeoutError("MCU response timed out")
            chunk = os.read(self.fd, 7 - len(data))
            if not chunk:
                continue
            data.extend(chunk)
        if data[0] != 0xFA or data[-1] != 0xFB:
            raise ValueError("Invalid MCU frame")
        return bytes(data)

    def exchange(self, command, response=False):
        termios.tcflush(self.fd, termios.TCIFLUSH)
        for value in command:
            if os.write(self.fd, bytes([value])) != 1:
                raise OSError("Incomplete MCU write")
            time.sleep(0.001)
        data = self.read_frame()
        if response:
            if data[:3] != command[:3]:
                raise ValueError("Unexpected MCU response")
            ack = self.read_frame()
        else:
            ack = data
        if ack != ACK:
            raise ValueError("MCU did not acknowledge command")
        return data

    def set_fan(self, pwm):
        if not 64 <= pwm <= 255:
            raise ValueError("Fan PWM must be between 64 and 255")
        self.exchange(bytes([0xFA, 2, 0, pwm, 0, 0, 0xFB]))

    def fan_rpm(self):
        data = self.exchange(bytes.fromhex("fa0201000000fb"), response=True)
        return round(300000 / data[5]) if data[5] else 0

    def ready(self):
        self.exchange(bytes.fromhex("fa0301000000fb"))
        self.exchange(bytes.fromhex("fa2600110001fb"))

    def led_blink(self):
        self.exchange(bytes.fromhex("fa2600210001fb"))


@contextlib.contextmanager
def open_controller():
    fd = os.open("/dev/ttyS1", os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
    original = None
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        original = termios.tcgetattr(fd)
        attrs = copy.deepcopy(original)
        attrs[0] = attrs[1] = attrs[3] = 0
        attrs[2] = termios.CS8 | termios.CLOCAL | termios.CREAD
        attrs[4] = attrs[5] = termios.B19200
        attrs[6][termios.VMIN] = attrs[6][termios.VTIME] = 0
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
        yield Microcontroller(fd)
    finally:
        if original is not None:
            termios.tcsetattr(fd, termios.TCSANOW, original)
        os.close(fd)


def fan_level(cpu, disk_temperatures, previous):
    """Raise immediately. Lower one step with 3 C CPU / 2 C HDD hysteresis."""
    hottest_disk = max((t for t in disk_temperatures if t is not None), default=0)
    demand = 0
    for level, (cpu_limit, disk_limit) in enumerate(TEMPERATURE_STEPS, start=1):
        if cpu >= cpu_limit or hottest_disk >= disk_limit:
            demand = level
    if demand >= previous:
        return demand
    cpu_limit, disk_limit = TEMPERATURE_STEPS[previous - 1]
    if cpu <= cpu_limit - 3 and hottest_disk <= disk_limit - 2:
        return max(demand, previous - 1)
    return previous


def cpu_temperature():
    for zone in Path("/sys/class/thermal").glob("thermal_zone*"):
        if (zone / "type").read_text().strip().endswith(".thermal"):
            value = int((zone / "temp").read_text()) / 1000
            if not -20 <= value <= 150:
                raise ValueError("CPU sensor outside plausible range")
            return round(value, 1)
    raise ValueError("Armada thermal sensor unavailable")


def disk_temperature(result):
    data = json.loads(result.stdout)
    value = data.get("temperature", {}).get("current")
    if type(value) in (int, float) and 0 <= value <= 90:
        return value
    messages = data.get("smartctl", {}).get("messages", [])
    sleeping = any(re.search(r"\b(STANDBY|SLEEP)\b", m.get("string", ""))
                   for m in messages)
    if result.returncode == 2 and sleeping:
        return None
    raise ValueError("Active HDD temperature unavailable")


def disk_temperatures():
    temperatures = {}
    for disk in sorted(Path("/sys/block").glob("sd*")):
        if not re.search(r"/ata\d+/", str((disk / "device").resolve())):
            continue
        result = subprocess.run(
            ["/usr/sbin/smartctl", "-n", "standby", "-A", "-j", f"/dev/{disk.name}"],
            capture_output=True, text=True, timeout=4, check=False,
        )
        temperatures[disk.name] = disk_temperature(result)
    if len(temperatures) != 2:
        raise ValueError("Expected two internal SATA disks")
    return temperatures


def publish_state(state):
    STATE_PATH.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    temporary = STATE_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(state, sort_keys=True) + "\n")
    temporary.replace(STATE_PATH)


def run(controller):
    previous = len(PWM_LEVELS) - 1
    last_pwm = 255
    disks = {}
    disk_error = "HDD sensors not yet sampled"
    next_disk_sample = 0
    last_error = None
    fan_fault = True
    try:
        controller.set_fan(255)
        controller.ready()
        logging.info("MCU acknowledged system ready and steady blue power LED")
        while not STOP.is_set():
            cpu = None
            rpm = None
            error = None
            try:
                cpu = cpu_temperature()
                if time.monotonic() >= next_disk_sample:
                    try:
                        disks = disk_temperatures()
                        disk_error = None
                    except (OSError, ValueError, subprocess.SubprocessError) as exc:
                        disk_error = str(exc)
                    next_disk_sample = time.monotonic() + 60
                if disk_error:
                    raise ValueError(disk_error)
                level = 3 if fan_fault else fan_level(cpu, disks.values(), previous)
                pwm = PWM_LEVELS[level]
                controller.set_fan(pwm)
                # Allow spin-up / spin-down before checking the tachometer.
                if STOP.wait(3):
                    break
                rpm = controller.fan_rpm()
                if rpm <= 0:
                    raise ValueError("Fan tachometer reports zero RPM")
                fan_fault = False
                previous = level
            except (OSError, ValueError) as exc:
                error = str(exc)
                pwm = 255
                previous = len(PWM_LEVELS) - 1
                fan_fault = True
                controller.set_fan(pwm)
            if pwm != last_pwm or error != last_error:
                logging.info("PWM=%s CPU=%s HDD=%s RPM=%s error=%s",
                             pwm, cpu, disks, rpm, error)
            last_pwm, last_error = pwm, error
            publish_state({
                "timestamp": time.time(), "cpu_c": cpu, "disks_c": disks,
                "pwm": pwm, "pwm_percent": round(pwm * 100 / 255),
                "rpm": rpm, "error": error,
            })
            STOP.wait(7)
    finally:
        controller.set_fan(255)
        logging.info("Controller stopped with fan at maximum PWM")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "ready", "led-blink", "fan", "run"))
    parser.add_argument("pwm", type=int, nargs="?")
    args = parser.parse_args()
    if args.command == "fan" and (args.pwm is None or not 64 <= args.pwm <= 255):
        parser.error("fan requires a PWM value between 64 and 255")
    if args.command != "fan" and args.pwm is not None:
        parser.error("PWM is only accepted by the fan command")
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if args.command == "status" and STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text())
        state["age_seconds"] = round(time.time() - state["timestamp"], 1)
        print(json.dumps(state, indent=2))
        return
    signal.signal(signal.SIGTERM, lambda *_: STOP.set())
    signal.signal(signal.SIGINT, lambda *_: STOP.set())
    with open_controller() as controller:
        if args.command == "run":
            run(controller)
        elif args.command == "ready":
            controller.ready()
            print("MCU acknowledged system ready and steady blue power LED")
        elif args.command == "led-blink":
            controller.led_blink()
            print("MCU acknowledged blinking blue power LED")
        elif args.command == "fan":
            controller.set_fan(args.pwm)
            print(f"MCU acknowledged fan PWM {args.pwm}")
        else:
            print(json.dumps({"rpm": controller.fan_rpm(), "cpu_c": cpu_temperature(),
                              "disks_c": disk_temperatures()}, indent=2))


if __name__ == "__main__":
    main()
