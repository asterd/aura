from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from contextvars import ContextVar
import logging
from threading import Lock
from typing import Any

from aura.adapters.db.session import engine

metrics: Any = None
trace: Any = None
OTLPMetricExporter: Any = None
OTLPSpanExporter: Any = None
FastAPIInstrumentor: Any = None
SQLAlchemyInstrumentor: Any = None
MeterProvider: Any = None
PeriodicExportingMetricReader: Any = None
Resource: Any = None
TracerProvider: Any = None
BatchSpanProcessor: Any = None

try:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
except ImportError:  # pragma: no cover - optional dependency
    metrics = None
    trace = None
    OTLPMetricExporter = None
    OTLPSpanExporter = None
    FastAPIInstrumentor = None
    SQLAlchemyInstrumentor = None
    MeterProvider = None
    PeriodicExportingMetricReader = None
    Resource = None
    TracerProvider = None
    BatchSpanProcessor = None


logger = logging.getLogger("aura")

_LOCK = Lock()
_GAUGES: dict[str, float] = {}
_GAUGE_SERIES: dict[str, dict[tuple[tuple[str, str], ...], float]] = defaultdict(dict)
_TRACE_EVENTS: dict[str, list[str]] = defaultdict(list)
_INSTRUMENTS: dict[str, Any] = {}
_OTEL_INITIALIZED = False
_FASTAPI_INSTRUMENTED = False
_SQLALCHEMY_INSTRUMENTED = False
_TRACE_ID: ContextVar[str | None] = ContextVar("aura_trace_id", default=None)


def init_otel(service_name: str, otlp_endpoint: str | None = None) -> None:
    global _OTEL_INITIALIZED
    with _LOCK:
        if _OTEL_INITIALIZED:
            return
        _OTEL_INITIALIZED = True

    if metrics is None or trace is None or Resource is None:
        logger.info("otel_optional_dependencies_missing service_name=%s", service_name)
        _register_instruments()
        return

    resource = Resource.create({"service.name": service_name})

    if TracerProvider is not None:
        tracer_provider = TracerProvider(resource=resource)
        if otlp_endpoint and OTLPSpanExporter is not None and BatchSpanProcessor is not None:
            tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint)))
        trace.set_tracer_provider(tracer_provider)

    if MeterProvider is not None:
        readers = []
        if otlp_endpoint and OTLPMetricExporter is not None and PeriodicExportingMetricReader is not None:
            readers.append(PeriodicExportingMetricReader(OTLPMetricExporter(endpoint=otlp_endpoint)))
        metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=readers))

    _register_instruments()


def instrument_fastapi(app: Any) -> None:
    global _FASTAPI_INSTRUMENTED
    if _FASTAPI_INSTRUMENTED or FastAPIInstrumentor is None:
        return
    FastAPIInstrumentor.instrument_app(app)
    _FASTAPI_INSTRUMENTED = True


def instrument_sqlalchemy() -> None:
    global _SQLALCHEMY_INSTRUMENTED
    if _SQLALCHEMY_INSTRUMENTED or SQLAlchemyInstrumentor is None:
        return
    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
    _SQLALCHEMY_INSTRUMENTED = True


def set_current_trace_id(trace_id: str | None) -> None:
    _TRACE_ID.set(trace_id)


def get_current_trace_id() -> str | None:
    return _TRACE_ID.get()


def record_trace_event(trace_id: str, message: str) -> None:
    if not trace_id:
        return
    with _LOCK:
        _TRACE_EVENTS[trace_id].append(message)


def get_trace_events(trace_id: str) -> list[str]:
    with _LOCK:
        return list(_TRACE_EVENTS.get(trace_id, []))


def clear_trace_events() -> None:
    with _LOCK:
        _TRACE_EVENTS.clear()


def set_gauge_value(name: str, value: float, attributes: dict[str, str] | None = None) -> None:
    normalized_attributes = _normalize_attributes(attributes)
    with _LOCK:
        _GAUGE_SERIES[name][normalized_attributes] = float(value)
        if normalized_attributes:
            _GAUGES[name] = max(_GAUGE_SERIES[name].values(), default=float(value))
        else:
            _GAUGES[name] = float(value)
    instrument = _INSTRUMENTS.get(name)
    if instrument is not None:
        try:
            instrument.set(float(value), dict(normalized_attributes))
        except Exception:  # pragma: no cover - defensive
            logger.debug("otel_gauge_set_failed name=%s", name, exc_info=True)


def get_gauge_value(
    name: str,
    default: float = 0.0,
    attributes: dict[str, str] | None = None,
) -> float:
    normalized_attributes = _normalize_attributes(attributes)
    with _LOCK:
        if normalized_attributes:
            return float(_GAUGE_SERIES.get(name, {}).get(normalized_attributes, default))
        return float(_GAUGES.get(name, default))


def record_request_latency(*, endpoint: str, method: str, status: int, latency_ms: float) -> None:
    _record_histogram(
        "aura.request.latency_ms",
        latency_ms,
        {"endpoint": endpoint, "method": method, "status": str(status)},
    )


def record_job_success(*, job_type: str, queue: str) -> None:
    _increment_counter("aura.job.success_total", 1, {"job_type": job_type, "queue": queue})


def record_job_failure(*, job_type: str, queue: str) -> None:
    _increment_counter("aura.job.failure_total", 1, {"job_type": job_type, "queue": queue})


def record_retrieval_latency(*, space_id: str, reranker: str, latency_ms: float) -> None:
    _record_histogram(
        "aura.retrieval.latency_ms",
        latency_ms,
        {"space_id": space_id, "reranker": reranker},
    )


def record_litellm_call_latency(*, model: str, tenant_id: str, latency_ms: float) -> None:
    _record_histogram(
        "aura.litellm.call_latency_ms",
        latency_ms,
        {"model": model, "tenant_id": tenant_id},
    )


def record_litellm_tokens_used(*, model: str, tenant_id: str, direction: str, tokens: int) -> None:
    _increment_counter(
        "aura.litellm.tokens_used",
        tokens,
        {"model": model, "tenant_id": tenant_id, "direction": direction},
    )


def record_pii_transform_error(*, mode: str, tenant_id: str) -> None:
    _increment_counter("aura.pii.transform_error_total", 1, {"mode": mode, "tenant_id": tenant_id})


def record_sandbox_wall_time(*, skill_name: str, status: str, wall_time_s: float) -> None:
    _record_histogram(
        "aura.sandbox.wall_time_s",
        wall_time_s,
        {"skill_name": skill_name, "status": status},
    )


def _register_instruments() -> None:
    if _INSTRUMENTS:
        return
    meter = metrics.get_meter("aura") if metrics is not None else None

    _INSTRUMENTS.update(
        {
            "aura.request.latency_ms": _make_instrument(meter, "create_histogram", "aura.request.latency_ms"),
            "aura.job.success_total": _make_instrument(meter, "create_counter", "aura.job.success_total"),
            "aura.job.failure_total": _make_instrument(meter, "create_counter", "aura.job.failure_total"),
            "aura.retrieval.latency_ms": _make_instrument(meter, "create_histogram", "aura.retrieval.latency_ms"),
            "aura.litellm.call_latency_ms": _make_instrument(meter, "create_histogram", "aura.litellm.call_latency_ms"),
            "aura.litellm.tokens_used": _make_instrument(meter, "create_counter", "aura.litellm.tokens_used"),
            "aura.identity.sync_freshness_s": _make_instrument(meter, "create_gauge", "aura.identity.sync_freshness_s"),
            "aura.datasource.stale_count": _make_instrument(meter, "create_gauge", "aura.datasource.stale_count"),
            "aura.pii.transform_error_total": _make_instrument(meter, "create_counter", "aura.pii.transform_error_total"),
            "aura.sandbox.wall_time_s": _make_instrument(meter, "create_histogram", "aura.sandbox.wall_time_s"),
        }
    )


def _make_instrument(meter: Any, method_name: str, instrument_name: str) -> Any:
    if meter is None:
        return None
    try:
        factory: Callable[..., Any] = getattr(meter, method_name)
        return factory(instrument_name)
    except Exception:  # pragma: no cover - defensive
        logger.debug("otel_instrument_registration_failed name=%s", instrument_name, exc_info=True)
        return None


def _record_histogram(name: str, value: float, attributes: dict[str, str]) -> None:
    instrument = _INSTRUMENTS.get(name)
    if instrument is not None:
        try:
            instrument.record(float(value), attributes)
        except Exception:  # pragma: no cover - defensive
            logger.debug("otel_histogram_record_failed name=%s", name, exc_info=True)


def _increment_counter(name: str, value: int, attributes: dict[str, str]) -> None:
    instrument = _INSTRUMENTS.get(name)
    if instrument is not None:
        try:
            instrument.add(int(value), attributes)
        except Exception:  # pragma: no cover - defensive
            logger.debug("otel_counter_add_failed name=%s", name, exc_info=True)


def _normalize_attributes(attributes: dict[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not attributes:
        return ()
    return tuple(sorted((str(key), str(value)) for key, value in attributes.items()))
