#!/bin/bash

build_kernel()
(
    set -e
    set -o pipefail

    # Keep cache paths below cache_dir, including for explicitly selected tags.
    [[ $kernel_branch =~ ^[a-zA-Z0-9][a-zA-Z0-9._-]*$ && $kernel_branch != *..* ]] ||
        exit_with_error "Invalid kernel reference"
    if [[ $kernel_branch == linux-* ]]; then
        kernel_dir="${cache_dir}/${kernel_branch}"
        kernel_config="${current_dir}/config/${kernel_branch}.config"
    else
        kernel_dir="${cache_dir}/linux-${kernel_branch}"
        kernel_config="${current_dir}/config/linux-${kernel_branch}.config"
    fi

    mkdir -p "${cache_dir}" "${boot_dir}"
    if [[ ! -d ${kernel_dir} ]]; then
        git clone --branch "$kernel_branch" --depth 1 \
            https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git "${kernel_dir}"
    elif [[ $CLEAN_KERNEL_SRC == on ]]; then
        git -C "${kernel_dir}" fetch --depth 1 origin "$kernel_branch"
        git -C "${kernel_dir}" checkout -f -q FETCH_HEAD
        git -C "${kernel_dir}" clean -qdf
    fi

    source_version=$(grab_version "${kernel_dir}")
    modern_trial=off
    if [[ $source_version == 6.12.* ]]; then
        modern_trial=on
        kernel_config="${current_dir}/config/linux-6.1.y.config"
    elif [[ ! -f ${kernel_config} ]]; then
        kernel_config="${current_dir}/config/linux-default.config"
    fi
    cp "${kernel_config}" "${kernel_dir}/.config"

    dtb_name=armada-385-wdmc-Ex2-Ultra
    dts_subdir=
    if [[ -d ${kernel_dir}/arch/arm/boot/dts/marvell ]]; then
        dts_subdir=marvell/
    fi
    cp "${current_dir}/dts/${dtb_name}.dts" "${kernel_dir}/arch/arm/boot/dts/${dts_subdir}"
    dtb_target="${dts_subdir}${dtb_name}.dtb"
    dtb_makefile="${kernel_dir}/arch/arm/boot/dts/${dts_subdir}Makefile"
    if ! grep -Fq "${dtb_name}.dtb" "$dtb_makefile"; then
        printf '\ndtb-$(CONFIG_MACH_ARMADA_38X) += %s.dtb\n' "$dtb_name" >> "$dtb_makefile"
    fi

    cd "${kernel_dir}"
    if [[ $modern_trial == on ]]; then
        scripts/kconfig/merge_config.sh -m .config "${current_dir}/config/linux-6.12.y.fragment"
    fi
    [[ $ALLOW_KERNEL_CONFIG_CHANGES != on ]] || "${makehelp[@]}" menuconfig
    "${makehelp[@]}" olddefconfig
    if [[ $modern_trial == on ]]; then
        bash "${current_dir}/tools/check-boot-config.sh" .config
    fi
    kernel_version=$("${makehelp[@]}" -s kernelrelease)
    modules_dir="${output_dir}/lib/modules/${kernel_version}"
    [[ ! -d $modules_dir ]] || rm -rf -- "$modules_dir"

    "${makehelp[@]}" -j"${THREADS}" zImage "$dtb_target" modules
    cat arch/arm/boot/zImage "arch/arm/boot/dts/${dtb_target}" > zImage_and_dtb
    mkimage -A arm -O linux -T kernel -C none -a 0x00008000 -e 0x00008000 \
        -n "WD EX2 Ultra ${kernel_version}" -d zImage_and_dtb "${boot_dir}/uImage-${kernel_version}"
    "${makehelp[@]}" -j"${THREADS}" INSTALL_MOD_PATH="${output_dir}" modules_install
    rm -f -- "${modules_dir}/source" "${modules_dir}/build"

    cp .config "${boot_dir}/linux-${kernel_version}.config"
    cp System.map "${boot_dir}/System.map-${kernel_version}"
    cp "arch/arm/boot/dts/${dtb_target}" "${boot_dir}/${dtb_name}-${kernel_version}.dtb"
    # Legacy rootfs creation still consumes this file. The 6.12 trial archive
    # packages the versioned kernel, config, map and DTB.
    cp "${current_dir}/prebuilt/uRamdisk" "${boot_dir}/uRamdisk"
    chmod 755 "${boot_dir}/uImage-${kernel_version}" "${boot_dir}/uRamdisk"

    source_commit=$(git rev-parse HEAD)
    builder_commit=$(git -C "${current_dir}" rev-parse HEAD)
    compiler_version=$("${CROSS_COMPILE:-arm-linux-gnueabihf-}gcc" -dumpfullversion)
    python3 - "$output_dir" "$kernel_branch" "$source_commit" "$builder_commit" "$kernel_version" "$compiler_version" <<'PY'
import json
from pathlib import Path
import sys

output, ref, source, builder, release, compiler = sys.argv[1:]
Path(output, f"build-{release}.json").write_text(json.dumps({
    "kernel_ref": ref, "kernel_commit": source, "builder_commit": builder,
    "kernel_release": release, "compiler_version": compiler,
}, indent=2) + "\n")
PY
    printf '%s\n' "$kernel_version" > "${output_dir}/kernel-release"
    cd "${output_dir}"
    tar -czf "modules-${kernel_version}.tar.gz" -C lib/modules "$kernel_version"
    if [[ $modern_trial == on ]]; then
        tar -czf "boot-${kernel_version}.tar.gz" \
            "boot/uImage-${kernel_version}" "boot/linux-${kernel_version}.config" \
            "boot/System.map-${kernel_version}" "boot/${dtb_name}-${kernel_version}.dtb"
    else
        cp "boot/uImage-${kernel_version}" boot/uImage
        tar -czf "boot-${kernel_version}.tar.gz" boot/uRamdisk boot/uImage \
            "boot/uImage-${kernel_version}" "boot/linux-${kernel_version}.config"
        rm boot/uImage
    fi
    sha256sum "boot-${kernel_version}.tar.gz" "modules-${kernel_version}.tar.gz" \
        "build-${kernel_version}.json" > "SHA256SUMS-${kernel_version}"
    if [[ $GHRUNNER != on ]]; then
        chown "${current_user}:sudo" "boot-${kernel_version}.tar.gz" \
            "modules-${kernel_version}.tar.gz" "build-${kernel_version}.json" \
            "SHA256SUMS-${kernel_version}" kernel-release
    fi
)
