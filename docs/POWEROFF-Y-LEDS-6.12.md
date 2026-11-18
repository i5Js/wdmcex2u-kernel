# EX2 Ultra — apagado físico y LED de las bahías

## Candidato del 18 de noviembre de 2026

El objetivo de compilación produce `6.12.118-wdex2u-wol1`, con módulos propios bajo `/lib/modules/6.12.118-wdex2u-wol1/`. Parte del mismo tag `v6.12.118` de la primera compilación y añade el soporte de apagado físico de la placa. El arranque y el ciclo de apagado y Wake-on-LAN requieren verificación en el NAS.

La revisión del kernel 6.0.13 instalado confirmó `CONFIG_POWER_RESET` desactivado. La orden de apagado de OMV retiró los servicios y la red, mientras el propietario observaba ventilación y pilotos activos. El equipo siguió inaccesible después de los paquetes WOL y se recuperó al reconectar la alimentación. El regulador térmico ordena ventilación máxima al detenerse.

## Controlador de apagado

La receta aplica `patches/linux-6.12/0001-power-reset-qnap-add-wd-ex2-ultra.patch` sobre el controlador existente `qnap-poweroff.c`. Se incorpora un perfil para el EX2 Ultra, a 19200 baudios, que envía la trama Weltrend `fa 03 03 01 00 00 fb` con cinco milisegundos entre bytes. Se conservan las órdenes originales de un byte de QNAP y Synology. [Controlador base Linux 6.12.118](https://github.com/gregkh/linux/blob/v6.12.118/drivers/power/reset/qnap-poweroff.c), [protocolo Weltrend](https://github.com/c-MM/mcm-daemon/blob/master/mcm.h).

El Device Tree enlaza el nodo de apagado de UART1 con `wd,ex2-ultra-poweroff`. La configuración y las comprobaciones de compilación exigen `POWER_RESET=y` y `POWER_RESET_QNAP=y`. El controlador toma la UART en el último paso de apagado, después de detener los servicios y sincronizar los sistemas de archivos.

## LED de los discos

Los dos LED azules usan GPIO53 y GPIO54 y quedan encendidos por defecto al iniciar el kernel. Se exigen integrados `NEW_LEDS`, `LEDS_CLASS` y `LEDS_GPIO`. Cada bahía conserva su nombre en `/sys/class/leds/`, `wdmcex2u:blue:hdd1` y `wdmcex2u:blue:hdd2`. La apariencia y la correspondencia física se comprueban con el propietario.

## Compilación y prueba

```sh
gh workflow run compile-kernel.yml --repo i5Js/wdmcex2u-kernel --ref codex/wdnas-wol-poweroff-6.12 -f kernelversion=v6.12.118
```

Antes de seleccionar el kernel nuevo, guardar fuera del NAS el kernel y el initramfs activos con sus SHA-256, conservar copias versionadas y preparar su reposición. Instalar los módulos en su directorio propio y ejecutar `depmod` para esa identificación. Los datos de las bahías y la raíz USB se comparten durante la prueba.

Una prueba sin consola serie exige acceso físico al USB para volver a colocar el kernel conocido si falla el arranque por red. El cambio del archivo activo debe realizarse mediante renombrado dentro del mismo sistema de archivos y una sincronización completa antes del reinicio. La recuperación repone únicamente el archivo de arranque cuyo hash coincida con el candidato instalado.

Comprobar identificación del kernel, raíz USB, RAID1, VLAN de administración y datos, servicios OMV, control térmico y ambos LED. Confirmar WOL persistido en OMV, `Wake-on: g` y la alimentación de espera del equipo después de un apagado completo. Enviar el paquete desde la VLAN conectada y comprobar un nuevo identificador de arranque.
