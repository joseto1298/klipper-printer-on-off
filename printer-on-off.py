import os
import logging
import asyncio
import aiohttp
from dotenv import load_dotenv
from tapo import ApiClient
from quart import Quart, jsonify, request
from logging.handlers import TimedRotatingFileHandler

# Configuración de logs
LOG_FILE = "/home/pi/klipper-printer-on-off/printer_on_off.log"

# Configuración de logs
LOG_FILE = "/home/pi/klipper-printer-on-off/printer_on_off.log"
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
API_URL_STATUS = "http://localhost:7125/api/printer"
API_URL_GCODE = "http://localhost:7125/printer/gcode/script"
NOZZLE_COOLDOWN_TEMP = 50  # Temperatura objetivo para apagar (en °C)

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

async def send_klipper_command(command):
    try:
        async with session.post(API_URL_GCODE, json={"script": command}) as response:
            if response.status == 200:
                logging.info(f"✅ Comando enviado a Klipper: {command}")
            else:
                logging.error(f"❌ Error al enviar comando a Klipper: {response.status}")
    except Exception as e:
        logging.error(f"❌ Error en la comunicación con Moonraker: {e}")

async def get_device(max_retries=10, delay=5):
    """Intenta conectar con el TAPO P115 varias veces antes de fallar (versión asíncrona)."""
    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"🔄 Intento {attempt} de {max_retries} para conectar con TAPO P115...")
            device = await client.p110(TAPO_ADDRESS)
            logging.info("✅ Conexión exitosa con TAPO P115.")
            return device
        except Exception as e:
            logging.error(f"❌ Error al conectar con TAPO P115 (Intento {attempt}): {e}")
            if attempt < max_retries:
                sleep_time = delay * 2 ** (attempt - 1)
                logging.info(f"⏳ Reintentando en {sleep_time} segundos...")
                await asyncio.sleep(sleep_time)
            else:
                logging.error("🚨 Se agotaron los intentos para conectar con TAPO P115.")
                return None

async def get_printer_status(retries=5):
    """Consulta el estado de la impresora en OctoPrint con reintentos en caso de error."""
    await asyncio.sleep(15)
    for attempt in range(retries):
        try:
            async with session.get(API_URL_STATUS, timeout=5) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["state"]["flags"]["printing"], data["temperature"]["tool0"]["actual"]

                logging.error(f"⚠️ Error en la respuesta de OctoPrint (Código {response.status})")
        except Exception as e:
            logging.error(f"❌ Error al obtener el estado de la impresora (Intento {attempt+1}): {e}")
            await asyncio.sleep(2)

    logging.error("❌ No se pudo obtener el estado de la impresora después de varios intentos.")
    return None, None

async def wait_for_cooldown():
    """Espera a que la boquilla (nozzle) se enfríe antes de apagar la impresora."""
    while True:
        printing, nozzle_temp = await get_printer_status()
        
        if printing:
            logging.info("⏳ La impresora ha comenzado otra impresión. Cancelando apagado.")
            return {"printing": True}

        if nozzle_temp is None:
            logging.error("❌ No se pudo obtener la temperatura del nozzle.")
            return {"nozzle_temp": None}

        if nozzle_temp <= NOZZLE_COOLDOWN_TEMP:
            logging.info(f"✅ Nozzle frío ({nozzle_temp}°C). Procediendo con el apagado.")
            return {"can_turn_off": True}

        logging.info(f"⏳ Esperando enfriamiento... Nozzle: {nozzle_temp}°C")
        await asyncio.sleep(30)

async def turn_off_if_possible():
    """Apaga el enchufe solo si la impresora ha terminado y se ha enfriado."""
    device = await get_device()
    if not device:
        logging.error("❌ No se pudo conectar al TAPO P115 para apagarlo.")
        return jsonify({"status": "error", "message": "No se pudo conectar al dispositivo TAPO"}), 500
    
    can_turn_off = await wait_for_cooldown()

    if can_turn_off.get("can_turn_off"):
        await device.off()
        await asyncio.sleep(5)
        await send_klipper_command("FIRMWARE_RESTART")
        logging.info("✅ Impresora apagada correctamente.")
        return jsonify({"status": False})

    elif can_turn_off.get("printing"):
        logging.info("🚫 Apagado cancelado porque la impresora comenzó otra impresión.")
        return jsonify({"status": True})

    elif can_turn_off.get("nozzle_temp") is None:
        await device.off()
        await asyncio.sleep(5)
        await send_klipper_command("FIRMWARE_RESTART")
        logging.error("❌ Apagado forzado, No se pudo determinar la temperatura del nozzle")
        return jsonify({"status": False})


@app.route('/on', methods=['GET'])
async def turn_on():
    """Enciende el TAPO P115 manualmente."""
    device = await get_device()
    if not device:
        return jsonify({"status": "error", "message": "No se pudo conectar al dispositivo TAPO"}), 500
    
    await device.on()
    logging.info("✅ Dispositivo TAPO encendido.")
    return jsonify({"status": True})

@app.route('/off', methods=['GET'])
async def turn_off():
    """Apaga el TAPO P115 solo si la impresora ha terminado y está fría."""
    asyncio.create_task(turn_off_if_possible())  # Ejecutar en segundo plano
    return jsonify({"status": "processing"})

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
