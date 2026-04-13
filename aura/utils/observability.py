from __future__ import annotations

from threading import Lock


_GAUGES: dict[str, float] = {}
_LOCK = Lock()


def set_gauge_value(name: str, value: float) -> None:
    with _LOCK:
        _GAUGES[name] = float(value)


def get_gauge_value(name: str, default: float = 0.0) -> float:
    with _LOCK:
        return float(_GAUGES.get(name, default))
