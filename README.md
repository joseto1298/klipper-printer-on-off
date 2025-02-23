# Control de Encendido y Apagado de la Impresora 3D con TAPO P115

Este proyecto permite encender y apagar automáticamente una impresora 3D conectada a un enchufe inteligente **TP-Link TAPO P115**, utilizando **Klipper**, **Moonraker** y un servidor HTTP en Python.

## Características
✅ Encendido y apagado remoto de la impresora.  
✅ Integración con Moonraker para control automático.  
✅ Protección contra apagados durante la impresión.  
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
### 1️⃣ Instalar dependencias
```bash
sudo apt update && sudo apt install python3-pip python3-venv
python3 -m venv /home/pi/tapo-env
source /home/pi/tapo-env/bin/activate
pip install requests dotenv PyP100
```

### 2️⃣ Configurar credenciales de TAPO
Crear un archivo `.env` en `/home/pi/tapo/` con:
```ini
TAPO_ADDRESS_P115=192.168.X.X
TAPO_USERNAME=tu_usuario
TAPO_PASSWORD=tu_contraseña
```

### 3️⃣ Configurar el servicio systemd
Crear `/etc/systemd/system/printer-on-off.service`:
```ini
[Unit]
Description=Control de encendido y apagado de la impresora 3D con TAPO P115
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=/home/pi/tapo-env/bin/python3 /home/pi/tapo/printer-on-off.py
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

Habilitar y arrancar el servicio:
```bash
sudo systemctl daemon-reload
sudo systemctl enable printer-on-off
sudo systemctl start printer-on-off
```

### 4️⃣ Configurar Moonraker
Editar `moonraker.conf` para agregar:
```ini
[power printer]
type: http
on_url: http://localhost:56427/on
off_url: http://localhost:56427/off
status_url: http://localhost:56427/status
response_template:
  {% set resp = http_request.last_response().json() if http_request.last_response().is_json else {} %}
  {% if resp.get("status") == true %}
    {"on"}
  {% elif resp.get("status") == false  %}
    {"off"}
  {% else %}
    {"unknown"}
  {% endif %}
off_when_shutdown: True
locked_while_printing: True
restart_klipper_when_powered: True
on_when_job_queued: True
```
Reiniciar Moonraker:
```bash
sudo systemctl restart moonraker
```

---

## 🔥 Uso
- Encender la impresora: `M80` en Klipper.
- Apagar la impresora: `M81` en Klipper.
- Control manual:
  - **Encender**: `curl http://localhost:56427/on`
  - **Apagar**: `curl http://localhost:56427/off`
  - **Estado**: `curl http://localhost:56427/status`

---

## 🛠️ Solución de Problemas
🔹 **El enchufe TAPO no responde**
- Verifica que la Raspberry Pi esté conectada a la red.
- Revisa que la IP en `.env` sea correcta.
- Reinicia el servicio:
  ```bash
  sudo systemctl restart printer-on-off
  ```

🔹 **Moonraker no enciende la impresora automáticamente**
- Asegúrate de haber agregado la configuración en `moonraker.conf`.
- Verifica los logs con:
  ```bash
  tail -f /var/log/moonraker.log
  ```

🔹 **Klipper no reconoce M80/M81**
- Agregar en `printer.cfg`:
  ```ini
  [gcode_macro M80]
  gcode:
    {action_call_remote_method('set_device_power', device='printer', state='on')}
  
  [gcode_macro M81]
  gcode:
    {action_call_remote_method('set_device_power', device='printer', state='off')}
  ```

---

## 📜 Licencia
Proyecto bajo licencia MIT.

---

🚀 **¡Listo! Ahora puedes controlar tu impresora automáticamente con TAPO P115 y Moonraker.**

