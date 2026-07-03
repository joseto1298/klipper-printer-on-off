import os
import time
import logging
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv
from aiohttp import web
from kasa import Device, DeviceConfig, Credentials

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "printer_on_off.log")

log_handler = TimedRotatingFileHandler(
    LOG_FILE, when="midnight", interval=1, backupCount=3, encoding="utf-8"
)
log_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))

logger = logging.getLogger()
logger.setLevel(logging.INFO)
logger.addHandler(log_handler)
logger.addHandler(logging.StreamHandler())

load_dotenv()
HOST = os.getenv("TAPO_ADDRESS_P115")
USER = os.getenv("TAPO_USERNAME")
PASS = os.getenv("TAPO_PASSWORD")
STATUS_CACHE_TTL = int(os.getenv("TAPO_P115_CACHE_TTL", "30"))

_device = None
_device_last_attempt = 0.0
_status_cache = {"value": None, "time": 0.0}
BACKOFF_SECONDS = 60


async def ensure_device():
    global _device, _device_last_attempt
    if _device is not None:
        return _device
    if time.time() - _device_last_attempt < BACKOFF_SECONDS:
        return None
    _device_last_attempt = time.time()
    try:
        config = DeviceConfig(host=HOST, credentials=Credentials(USER, PASS))
        _device = await Device.connect(config=config)
        await _device.update()
        logging.info(f"Conectado a {_device.alias} ({_device.model})")
        global _status_cache
        _status_cache = {"value": bool(_device.is_on), "time": time.time()}
        return _device
    except Exception as e:
        logging.error(f"Error conectando P115: {e}")
        _device = None
        return None


async def handle_on(request):
    dev = await ensure_device()
    if not dev:
        return web.json_response({"status": "error"}, status=500)
    try:
        await dev.turn_on()
        global _status_cache
        _status_cache = {"value": True, "time": time.time()}
        logging.info("Impresora encendida")
        return web.json_response({"status": True})
    except Exception as e:
        logging.error(f"Error al encender: {e}")
        return web.json_response({"status": "error"}, status=500)


async def handle_off(request):
    dev = await ensure_device()
    if not dev:
        return web.json_response({"status": "error"}, status=500)
    try:
        await dev.turn_off()
        global _status_cache
        _status_cache = {"value": False, "time": time.time()}
        logging.info("Impresora apagada")
        return web.json_response({"status": False})
    except Exception as e:
        logging.error(f"Error al apagar: {e}")
        return web.json_response({"status": "error"}, status=500)


async def handle_status(request):
    global _status_cache
    dev = await ensure_device()
    if not dev:
        return web.json_response({"status": "error"}, status=500)
    if time.time() - _status_cache["time"] < STATUS_CACHE_TTL:
        return web.json_response({"status": _status_cache["value"]})
    try:
        await dev.update()
        _status_cache = {"value": bool(dev.is_on), "time": time.time()}
        return web.json_response({"status": _status_cache["value"]})
    except Exception as e:
        logging.error(f"Error de estado: {e}")
        return web.json_response({"status": "error"}, status=500)


app = web.Application()
app.router.add_get("/on", handle_on)
app.router.add_get("/off", handle_off)
app.router.add_get("/status", handle_status)

if __name__ == "__main__":
    logging.info("Iniciando servidor en 127.0.0.1:56427")
    web.run_app(app, host="127.0.0.1", port=56427)
