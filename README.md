# Control de Encendido y Apagado de la Impresora 3D con TAPO P115

Este proyecto permite encender y apagar automáticamente una impresora 3D conectada a un enchufe inteligente **TP-Link TAPO P115**, utilizando **Klipper**, **Moonraker** y un servidor HTTP en Python.

Usa la librería [`python-kasa`](https://github.com/python-kasa/python-kasa) para control local del P115 (sin depender de la nube de TP-Link).

## Características

✅ Encendido y apagado remoto de la impresora (local, sin nube).  
✅ Integración con Moonraker (`[power] type: http`).  
✅ Verificación de temperatura antes de apagar la impresora.  
✅ Reintentos en caso de fallos de conexión.  
✅ Polling cada 15s para que Moonraker detecte cambios externos.

---

## Requisitos

- Raspberry Pi con Klipper y Moonraker instalados.
- Enchufe TP-Link TAPO P115 en la misma red.
- Python 3 y `pip` instalados.
- Cuenta TP-Link/Tapo (para autenticación inicial del dispositivo).
- **"Third-party compatibility" activado** en la app Tapo (Perfil > Third-Party Services).

---

## Instalación

### 1. Descargar ficheros

```bash
cd ~ && git clone https://github.com/joseto1298/klipper-printer-on-off.git
```

### 2. Instalar dependencias

```bash
sudo apt update && sudo apt install python3-pip python3-venv
python3 -m venv /home/pi/klipper-printer-on-off/.venv
source /home/pi/klipper-printer-on-off/.venv/bin/activate
pip install -r /home/pi/klipper-printer-on-off/requirements.txt
```

### 3. Configurar credenciales de TAPO

```bash
cd /home/pi/klipper-printer-on-off
cp example.env .env
nano .env
```

Completar con:
- `TAPO_ADDRESS_P115` — IP fija del enchufe en tu red.
- `TAPO_USERNAME` — Email de tu cuenta TP-Link/Tapo.
- `TAPO_PASSWORD` — Contraseña de tu cuenta TP-Link/Tapo.

> **Importante:** La IP del P115 debe ser estática. Asigna una reserva DHCP en tu router o usa la app Tapo.

### 4. Configurar el servicio systemd

```bash
cd /home/pi/klipper-printer-on-off
sudo cp klipper-printer-on-off.service /etc/systemd/system/klipper-printer-on-off.service
sudo systemctl daemon-reload
sudo systemctl enable klipper-printer-on-off
sudo systemctl start klipper-printer-on-off
```

Verificar que arrancó bien:

```bash
sudo journalctl -u klipper-printer-on-off -n 20 --no-pager
```

### 5. Configurar Moonraker

Añadir el contenido de `moonraker-example.cfg` a `moonraker.conf`:

```bash
cat ~/klipper-printer-on-off/moonraker-example.cfg >> ~/moonraker.conf
```

Añadir el contenido de `macro-example.cfg` a `printer.cfg`:

```bash
cat ~/klipper-printer-on-off/macro-example.cfg >> ~/printer.cfg
```

Luego reiniciar Moonraker y Klipper.

### 6. Uso

- Encender impresora: `M80` en Klipper.
- Apagar impresora: `M81` en Klipper.
- Apagado automático por inactividad (10 min) con espera de enfriamiento.

---

## Solución de problemas

| Problema | Causa probable | Solución |
|---|---|---|
| No conecta con el P115 | IP incorrecta o credenciales malas | Verificar `.env` y que el P115 tenga IP fija |
| "Third-party compatibility" error | Firmware >=1.4.0 desactivó la opción | App Tapo > Perfil > Third-Party Services > activar |
| Moonraker no cambia estado | `poll_interval` no configurado | Verificar `moonraker-example.cfg` |
| El servicio no arranca | Puerto 56427 ocupado | `sudo ss -tlnp \| grep 56427` |

---

## Licencia

Proyecto bajo licencia MIT.
