import os
import logging
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv
from quart import Quart, jsonify
from tplinkcloud import TPLinkDeviceManager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "printer_on_off.log")
log_handler = TimedRotatingFileHandler(LOG_FILE, when="midnight", interval=1, backupCount=3, encoding="utf-8")
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)
logger.addHandler(logging.StreamHandler())

load_dotenv()
USER = os.getenv("TAPO_USERNAME")
PASS = os.getenv("TAPO_PASSWORD")

app = Quart(__name__)

_device = None
_initialized = False

async def ensure_device():
    global _device, _initialized
    if _initialized:
        return _device
    try:
        dm = TPLinkDeviceManager(USER, PASS)
        logging.info("Obteniendo dispositivos de la nube Tapo...")
        devices = await dm.get_devices()
        for d in devices:
            model = d.device_info.device_model or ""
            if "P115" in model.upper():
                _device = d
                logging.info(f"Conectado a {d.get_alias()} ({model})")
                break
        if _device is None:
            logging.error("No se encontró dispositivo P115 en la nube")
    except Exception as e:
        logging.error(f"Error conectando a nube Tapo: {e}")
    _initialized = True
    return _device

@app.route('/on')
async def turn_on():
    device = await ensure_device()
    if not device:
        return jsonify({"status": "error"}), 500
    try:
        await device.power_on()
        logging.info("Impresora Encendida")
        return jsonify({"status": True})
    except Exception as e:
        logging.error(f"Error al encender: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/off')
async def turn_off():
    device = await ensure_device()
    if not device:
        return jsonify({"status": "error"}), 500
    try:
        await device.power_off()
        logging.info("Impresora Apagada")
        return jsonify({"status": False})
    except Exception as e:
        logging.error(f"Error al apagar: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/status')
async def status():
    device = await ensure_device()
    if not device:
        return jsonify({"status": "error"}), 500
    try:
        sys_info = await device.get_sys_info()
        if sys_info is not None:
            info = sys_info.__dict__ if hasattr(sys_info, "__dict__") else sys_info
            if "relay_state" in info:
                is_on = info["relay_state"] == 1
            elif "device_on" in info:
                is_on = info["device_on"] is True
            else:
                is_on = await device.is_on()
        else:
            is_on = await device.is_on()
        return jsonify({"status": bool(is_on)})
    except Exception as e:
        logging.error(f"Error de estado: {e}")
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    app.run(host="127.0.0.1", port=56427)
