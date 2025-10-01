import os
import logging
import asyncio
import aiohttp
from dotenv import load_dotenv
from tapo import ApiClient
from quart import Quart, jsonify
from logging.handlers import TimedRotatingFileHandler

# Configuración de logs
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "printer_on_off.log")

log_handler = TimedRotatingFileHandler(LOG_FILE, when="midnight", interval=1, backupCount=3, encoding="utf-8")
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
log_handler.suffix = "%Y-%m-%d"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()]
)

# Cargar variables de entorno
load_dotenv()
TAPO_USERNAME = os.getenv("TAPO_USERNAME")
TAPO_PASSWORD = os.getenv("TAPO_PASSWORD")
TAPO_ADDRESS = os.getenv("TAPO_ADDRESS_P115")

if not all([TAPO_ADDRESS, TAPO_USERNAME, TAPO_PASSWORD]):
    logging.error("❌ Faltan credenciales de TAPO P115 en el archivo .env")
    raise ValueError("Faltan credenciales de TAPO P115 en el archivo .env")

# Inicialización de Quart y TAPO
app = Quart(__name__)
client = ApiClient(TAPO_USERNAME, TAPO_PASSWORD)

# Sesión global para HTTP
session = None

@app.before_serving
async def create_session():
    global session
    session = aiohttp.ClientSession()

@app.after_serving
async def close_session():
    global session
    await session.close()

async def get_device(max_retries=3, delay=3):
    for attempt in range(1, max_retries + 1):
        try:
            device = await client.p110(TAPO_ADDRESS)
            return device
        except Exception as e:
            logging.error(f"❌ Error TAPO intento {attempt}: {e}")
            if attempt < max_retries:
                await asyncio.sleep(delay)
    return None

@app.route('/on', methods=['GET'])
async def turn_on():
    """Enciende el TAPO P115"""
    device = await get_device()
    if not device:
        return jsonify({"status": "error", "message": "No se pudo conectar al dispositivo TAPO"}), 500
    
    await device.on()
    logging.info("✅ Dispositivo TAPO encendido.")
    return jsonify({"status": True})

@app.route('/off', methods=['GET'])
async def turn_off():
    """Apaga el TAPO P115 solo si la impresora ha terminado y está fría."""
    device = await get_device()
    await device.off()
    logging.info("✅ Impresora apagada.")
    return jsonify({"status": False})

@app.route('/status', methods=['GET'])
async def status():
    """Devuelve el estado actual del TAPO P115."""
    device = await get_device()
    if not device:
        return jsonify({"status": "error", "message": "No se pudo conectar al dispositivo TAPO"}), 500
    
    try:
        device_info = await device.get_device_info()
        return jsonify({"status": device_info.device_on})
    except AttributeError as e:
        logging.error(f"❌ Error al obtener el estado del dispositivo: {e}")
        return jsonify({"status": "error", "message": "Error al obtener información del dispositivo"}), 500

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    app.run(debug=False, host="127.0.0.1", port=56427)
