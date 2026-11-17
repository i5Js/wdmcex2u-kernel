#!/bin/bash
set -euo pipefail

config=${1:?Pass the generated kernel .config}
required=(
    ARM_APPENDED_DTB ARM_ATAG_DTB_COMPAT ARM_ATAG_DTB_COMPAT_CMDLINE_FROM_BOOTLOADER
    BLK_DEV_INITRD RD_GZIP DEVTMPFS DEVTMPFS_MOUNT SCSI BLK_DEV_SD
    USB_STORAGE USB_XHCI_HCD USB_XHCI_PLATFORM USB_XHCI_MVEBU USB_EHCI_HCD_ORION
    EXT4_FS EXT4_USE_FOR_EXT2 AHCI_MVEBU BLK_DEV_MD MD_RAID1
    MVNETA MVMDIO MARVELL_PHY VLAN_8021Q SERIAL_8250 SERIAL_8250_CONSOLE
    SERIAL_OF_PLATFORM ARMADA_THERMAL REGULATOR_FIXED_VOLTAGE
    MTD_CMDLINE_PARTS MTD_RAW_NAND MTD_NAND_MARVELL MTD_UBI UBIFS_FS
)
for symbol in "${required[@]}"; do
    grep -qx "CONFIG_${symbol}=y" "$config" || {
        printf '%s\n' "Required built-in driver missing: CONFIG_${symbol}" >&2
        exit 1
    }
done
grep -qx 'CONFIG_LOCALVERSION="-wdex2u"' "$config"
printf '%s\n' 'USB boot, NAND MAC retrieval, SATA/RAID, UART, thermal and VLAN configuration verified'
