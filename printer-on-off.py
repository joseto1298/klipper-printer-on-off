import json
import requests
import time
import logging
import os
import threading
import socket
from dotenv import load_dotenv
from http.server import SimpleHTTPRequestHandler, HTTPServer
from PyP100 import PyP110

# Configuración de logs
LOG_FILE = "/home/pi/tapo/printer_on_off_log.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)

# Cargar variables de entorno
load_dotenv()
TAPO_ADDRESS = os.getenv("TAPO_ADDRESS_P115")
TAPO_USERNAME = os.getenv("TAPO_USERNAME")
TAPO_PASSWORD = os.getenv("TAPO_PASSWORD")

if not all([TAPO_ADDRESS, TAPO_USERNAME, TAPO_PASSWORD]):
    logging.error("Faltan credenciales de TAPO P115 en el archivo .env")
    raise ValueError("Faltan credenciales de TAPO P115 en el archivo .env")

CHECK_INTERVAL = 10  # Intervalo de comprobación en segundos
TOOL_COOL_THRESHOLD = 45  # Temperatura máxima para permitir apagado
RETRY_INTERVAL = 30  # Intervalo de reintento en segundos
MAX_RETRIES = 5  # Máximo de reintentos de conexión

# Parámetros para la conexión a Klipper con reintentos
KLIPPER_API_URL = "http://localhost:7125/api/printer"
MAX_API_RETRIES = 5  # Máximo de intentos antes de fallar
RETRY_BACKOFF = 2  # Factor de espera (exponencial)

class TapoPlug:
    """Clase para manejar el enchufe TAPO P115."""
    def __init__(self, address, username, password):
        self.address = address
        self.username = username
        self.password = password
        self.plug = None
        self.initialize()

    def initialize(self):
        """Inicializa la conexión con el enchufe TAPO, con reintentos en caso de fallo."""
        retries = 0
        while retries < MAX_RETRIES:
            try:
                self.plug = PyP110.P110(self.address, self.username, self.password)
                self.plug.handshake()
                self.plug.login()
                logging.info("Conexión con TAPO P115 exitosa.")
                return
            except Exception as e:
                retries += 1
                logging.warning(f"Error al conectar con TAPO P115: {e}. Reintentando ({retries}/{MAX_RETRIES})...")
                time.sleep(RETRY_INTERVAL)
        logging.error("No se pudo conectar con TAPO P115 después de varios intentos.")
        self.plug = None

    def reconnect(self):
        """Reintenta la conexión con TAPO P115."""
        logging.info("Intentando reconectar con TAPO P115...")
        self.initialize()

    def ensure_connection(func):
        """Decorador para garantizar que la conexión con TAPO P115 esté activa."""
        def wrapper(self, *args, **kwargs):
            if not self.plug:
                self.reconnect()
            try:
                return func(self, *args, **kwargs)
            except Exception as e:
                logging.error(f"Error en la operación con TAPO P115: {e}. Reintentando...")
                self.reconnect()
                return func(self, *args, **kwargs)
        return wrapper

    @ensure_connection
    def turn_off(self):
        """Apaga el enchufe TAPO P115."""
        if self.plug:
            self.plug.turnOff()
            logging.info("Impresora apagada.")

    @ensure_connection
    def turn_on(self):
        """Enciende el enchufe TAPO P115."""
        if self.plug:
            self.plug.turnOn()
            logging.info("Impresora encendida.")

    @ensure_connection
    def get_status(self):
        """Obtiene el estado del enchufe TAPO P115."""
        if self.plug:
            try:
                device_info = self.plug.getDeviceInfo()
                return {"status": device_info.get("device_on", "error")}
            except Exception as e:
                logging.error(f"Error al obtener el estado de TAPO P115: {e}")
        return {"status": "error"}

# Función para verificar conexión a la red WiFi
def wait_for_network():
    while True:
        try:
            # Intentar conectarse a una dirección pública
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            logging.info("Conectado a la red WiFi.")
            return
        except OSError:
            logging.warning("Esperando conexión a la red WiFi...")
            time.sleep(5)

# Esperar hasta que el dispositivo esté conectado a la red WiFi
wait_for_network()

# Inicializar TAPO P115
tapo_plug = TapoPlug(TAPO_ADDRESS, TAPO_USERNAME, TAPO_PASSWORD)

def request_klipper_data():
    """Realiza una solicitud a la API de Klipper con reintentos."""
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

def is_printer_busy():
    """Verifica si la impresora está ocupada."""
    data = request_klipper_data()
    if data:
        flags = data.get("state", {}).get("flags", {})
        return any(flags.get(state, False) for state in ["printing", "paused", "cancelling"])
    return False

def is_tool_cool():
    """Verifica si la herramienta está lo suficientemente fría para apagarse."""
    data = request_klipper_data()
    if data:
        tool_temp = data.get("temperature", {}).get("tool0", {}).get("actual", 40)
        return tool_temp < TOOL_COOL_THRESHOLD
    return False

def check_conditions_for_shutdown():
    """Comprueba si la impresora está lista para apagarse con doble verificación."""

    while True:
        if is_printer_busy():
            logging.info("La impresora esta ocupada. Cancelando apagado.")
            return  # Si la impresora se usa en cualquier momento, se cancela el apagado

        if not is_tool_cool():
            logging.info(f"La herramienta está caliente (> {TOOL_COOL_THRESHOLD}°C). Esperando a que se enfríe...")
            time.sleep(CHECK_INTERVAL)
            continue

        logging.info("Procediendo al apagado.")
        tapo_plug.turn_off()
        logging.info("La impresora se apagó exitosamente.")
        return

class MyHttpRequestHandler(SimpleHTTPRequestHandler):
    """Manejador HTTP para el control de la impresora."""
    
    def do_GET(self):
        if self.client_address[0] != '127.0.0.1':
            self.send_response(403)
            self.end_headers()
            self.wfile.write(json.dumps({"error": "Acceso denegado"}).encode("utf-8"))
            return
            
        try:
            if self.path == "/off":
                check_conditions_for_shutdown()

            elif self.path == "/off_now":
                tapo_plug.turn_off()

            elif self.path == "/on":
                tapo_plug.turn_on()

            elif self.path == "/status":
                response_data = tapo_plug.get_status()

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(response_data).encode("utf-8"))

        except BrokenPipeError:
            logging.warning("El cliente cerró la conexión antes de recibir la respuesta.")

        except Exception as e:
            logging.error(f"Error en la API HTTP: {e}")

if __name__ == '__main__':
    server_address = ('127.0.0.1', 56427)
    httpd = HTTPServer(server_address, MyHttpRequestHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Servidor detenido por el usuario.")
