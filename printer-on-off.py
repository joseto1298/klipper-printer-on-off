import os
import sys
import time
import logging
from logging.handlers import TimedRotatingFileHandler
from dotenv import load_dotenv
from aiohttp import web
from tapo import ApiClient

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
TAPO_EMAIL = os.getenv("TAPO_EMAIL")
TAPO_PASSWORD = os.getenv("TAPO_PASSWORD")
TAPO_IP = os.getenv("TAPO_ADDRESS_P115")

if not all([TAPO_IP, TAPO_EMAIL, TAPO_PASSWORD]):
    logger.error(
        "Faltan variables de entorno obligatorias. "
        "Verifica TAPO_ADDRESS_P115, TAPO_EMAIL y TAPO_PASSWORD en el archivo .env"
    )
    sys.exit(1)
STATUS_CACHE_TTL = int(os.getenv("TAPO_P115_CACHE_TTL", "30"))

_device = None
_device_last_attempt = 0.0
_status_cache = {"value": None, "time": 0.0}
BACKOFF_SECONDS = 60


def _is_session_expired(e: Exception) -> bool:
    msg = str(e).lower()
    return "session" in msg and ("timeout" in msg or "expired" in msg or "unauthorized" in msg)


def _invalidate_device():
    global _device
    _device = None
    _device_last_attempt = 0.0


async def ensure_device():
    global _device, _device_last_attempt
    if _device is not None:
        return _device
    if time.time() - _device_last_attempt < BACKOFF_SECONDS:
        return None
    _device_last_attempt = time.time()
    try:
        client = ApiClient(TAPO_EMAIL, TAPO_PASSWORD)
        _device = await client.p115(TAPO_IP)
        logger.info(f"Conectado a Tapo P115 en {TAPO_IP}")
        try:
            info = await _device.get_device_info_json()
            global _status_cache
            is_on = bool(info.get("device_on", False))
            _status_cache = {"value": is_on, "time": time.time()}
        except Exception:
            pass
        return _device
    except Exception as e:
        logger.error(f"Error conectando P115 con tapo: {e}")
        _device = None
        return None


async def disconnect_device():
    global _device
    if _device is not None:
        try:
            await _device.refresh_session()
            logger.info("Sesión Tapo P115 cerrada")
        except Exception as e:
            logger.error(f"Error al desconectar: {e}")
        _device = None


async def handle_on(request):
    global _status_cache
    dev = await ensure_device()
    if not dev:
        return web.json_response({"status": "error"}, status=500)
    try:
        await dev.on()
        _status_cache = {"value": True, "time": time.time()}
        logger.info("Impresora encendida")
        return web.json_response({"status": True})
    except Exception as e:
        if _is_session_expired(e):
            _invalidate_device()
        logger.error(f"Error al encender: {e}")
        return web.json_response({"status": "error"}, status=500)


async def handle_off(request):
    global _status_cache
    dev = await ensure_device()
    if not dev:
        return web.json_response({"status": "error"}, status=500)
    try:
        await dev.off()
        _status_cache = {"value": False, "time": time.time()}
        logger.info("Impresora apagada")
        return web.json_response({"status": False})
    except Exception as e:
        if _is_session_expired(e):
            _invalidate_device()
        logger.error(f"Error al apagar: {e}")
        return web.json_response({"status": "error"}, status=500)


async def handle_status(request):
    global _status_cache
    dev = await ensure_device()
    if not dev:
        return web.json_response({"status": "error"}, status=500)
    if time.time() - _status_cache["time"] < STATUS_CACHE_TTL:
        return web.json_response({"status": _status_cache["value"]})
    try:
        info = await dev.get_device_info_json()
        is_on = bool(info.get("device_on", False))
        _status_cache = {"value": is_on, "time": time.time()}
        return web.json_response({"status": _status_cache["value"]})
    except Exception as e:
        if _is_session_expired(e):
            _invalidate_device()
        logger.error(f"Error de estado: {e}")
        return web.json_response({"status": "error"}, status=500)


async def handle_health(request):
    return web.json_response({"status": "ok"})


app = web.Application()
app.router.add_get("/on", handle_on)
app.router.add_get("/off", handle_off)
app.router.add_get("/status", handle_status)
app.router.add_get("/health", handle_health)


async def on_shutdown(app):
    await disconnect_device()


app.on_shutdown.append(on_shutdown)

if __name__ == "__main__":
    logger.info("Iniciando servidor en 127.0.0.1:56427")
    web.run_app(app, host="127.0.0.1", port=56427)
