# Control de Encendido y Apagado de la Impresora 3D con TAPO P115

Este proyecto permite encender y apagar automáticamente una impresora 3D conectada a un enchufe inteligente **TP-Link TAPO P115**, utilizando **Klipper**, **Moonraker** y un servidor HTTP en Python.

## Características

✅ Encendido y apagado remoto de la impresora.  
✅ Integración con Moonraker para control automático.  
✅ Verificación de temperatura antes de apagar la impresora.  
✅ Reintentos en caso de fallos de conexión.

---

## 📌 Requisitos

- Raspberry Pi con Klipper y Moonraker instalados.
- Enchufe TP-Link TAPO P115.
- Python 3 y `pip` instalados.
- Acceso a la API de Moonraker.

---

## 📦 Instalación

### 1️⃣ Descargar ficheros

```bash
cd ~ && git clone https://github.com/joseto1298/klipper-printer-on-off.git
```

### 2️⃣ Instalar dependencias

```bash
sudo apt update && sudo apt install python3-pip python3-venv
python3 -m venv /home/pi/klipper-printer-on-off/.venv
source /home/pi/klipper-printer-on-off/.venv/bin/activate
pip install -r requirements.txt
```

### 3️⃣ Configurar credenciales de TAPO

Copiar archivo `example.env` en `/home/pi/klipper-printer-on-off/.env` con:

```bash
cd /home/pi/klipper-printer-on-off
cp example.env .env
```

Modificar fichero con:

```bash
cd /home/pi/klipper-printer-on-off/
nano config.env
```

### 4️⃣ Configurar el servicio systemd

Copiar archivo `klipper-printer-on-off` en `/etc/systemd/system/klipper-printer-on-off.service` con:

```bash
cd /home/pi/klipper-printer-on-off
cp klipper-printer-on-off.service /etc/systemd/system/klipper-printer-on-off.service
```

Habilitar y arrancar el servicio:

```bash
sudo systemctl daemon-reload
sudo systemctl enable klipper-printer-on-off
sudo systemctl start klipper-printer-on-off
```

### 5️⃣ Configurar Moonraker

Añadir el contenido de `moonraker-example.cfg` a `moonraker.cfg`:

Añadir el contenido de `macro-example.cfg` a `printer.cfg`:

- Encender la impresora: `M80` en Klipper.
- Apagar la impresora: `M81` en Klipper.

## 📜 Licencia

Proyecto bajo licencia MIT.

---

🚀 **¡Listo! Ahora puedes controlar tu impresora automáticamente con TAPO P115 y Moonraker.**
