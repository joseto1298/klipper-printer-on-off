import os
import logging
import asyncio
import aiohttp
from dotenv import load_dotenv
from tapo import ApiClient
from quart import Quart, jsonify, request

# Configuración de logs
LOG_FILE = "/home/pi/klipper-printer-on-off/printer_on_off.log"

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
OCTOPRINT_API_URL = "http://localhost:7125/api/printer"
NOZZLE_COOLDOWN_TEMP = 50  # Temperatura objetivo para apagar (en °C)

if not all([TAPO_ADDRESS, TAPO_USERNAME, TAPO_PASSWORD]):
    logging.error("❌ Faltan credenciales de TAPO P115 en el archivo .env")
    raise ValueError("Faltan credenciales de TAPO P115 en el archivo .env")

# Inicialización de Quart y TAPO
app = Quart(__name__)
client = ApiClient(TAPO_USERNAME, TAPO_PASSWORD)

async def get_device(max_retries=10, delay=5):
    """Intenta conectar con el TAPO P115 varias veces antes de fallar (versión asíncrona)."""
    for attempt in range(1, max_retries + 1):
        try:
            logging.info(f"🔄 Intento {attempt} de {max_retries} para conectar con TAPO P115...")
            device = await client.p110(TAPO_ADDRESS)  # 🔹 Usar `await` aquí
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
                return None  # Retornar None en caso de fallo

async def get_printer_status(max_retries=10, delay=5):
    """Consulta el estado de la impresora en OctoPrint con reintentos en caso de error."""
    for attempt in range(1, max_retries + 1):
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(OCTOPRINT_API_URL) as response:
                    if response.status == 200:
                        data = await response.json()
                        printing = data["state"]["flags"]["printing"]
                        nozzle_temp = data["temperature"]["tool0"]["actual"]
                        return printing, nozzle_temp
                    
                    logging.error(f"⚠️ Error en la respuesta de OctoPrint (Código {response.status})")
            except Exception as e:
                logging.error(f"❌ Error al obtener el estado de la impresora (Intento {attempt}): {e}")

            if attempt < max_retries:
                sleep_time = delay * 2 ** (attempt - 1)
                logging.info(f"⏳ Reintentando en {sleep_time} segundos...")
                await asyncio.sleep(sleep_time)
            else:
                logging.error("🚨 Se agotaron los intentos para obtener el estado de la impresora.")
                return None, None

async def wait_for_cooldown():
    """Espera a que la boquilla (nozzle) se enfríe antes de apagar la impresora."""
    while True:
        printing, nozzle_temp = await get_printer_status()
        
        if printing:
            logging.info("⏳ La impresora ha comenzado otra impresión. Cancelando apagado.")
            return {"printing": True}  # Se cancela la orden de apagado

        if nozzle_temp is None:
            logging.error("❌ No se pudo obtener la temperatura del nozzle.")
            return {"nozzle_temp": None}  # No se puede determinar la temperatura

        if nozzle_temp <= NOZZLE_COOLDOWN_TEMP:
            logging.info(f"✅ Nozzle frío ({nozzle_temp}°C). Procediendo con el apagado.")
            return {"can_turn_off": True}  # Puede apagarse

        logging.info(f"⏳ Esperando enfriamiento... Nozzle: {nozzle_temp}°C")
        await asyncio.sleep(30)  # Esperar 30 segundos antes de volver a verificar

async def turn_off_if_possible():
    """Apaga el enchufe solo si la impresora ha terminado y se ha enfriado."""
    device = await get_device()
    if not device:
        logging.error("❌ No se pudo conectar al TAPO P115 para apagarlo.")
        return
    
    can_turn_off = await wait_for_cooldown()
    if can_turn_off.get("can_turn_off"):
        await device.off()  # 🔹 `await` para apagar
        logging.info("✅ Impresora apagada correctamente.")
    if can_turn_off.get("printing"):
        logging.info("🚫 Apagado cancelado porque la impresora comenzó otra impresión.")
    if can_turn_off.get("nozzle_temp") is None:
        logging.error("❌ No se pudo determinar la temperatura del nozzle. Apagado cancelado.")

@app.route('/on', methods=['GET'])
async def turn_on():
    """Enciende el TAPO P115 manualmente."""
    device = await get_device()
    if not device:
        return jsonify({"status": "error", "message": "No se pudo conectar al dispositivo TAPO"}), 500
    
    await device.on()  # 🔹 `await` para encender
    logging.info("✅ Dispositivo TAPO encendido.")
    return jsonify({"status": True})

@app.route('/off', methods=['GET'])
async def turn_off():
    """Apaga el TAPO P115 solo si la impresora ha terminado y está fría."""
    asyncio.create_task(turn_off_if_possible())  # Ejecutar en segundo plano
    return jsonify({"status": "pending", "message": "Esperando a que la impresora termine y se enfríe."})

@app.route('/status', methods=['GET'])
async def status():
    """Devuelve el estado actual del TAPO P115."""
    device = await get_device()  # 🔹 Se debe usar `await get_device()`
    
    if not device:
        return jsonify({"status": "error", "message": "No se pudo conectar al dispositivo TAPO"}), 500
    
    try:
        device_info = await device.get_device_info()  # 🔹 Ahora se puede usar `await`
        return jsonify({"status": device_info.device_on})
    except AttributeError as e:
        logging.error(f"❌ Error al obtener el estado del dispositivo: {e}")
        return jsonify({"status": "error", "message": "Error al obtener información del dispositivo"}), 500

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    app.run(debug=False, host="127.0.0.1", port=56427)
