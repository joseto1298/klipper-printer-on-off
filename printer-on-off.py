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

_device = None

def _init_sync():
    global _device
    try:
        dm = TPLinkDeviceManager(USER, PASS)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            devices = loop.run_until_complete(dm.get_devices())
            for d in devices:
                if "P115" in (d.device_info.device_model or "").upper():
                    _device = d
                    break
        finally:
            loop.close()
        if _device is None:
            logging.error("No se encontró dispositivo P115")
        else:
            logging.info(f"Conectado a {_device.get_alias()}")
    except Exception as e:
        logging.error(f"Error inicializando: {e}")

logging.info("Inicializando conexión a TAPO P115...")
_init_sync()

@app.route('/on')
async def turn_on():
    if not _device:
        return jsonify({"status": "error"}), 500
    try:
        await _device.power_on()
        logging.info("Impresora Encendida")
        return jsonify({"status": True})
    except Exception as e:
        logging.error(f"Error al encender: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/off')
async def turn_off():
    if not _device:
        return jsonify({"status": "error"}), 500
    try:
        await _device.power_off()
        logging.info("Impresora Apagada")
        return jsonify({"status": False})
    except Exception as e:
        logging.error(f"Error al apagar: {e}")
        return jsonify({"status": "error"}), 500

@app.route('/status')
async def status():
    if not _device:
        return jsonify({"status": "error"}), 500
    try:
        sys_info = await _device.get_sys_info()
        if sys_info is None:
            return jsonify({"status": "error"}), 500
        info = sys_info.__dict__ if hasattr(sys_info, "__dict__") else sys_info
        if "relay_state" in info:
            is_on = info["relay_state"] == 1
        elif "device_on" in info:
            is_on = info["device_on"] is True
        else:
            is_on = await _device.is_on()
        return jsonify({"status": bool(is_on)})
    except Exception as e:
        logging.error(f"Error de estado: {e}")
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    app.run(host="127.0.0.1", port=56427)
