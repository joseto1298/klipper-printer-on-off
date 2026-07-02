import os
import asyncio
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

_device_manager = None
_device = None

async def get_device():
    global _device_manager, _device
    try:
        if _device_manager is None:
            _device_manager = await asyncio.to_thread(
                TPLinkDeviceManager, USER, PASS
            )
        if _device is None:
            devices = await _device_manager.get_devices()
            for d in devices:
                model = d.device_info.device_model or ""
                if "P115" in model.upper():
                    _device = d
                    break
        return _device
    except Exception as e:
        logging.error(f"Error conectando: {e}")
        return None

@app.route('/on')
async def turn_on():
    device = await get_device()
    if device:
        await device.power_on()
        logging.info("Impresora Encendida")
        return jsonify({"status": True})
    return jsonify({"status": "error"}), 500

@app.route('/off')
async def turn_off():
    device = await get_device()
    if device:
        await device.power_off()
        logging.info("Impresora Apagada")
        return jsonify({"status": False})
    return jsonify({"status": "error"}), 500

@app.route('/status')
async def status():
    device = await get_device()
    if not device:
        return jsonify({"status": "error"}), 500
    try:
        sys_info = await device.get_sys_info()
        if sys_info is None:
            return jsonify({"status": "error"}), 500
        info = sys_info.__dict__ if hasattr(sys_info, "__dict__") else sys_info
        if "relay_state" in info:
            is_on = info["relay_state"] == 1
        elif "device_on" in info:
            is_on = info["device_on"] is True
        else:
            is_on = await device.is_on()
        return jsonify({"status": bool(is_on)})
    except Exception as e:
        logging.error(f"Error de estado: {e}")
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    app.run(host="127.0.0.1", port=56427)
