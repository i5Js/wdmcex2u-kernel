#!/bin/sh
set -eu

recovery_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
control=/usr/local/sbin/wdnas-hw-control
unit=/etc/systemd/system/wdnas-hw-control.service

# Refuse to retire files changed by another session since installation.
cd "$recovery_dir"
sha256sum -c installed.sha256
systemctl disable --now wdnas-hw-control.service
"$control" fan 255
"$control" led-blink
mkdir retired
mv "$control" retired/wdnas-hw-control
mv "$unit" retired/wdnas-hw-control.service
systemctl daemon-reload
printf '%s\n' 'Retired this controller. Fan remains at maximum PWM.'
