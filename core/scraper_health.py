import logging
import threading
import time

logger = logging.getLogger(__name__)

MAX_FAILURES = 3
COOLDOWN_SECONDS = 300  # 5 min

_health: dict[str, dict] = {}
_lock = threading.Lock()


def _ensure(name: str):
    if name not in _health:
        _health[name] = {
            'consecutive_failures': 0,
            'last_error': None,
            'last_error_time': None,
            'temporarily_disabled': False,
            'disabled_until': None,
        }


def record_failure(name: str, error_msg: str) -> bool:
    with _lock:
        _ensure(name)
        state = _health[name]
        state['consecutive_failures'] += 1
        state['last_error'] = error_msg
        state['last_error_time'] = time.time()
        if state['consecutive_failures'] >= MAX_FAILURES and not state['temporarily_disabled']:
            state['temporarily_disabled'] = True
            state['disabled_until'] = time.time() + COOLDOWN_SECONDS
            logger.warning(
                f"Scraper '{name}' desactivado temporalmente tras "
                f"{state['consecutive_failures']} fallos consecutivos: {error_msg}"
            )
            return True
        logger.info(f"Scraper '{name}' fallo #{state['consecutive_failures']}: {error_msg}")
        return False


def record_success(name: str):
    with _lock:
        _ensure(name)
        state = _health[name]
        if state['consecutive_failures'] > 0 or state['temporarily_disabled']:
            logger.info(f"Scraper '{name}' recuperado tras {state['consecutive_failures']} fallos")
        state['consecutive_failures'] = 0
        state['last_error'] = None
        state['last_error_time'] = None
        state['temporarily_disabled'] = False
        state['disabled_until'] = None


def is_available(name: str) -> bool:
    with _lock:
        _ensure(name)
        state = _health[name]
        if not state['temporarily_disabled']:
            return True
        if state['disabled_until'] and time.time() >= state['disabled_until']:
            state['temporarily_disabled'] = False
            state['disabled_until'] = None
            state['consecutive_failures'] = 0
            logger.info(f"Scraper '{name}' re-activado automaticamente tras cooldown")
            return True
        return False


def re_enable(name: str):
    with _lock:
        _ensure(name)
        state = _health[name]
        was_disabled = state['temporarily_disabled']
        state['consecutive_failures'] = 0
        state['last_error'] = None
        state['last_error_time'] = None
        state['temporarily_disabled'] = False
        state['disabled_until'] = None
        if was_disabled:
            logger.info(f"Scraper '{name}' re-activado manualmente")


def get_status(name: str) -> dict:
    with _lock:
        _ensure(name)
        state = _health[name].copy()
        if state['temporarily_disabled'] and state['disabled_until']:
            remaining = max(0, state['disabled_until'] - time.time())
            state['remaining_seconds'] = int(remaining)
            if remaining <= 0:
                state['temporarily_disabled'] = False
                state['disabled_until'] = None
                state['consecutive_failures'] = 0
        else:
            state['remaining_seconds'] = 0
        return state


def get_all_status() -> dict[str, dict]:
    result = {}
    for name in list(_health.keys()):
        result[name] = get_status(name)
    return result


def init_health_for_source(name: str):
    with _lock:
        _ensure(name)
