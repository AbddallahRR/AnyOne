"""Progreso byte a byte de descargas activas.

Store en memoria clave `job_id` -> progreso del archivo que se está
descargando en este momento. Lo alimentan las fuentes mediante un callback
y lo lee `GET /api/queue/status`. No se persiste en BD para evitar churn
de escrituras (la BD ya se actualiza cada ~30 s).
"""

import threading

_lock = threading.Lock()
_progress: dict[int, dict] = {}


def report(job_id: int, done: int, total: int | None = None, label: str = '') -> None:
    """Registra el progreso actual de un job.

    Si `total` es None o 0 el progreso se marca como indeterminado
    (el frontend muestra una barra animada sin porcentaje).
    """
    with _lock:
        _progress[job_id] = {
            'done': done,
            'total': total,
            'percent': int(done / total * 100) if total else None,
            'indeterminate': not total,
            'label': label,
        }


def get(job_id: int) -> dict | None:
    with _lock:
        return _progress.get(job_id)


def clear(job_id: int) -> None:
    with _lock:
        _progress.pop(job_id, None)
