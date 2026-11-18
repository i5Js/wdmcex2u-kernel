# EX2 Ultra — apagado físico y LED de las bahías

## Candidato del 18 de noviembre de 2026

El objetivo de compilación produce `6.12.118-wdex2u-wol1`, con módulos propios bajo `/lib/modules/6.12.118-wdex2u-wol1/`. Parte del mismo tag `v6.12.118` de la primera compilación y añade el soporte de apagado físico de la placa.

## Primera prueba física

La compilación Actions `44342375149` terminó correctamente con el constructor `129807421624403479dc1014be5bf4f25e92e67c` y el commit estable `b869a5313cbfe7102873d3de318ddb68675146d0`. Se comprobaron las CRC de U-Boot, el DTB concatenado, el controlador integrado y los 272 módulos. El kernel ocupa 4960910 bytes, con SHA-256 `64530b234ee7d3cc7c5fe353adaadfc2df1fd60bce5ffa8a3d613f4a5dd0323e`.

El primer reinicio arrancó el candidato por SSH. El RAID1 quedó `[UU]`, los servicios activos, ambas VLAN operativas y el regulador térmico reconoció los discos aunque cambiara su orden de enumeración. El controlador `qnap_power_off` quedó vinculado al nodo de apagado.

El propietario confirmó la parada del ventilador y de los pilotos frontales después del apagado desde OMV. La luz Ethernet seguía activa. Los primeros ensayos de despertar fallaron. La entrega por el último switch se comprobó mediante una tanda de 19 paquetes y el incremento exacto de 19 broadcasts por el puerto del NAS, con cero errores.

El PHY conservaba `Wake-on: g` pero tenía deshabilitada la interrupción WOL. Se comprobó que repetir `wol g`, incluso mediante ioctl, omite la escritura cuando las opciones coinciden. Tras desactivar y activar realmente `WAKE_MAGIC`, la máscara pasó de cero a `0x0080`. El siguiente paquete desde el router produjo un nuevo arranque con este kernel. El servicio de rearme para OMV está documentado en [hardware](../hardware/README.md#rearme-de-wake-on-lan-en-omv).

Se completaron dos ciclos de apagado y despertar. El segundo utilizó el servicio persistente y el propietario confirmó el encendido. En ambos, SSH respondió aproximadamente 61 segundos después del paquete. En el arranque final se verificó la ejecución automática del helper, el registro de interrupciones `0x0080`, RAID sano, ambas VLAN y control térmico activo.

Se inició una compilación experimental `wol2` con otros parámetros MCU del mantenedor. Al confirmar el despertar con `wol1`, se canceló esa compilación y se revirtió el cambio experimental mediante un nuevo commit.

Linux expone ambos LED azules con brillo 1, pero el propietario los observa apagados. La correspondencia física queda pendiente y el propietario prioriza completar WOL.

La revisión del kernel 6.0.13 instalado confirmó `CONFIG_POWER_RESET` desactivado. La orden de apagado de OMV retiró los servicios y la red, mientras el propietario observaba ventilación y pilotos activos. El equipo siguió inaccesible después de los paquetes WOL y se recuperó al reconectar la alimentación. El regulador térmico ordena ventilación máxima al detenerse.

## Controlador de apagado

La receta aplica `patches/linux-6.12/0001-power-reset-qnap-add-wd-ex2-ultra.patch` sobre el controlador existente `qnap-poweroff.c`. Se incorpora un perfil para el EX2 Ultra, a 19200 baudios, que envía la trama Weltrend `fa 03 03 01 00 00 fb` con cinco milisegundos entre bytes. Los perfiles QNAP y Synology utilizan sus órdenes de un byte. [Controlador base Linux 6.12.118](https://github.com/gregkh/linux/blob/v6.12.118/drivers/power/reset/qnap-poweroff.c), [protocolo Weltrend](https://github.com/c-MM/mcm-daemon/blob/master/mcm.h).

El Device Tree enlaza el nodo de apagado de UART1 con `wd,ex2-ultra-poweroff`. La configuración y las comprobaciones de compilación exigen `POWER_RESET=y` y `POWER_RESET_QNAP=y`. El controlador toma la UART en el último paso de apagado, después de detener los servicios y sincronizar los sistemas de archivos.

## LED de los discos

Los dos LED azules usan GPIO53 y GPIO54 y quedan encendidos por defecto al iniciar el kernel. Se exigen integrados `NEW_LEDS`, `LEDS_CLASS` y `LEDS_GPIO`. Cada bahía conserva su nombre en `/sys/class/leds/`, `wdmcex2u:blue:hdd1` y `wdmcex2u:blue:hdd2`. La apariencia y la correspondencia física se comprueban con el propietario.

## Compilación y prueba

Actions obtiene el tag del espejo del mantenedor estable `gregkh/linux`. El constructor admite `KERNEL_SOURCE_URL` y conserva kernel.org como valor predeterminado para las invocaciones locales. El manifiesto registra el commit fuente y el commit del constructor.

```sh
gh workflow run compile-kernel.yml --repo i5Js/wdmcex2u-kernel --ref codex/wdnas-wol-poweroff-6.12 -f kernelversion=v6.12.118
```

Antes de seleccionar el kernel nuevo, guardar fuera del NAS el kernel y el initramfs activos con sus SHA-256, conservar copias versionadas y preparar su reposición. Instalar los módulos en su directorio propio y ejecutar `depmod` para esa identificación. Los datos de las bahías y la raíz USB se comparten durante la prueba.

Una prueba sin consola serie exige acceso físico al USB para volver a colocar el kernel conocido si falla el arranque por red. El cambio del archivo activo debe realizarse mediante renombrado dentro del mismo sistema de archivos y una sincronización completa antes del reinicio. La recuperación repone únicamente el archivo de arranque cuyo hash coincida con el candidato instalado.

Comprobar identificación del kernel, raíz USB, RAID1, VLAN de administración y datos, servicios OMV, control térmico y ambos LED. Confirmar WOL persistido en OMV, `Wake-on: g` y la alimentación de espera del equipo después de un apagado completo. Enviar el paquete desde la VLAN conectada y comprobar un nuevo identificador de arranque.
