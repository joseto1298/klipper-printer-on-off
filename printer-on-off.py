import os
import time
import logging
from dotenv import load_dotenv
import requests
from tapo import ApiClient
from quart import Quart, jsonify, request, abort
import asyncio

# Configuración de logs (ajustada para producción)
LOG_FILE = "/home/pi/klipper-printer-on-off/printer_on_off_log.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

# Cargar variables de entorno
load_dotenv()  # Especifica la ruta completa al archivo .env
TAPO_USERNAME = os.getenv("TAPO_USERNAME")
TAPO_PASSWORD = os.getenv("TAPO_PASSWORD")
TAPO_ADDRESS = os.getenv("TAPO_ADDRESS_P115")
KLIPPER_API_URL = "http://localhost:7125/api/printer"

if not all([TAPO_ADDRESS, TAPO_USERNAME, TAPO_PASSWORD]):
    logging.error("Faltan credenciales de TAPO P115 en el archivo .env")
    raise ValueError("Faltan credenciales de TAPO P115 en el archivo .env")

CHECK_INTERVAL = 10  # Intervalo de comprobación en segundos
TOOL_COOL_THRESHOLD = 45  # Temperatura máxima para permitir apagado
RETRY_INTERVAL = 30  # Intervalo de reintento en segundos
MAX_RETRIES = 5  # Máximo de reintentos de conexión
MAX_API_RETRIES = 5  # Máximo de intentos de conexión a Klipper
RETRY_BACKOFF = 2  # Factor de espera (exponencial)

# Inicialización de Quart y Tapo
app = Quart(__name__)

# Crear cliente Tapo con las credenciales del archivo .env
client = ApiClient(TAPO_USERNAME, TAPO_PASSWORD)

# Función para obtener el dispositivo Tapo
async def get_device():
    retries = 0
    while retries < MAX_RETRIES:
        try:
            device = await client.p110(TAPO_ADDRESS)  # Usando la dirección IP almacenada en .env
            return device
        except Exception as e:
            retries += 1
            wait_time = RETRY_BACKOFF ** retries
            logging.warning(f"Error al conectar con el dispositivo Tapo ({e}). Reintentando ({retries}/{MAX_RETRIES}) en {wait_time}s...")
            await asyncio.sleep(wait_time)

    logging.error("No se pudo conectar con el dispositivo Tapo después de varios intentos.")
    return None

# Función para realizar solicitudes a la API de Klipper con reintentos
def request_klipper_data():
    retries = 0
    while retries < MAX_API_RETRIES:
        try:
            response = requests.get(KLIPPER_API_URL, timeout=5)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            retries += 1
            wait_time = RETRY_BACKOFF ** retries
            logging.warning(f"Error en la API de Klipper ({e}). Reintentando ({retries}/{MAX_API_RETRIES}) en {wait_time}s...")
            time.sleep(wait_time)

    logging.error("No se pudo conectar con la API de Klipper después de varios intentos.")
    return None

# Verifica si la impresora está ocupada
def is_printer_busy():
    data = request_klipper_data()
    if data:
        flags = data.get("state", {}).get("flags", {})
        return any(flags.get(state, False) for state in ["printing", "paused", "cancelling"])
    return False

# Verifica si la herramienta está lo suficientemente fría para apagarse
def is_tool_cool():
    data = request_klipper_data()
    if data:
        tool_temp = data.get("temperature", {}).get("tool0", {}).get("actual", 40)
        return tool_temp < TOOL_COOL_THRESHOLD
    return False

# Comprueba si la impresora está lista para apagarse
def check_conditions_for_shutdown():
    while True:
        if is_printer_busy():
            logging.info("La impresora está ocupada. Cancelando apagado.")
            return False

        if not is_tool_cool():
            logging.info(f"La herramienta está caliente (> {TOOL_COOL_THRESHOLD}°C). Esperando a que se enfríe...")
            time.sleep(CHECK_INTERVAL)
            continue

        logging.info("Procediendo al apagado.")
        return True

# Función para verificar si la solicitud proviene de localhost
def check_localhost():
    if request.remote_addr != '127.0.0.1':
        logging.warning(f"Solicitud rechazada desde IP: {request.remote_addr}. Solo se permiten solicitudes desde localhost.")
        abort(403, "Acceso denegado. Solo se permite acceso desde localhost.")

@app.route('/on', methods=['GET'])
async def turn_on():
    check_localhost()  # Verifica que la solicitud provenga de localhost
    device = await get_device()  # Obtiene el dispositivo Tapo P110
    if not device:
        return jsonify({"status": "error", "message": "No se pudo conectar al dispositivo Tapo"}), 500
    
    await device.on()
    logging.info("Dispositivo encendido.")
    return jsonify({"status": True})

@app.route('/off', methods=['GET'])
async def turn_off():
    check_localhost()  # Verifica que la solicitud provenga de localhost
    if not check_conditions_for_shutdown():  # Verifica si las condiciones son adecuadas para apagado
        return jsonify({"status": "error", "message": "No se cumplen las condiciones para apagado."}), 400
    
    device = await get_device()  # Obtiene el dispositivo Tapo P110
    if not device:
        return jsonify({"status": "error", "message": "No se pudo conectar al dispositivo Tapo"}), 500
    
    await device.off()
    logging.info("Dispositivo apagado.")
    return jsonify({"status": False})

@app.route('/status', methods=['GET'])
async def status():
    check_localhost()  # Verifica que la solicitud provenga de localhost
    device = await get_device()  # Obtiene el dispositivo Tapo P110
    if not device:
        return jsonify({"status": "error", "message": "No se pudo conectar al dispositivo Tapo"}), 500
    
    try:
        device_info = await device.get_device_info()  # Supongamos que esta es la función que te da el estado del dispositivo
        device_on = device_info.device_on  # Acceder al atributo 'device_on' como propiedad del objeto
                
        return jsonify({"status": device_on})
    
    except AttributeError as e:
        logging.error(f"Error al acceder a los atributos del dispositivo: {e}")
        return jsonify({"status": "error", "message": "Error al obtener información del dispositivo"}), 500

if __name__ == '__main__':
    app.run(debug=False, host="0.0.0.0", port=56427)
