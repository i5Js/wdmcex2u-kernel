# Control de hardware del WD EX2 Ultra

Controlador local para Debian 12 ARMv7 y systemd. Utiliza Python 3, `smartctl` y el microcontrolador Weltrend conectado a `/dev/ttyS1` a 19200 baudios. El protocolo procede del trabajo de [mcm-daemon](https://github.com/c-MM/mcm-daemon/blob/master/mcm.h).

## Funcionamiento

En el inicio solicita ventilación máxima, envía `DeviceReady` y selecciona azul fijo para el piloto de encendido. Comprueba el tacómetro antes de pasar a la curva térmica.

| Nivel | PWM | SoC a partir de | Disco más caliente a partir de |
| --- | --- | --- | --- |
| Mínimo | 96, aproximadamente 38 % | Temperaturas inferiores al siguiente nivel | Temperaturas inferiores al siguiente nivel |
| Medio | 128, aproximadamente 50 % | 60 °C | 40 °C |
| Alto | 192, aproximadamente 75 % | 70 °C | 45 °C |
| Máximo | 255, 100 % | 80 °C | 50 °C |

Se aplica el nivel mayor que demande cualquiera de los sensores. La reducción exige un margen de 3 °C en el SoC y 2 °C en los discos, y baja un nivel por ciclo. El SoC y el tacómetro se consultan aproximadamente cada diez segundos. Los dos discos SATA internos se identifican por su ruta de hardware y se consultan cada minuto con `smartctl -n standby`.

La lectura de un disco dormido se registra como `null`. Un fallo de sensor activo, la ausencia de alguno de los dos discos o un tacómetro a cero provoca una orden de PWM máximo. El servicio vuelve a comprobar el tacómetro al máximo antes de reanudar la curva. Al detener el servicio se solicita también el máximo, mediante el cierre del proceso y `ExecStopPost`.

El controlador mantiene un bloqueo exclusivo cooperativo de la UART durante su ejecución. Las consultas de estado utilizan el archivo de telemetría en RAM. Las respuestas de la MCU se comprueban mediante trama, comando y confirmación, con tiempos de espera acotados.

## Pruebas

Desde la raíz del repositorio.

```sh
python3 -B -m unittest discover -s hardware -v
```

Las pruebas cubren umbrales, histéresis, discos dormidos, lecturas inválidas, confirmación del protocolo, fallo de sensores y ventilador detenido. La prueba de discos dormidos emplea una respuesta simulada de SMART.

## Rearme de Wake-on-LAN en OMV

`wdnas_wol_arm.py` consulta la opción `wol` de `eth0` en la base de configuración de OMV. Cuando está habilitada, programa de nuevo el PHY mediante la API ethtool del kernel. Conserva las demás opciones de despertar y comprueba la transición de `WAKE_MAGIC` de desactivado a activado.

Esta transición es necesaria porque las API ioctl y netlink omiten la escritura cuando las opciones solicitadas coinciden con las actuales. En el EX2 Ultra examinado, `Wake-on: g` coexistía con la máscara de interrupción del PHY a cero. La transición activó el bit WOL de la máscara, con valor `0x0080`, y el siguiente apagado y despertar desde el router completó un nuevo arranque. [API ioctl de Linux 6.12.118](https://github.com/gregkh/linux/blob/v6.12.118/net/ethtool/ioctl.c), [controlador Marvell](https://github.com/gregkh/linux/blob/v6.12.118/drivers/net/phy/marvell.c).

El servicio ejecuta el rearme después de configurar la red y antes de detenerla durante el apagado. Cada ejecución vuelve a consultar la opción de OMV. Las pruebas simulan la optimización de ethtool, la conservación de otras opciones y la recuperación ante un fallo al activar.

Preparar copias y un rollback con sumas antes de instalar.

```sh
install -m 755 hardware/wdnas_wol_arm.py /usr/local/sbin/wdnas-wol-arm
install -m 644 hardware/wdnas-wol-arm.service /etc/systemd/system/wdnas-wol-arm.service
systemd-analyze verify /etc/systemd/system/wdnas-wol-arm.service
systemctl daemon-reload
systemctl enable --now wdnas-wol-arm.service
systemctl status wdnas-wol-arm.service --no-pager
```

La reversión comprueba primero las sumas instaladas, detiene y deshabilita la unidad y retira exclusivamente esos dos archivos. Después recarga systemd. La opción WOL nativa de OMV tiene su propia recuperación.

## Instalación

Conservar un registro del estado previo, comprobar la ausencia de archivos anteriores y preparar el rollback antes de activar. Copiar estos dos archivos como root.

```sh
install -m 755 hardware/wdnas_hw_control.py /usr/local/sbin/wdnas-hw-control
install -m 644 hardware/wdnas-hw-control.service /etc/systemd/system/wdnas-hw-control.service
systemd-analyze verify /etc/systemd/system/wdnas-hw-control.service
systemctl daemon-reload
systemctl enable --now wdnas-hw-control.service
```

La activación se realiza en caliente. La unidad queda habilitada para futuros arranques.

```sh
/usr/local/sbin/wdnas-hw-control status
journalctl -u wdnas-hw-control.service --no-pager
```

El estado muestra la antigüedad de la muestra, temperaturas, PWM, RPM y errores. El comando de ventilador manual acepta valores de 64 a 255 para diagnóstico y recuperación, y exige que la UART esté libre.

## Reversión de esta instalación

El instalador operativo debe guardar `installed.sha256` con las sumas de los dos archivos instalados junto a `rollback.sh`. El script comprueba esas sumas antes de detener y deshabilitar la unidad. Después solicita ventilación máxima, restablece el piloto azul intermitente y mueve sus dos archivos a `retired/` dentro del directorio de recuperación.

La reversión conserva los archivos modificados por otras sesiones mediante la comprobación previa de sus sumas. El estado de recuperación deja ventilación máxima como medida térmica conservadora.

## Alcance de la verificación

Probado en un EX2 Ultra con Debian 12 y kernel 6.0.13 el 17 de noviembre de 2026. La MCU confirmó las órdenes del piloto y se midió la respuesta del tacómetro al cambiar PWM. La apariencia física del piloto requiere observación presencial. La persistencia se comprobó mediante la habilitación y el arranque del servicio.
