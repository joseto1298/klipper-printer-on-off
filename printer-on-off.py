import os
import logging
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv
from quart import Quart, jsonify

from plugp100.common.credentials import AuthCredential
from plugp100.new.device_factory import connect, DeviceConnectConfiguration

# --- CONFIGURACIÓN DE LOGS (3 DÍAS) ---
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

async def get_device():
    """Crea la conexión y retorna el dispositivo y su cliente para poder cerrarlo después"""
    try:
        credentials = AuthCredential(USER, PASS)
        config = DeviceConnectConfiguration(host=IP, credentials=credentials)
        device = await connect(config)
        await device.update()
        return device
    except Exception as e:
        logging.error(f"❌ Error conectando: {e}")
        return None

@app.route('/on')
async def turn_on():
    device = await get_device()
    if device:
        await device.turn_on()
        logging.info("✅ Impresora Encendida")
        # Cerramos la sesión manualmente para evitar el error de "Unclosed session"
        await device.client.close()
        return jsonify({"status": True})
    return jsonify({"status": "error"}), 500

@app.route('/off')
async def turn_off():
    device = await get_device()
    if device:
        await device.turn_off()
        logging.info("✅ Impresora Apagada")
        await device.client.close()
        return jsonify({"status": False})
    return jsonify({"status": "error"}), 500

@app.route('/status')
async def status():
    device = await get_device()
    if not device:
        return jsonify({"status": "error"}), 500
    
    try:
        is_on = device.is_on
        await device.client.close()
        return jsonify({"status": is_on})
    except Exception as e:
        logging.error(f"❌ Error de estado: {e}")
        return jsonify({"status": "error"}), 500

if __name__ == '__main__':
    app.run(host="127.0.0.1", port=56427)