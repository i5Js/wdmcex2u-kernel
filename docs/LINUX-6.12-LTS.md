# Linux 6.12 LTS y pruebas con varios kernels

Los candidatos de apagado físico y Wake-on-LAN del 18 de noviembre se describen en [Apagado y LED de las bahías](POWEROFF-Y-LEDS-6.12.md). Las referencias `6.12.118-wdex2u` de este documento identifican la primera compilación del 17 de noviembre.

## Compilación

La referencia inicial es `v6.12.118`, publicada por kernel.org el 17 de noviembre de 2026. El objetivo genera la identificación `6.12.118-wdex2u`, con módulos en `/lib/modules/6.12.118-wdex2u/`. La rama estable puede seleccionarse también mediante `linux-6.12.y`. El tag fija la versión para poder repetir la prueba. [Fuentes y versiones oficiales](https://www.kernel.org/)

El camino 6.12 parte de la configuración de placa 6.1 existente, aplica `config/linux-6.12.y.fragment` y migra mediante `olddefconfig`. El script verifica los controladores integrados que necesita el arranque USB, incluyendo PHY, ext3 mediante ext4, UART, red, VLAN, SATA, RAID1 y la lectura NAND usada para recuperar la MAC. El Device Tree se compila desde el subdirectorio `marvell/` y se concatena a `zImage` para producir la imagen U-Boot.

### Desde GitHub Actions

Ejecutar el workflow en este fork, seleccionando la rama que se desea comprobar.

```sh
gh workflow run compile-kernel.yml --repo i5Js/wdmcex2u-kernel --ref codex/linux-6.12-lts -f kernelversion=v6.12.118
```

El workflow utiliza Ubuntu 24.04 y publica un artefacto llamado `wd-ex2-ultra-kernel`, con retención de 30 días. El manifiesto identifica el tag, el commit del kernel, el commit del constructor y la versión de GCC.

### Desde un equipo Linux

Con las dependencias instaladas, el modo de compilación aislado admite un usuario normal.

```sh
sudo apt-get install -y gcc-arm-linux-gnueabihf build-essential bc bison flex libssl-dev libelf-dev libncurses-dev u-boot-tools python3 git
./build.sh --ghrunner --kernel --clean --kernelbranch v6.12.118
```

El resultado aparece en `output/`.

| Archivo | Contenido |
| --- | --- |
| `boot-6.12.118-wdex2u.tar.gz` | Imagen de kernel, configuración final, System.map y DTB con nombres versionados |
| `modules-6.12.118-wdex2u.tar.gz` | Árbol de módulos de esa identificación de kernel |
| `build-6.12.118-wdex2u.json` | Procedencia de la compilación |
| `SHA256SUMS-6.12.118-wdex2u` | Sumas de los paquetes y del manifiesto |
| `kernel-release` | Identificación exacta producida por Kbuild |

El paquete de arranque 6.12 contiene únicamente nombres versionados. La preparación del arranque activo se realiza por separado.

## Varios kernels en el mismo USB

El EX2 Ultra examinado utiliza una partición USB MBR/ext3 con etiqueta `rootfs`. U-Boot carga por defecto `/boot/uImage` y `/boot/uRamdisk`. Se pueden conservar varios kernels en esa partición, con módulos separados por identificación, y elegir uno temporalmente desde la consola serie.

La organización de la prueba puede ser la siguiente.

```text
/boot/uImage                         arranque habitual conocido
/boot/uRamdisk                       initramfs habitual conocido
/boot/uImage-6.0.13                   copia del kernel conocido
/boot/uRamdisk-6.0.13                 copia del initramfs conocido
/boot/uImage-6.12.118-wdex2u           kernel de prueba
/lib/modules/6.0.13/                  módulos del sistema conocido
/lib/modules/6.12.118-wdex2u/          módulos del kernel de prueba
```

La selección temporal conserva los nombres habituales y las variables persistentes de U-Boot. Tras un reinicio vuelve a ejecutarse el arranque habitual. Una vez transferido el control al kernel, una parada temprana exige acceso local para recuperar el equipo. La consola serie proporciona el registro y el control necesarios en esa primera prueba.

Los kernels del mismo USB comparten el sistema raíz, la configuración y los discos conectados. La prueba debe comenzar con una copia recuperable de ese USB y del estado que pueda verse afectado.

## Preparación de la primera prueba

Esta sección describe una intervención de arranque que requiere autorización y una ventana de mantenimiento. Debe realizarse con consola UART de 3,3 V disponible y la copia recuperable comprobada.

1. Verificar las sumas de los artefactos descargados y la identidad `6.12.118-wdex2u` del manifiesto.
2. Comprobar las copias conocidas de kernel e initramfs y guardar sus sumas fuera del NAS.
3. Preparar una copia versionada del `uRamdisk` que utiliza actualmente el equipo.
4. Instalar los archivos versionados del paquete de arranque y los módulos en su directorio propio.
5. Ejecutar `depmod` para esa identificación y comprobar los módulos que utiliza la configuración de red y los servicios actuales.

Para un NAS cuyo sistema conocido es 6.0.13, los comandos de preparación, una vez autorizados y comprobada la ausencia de los destinos nuevos, son los siguientes.

```sh
cp -a /boot/uRamdisk /boot/uRamdisk-6.0.13
tar -xzf boot-6.12.118-wdex2u.tar.gz -C /
tar -xzf modules-6.12.118-wdex2u.tar.gz -C /lib/modules
depmod -a 6.12.118-wdex2u
```

La reutilización del initramfs presupone que la configuración comprobada conserva integrados sus controladores de arranque y que los programas ARMv7 existentes son compatibles. Esta condición se verifica en compilación y debe confirmarse durante el primer arranque físico.

## Selección temporal desde U-Boot

Las direcciones siguientes coinciden con el entorno guardado en el WD examinado. Confirmar primero sus valores y el USB elegido en la consola de ese equipo. La identificación del puerto puede requerir `usbActive 0` o `usbActive 1`, según dónde esté conectado el USB.

```text
printenv usbActive load_image load_initrd usb_set_bootargs
usb start
ext2ls usb 0:1 /boot
if ext2load usb 0:1 0x00800000 /boot/uImage-6.12.118-wdex2u; then if ext2load usb 0:1 0x02100000 /boot/uRamdisk-6.0.13; then run usb_set_bootargs; bootm 0x00800000 0x02100000; fi; fi
```

El DTB viaja concatenado al kernel. La orden utiliza los argumentos USB ya definidos en el equipo y los aplica en memoria. El retorno al kernel habitual se realiza reiniciando y dejando continuar su arranque por defecto. [Formato de arranque U-Boot](https://docs.u-boot.org/en/latest/usage/cmd/bootm.html)

## Verificación en el WD

Comprobar por consola y por red que `uname -r` devuelve la identificación esperada, que la raíz procede del USB correcto y que ambos discos se reconocen. Verificar el RAID, la red y las VLAN, el filtrado de administración, los servicios OMV, el regulador térmico, los reinicios y el apagado. Conservar el registro serie.

```sh
uname -r
findmnt /
cat /proc/mdstat
ip -brief address
systemctl --failed --no-pager
/usr/local/sbin/wdnas-hw-control status
```

La compilación y la inspección del paquete son comprobaciones distintas de su arranque en el hardware. Registrar ambos resultados antes de promover el kernel a arranque habitual.

## Compilación verificada del 17 de noviembre de 2026

La [ejecución 44170910914 de Actions](https://github.com/i5Js/wdmcex2u-kernel/actions/runs/44170910914) terminó correctamente con GCC 13.3.0. El constructor utilizó la revisión `c74c9bf9eecfee0e943c37f1023192e578a9fae0` del fork y el commit oficial `b869a5313cbfe7102873d3de318ddb68675146d0` de Linux.

La inspección de los artefactos descargados confirmó las sumas SHA-256, las CRC de la imagen U-Boot, arquitectura ARM, carga y entrada `0x00008000`, DTB concatenado para EX2 Ultra con 1 GiB y ambas UART habilitadas. El árbol contiene 272 módulos ARM dentro de su identificación propia. La imagen U-Boot ocupa 4.965.314 bytes.

| Paquete | SHA-256 |
| --- | --- |
| `boot-6.12.118-wdex2u.tar.gz` | `c443bcdfcd9ab461af65e5e73e5660562c0b54b21dda5a44fd1c26ff39537c14` |
| `modules-6.12.118-wdex2u.tar.gz` | `967a133a80747343c389ee2915d9b01fc1fe0380a0e3515ffa651376296aa044` |

También pasaron las trece pruebas del controlador de hardware y comprobaciones del punto de entrada con herramientas simuladas para los paquetes versionados 6.12, los nombres habituales de kernels anteriores, la propagación de errores de `make`, la conservación de paquetes anteriores y el rechazo de referencias de ruta inválidas.

El log conserva avisos de migración de `BASE_SMALL` de la semilla 6.1 y del formato histórico de nombres de particiones NAND en el DTS. La configuración final normalizada superó las comprobaciones de controladores integrados. El primer arranque y las pruebas funcionales de este kernel en el WD quedan pendientes.
