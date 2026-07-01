import os
import logging
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv
from quart import Quart, jsonify

from tapo import ApiClient

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
IP = os.getenv("TAPO_ADDRESS_P115")

app = Quart(__name__)

_client = None
_device = None

async def get_device():
    global _client, _device
    try:
        if _client is None:
            _client = ApiClient(USER, PASS)
        if _device is None:
            _device = await _client.p115(IP)
        return _device
    except Exception as e:
        logging.error(f"Error conectando: {e}")
        return None

@app.route('/on')
async def turn_on():
    device = await get_device()
    if device:
        await device.on()
        logging.info("Impresora Encendida")
        return jsonify({"status": True})
    return jsonify({"status": "error"}), 500

@app.route('/off')
async def turn_off():
    device = await get_device()
    if device:
        await device.off()
        logging.info("Impresora Apagada")
        return jsonify({"status": False})
    return jsonify({"status": "error"}), 500

@app.route('/status')
async def status():
    device = await get_device()
    if not device:
        return jsonify({"status": "error"}), 500
    try:
        device_info = await device.get_device_info()
        is_on = device_info.to_dict().get("device_on", False)
        return jsonify({"status": is_on})
    except Exception as e:
        logging.error(f"Error de estado: {e}")
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    app.run(host="127.0.0.1", port=56427)
