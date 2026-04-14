from apps.worker.worker_settings import WorkerSettings
from apps.api.config import settings
from aura.utils.observability import init_otel, instrument_sqlalchemy

init_otel("aura-worker", settings.otlp_endpoint)
instrument_sqlalchemy()

__all__ = ["WorkerSettings"]
