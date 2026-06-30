from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class SDMXAdapterError(RuntimeError):
    """Raised when the optional SDMX acquisition layer cannot run safely."""


@dataclass(frozen=True, slots=True)
class SDMXQuerySpec:
    provider_code: str
    resource_id: str
    key: str
    start_period: str
    end_period: str = ""
    params: dict[str, str] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.provider_code.strip():
            raise SDMXAdapterError("provider_code is required")
        if not self.resource_id.strip():
            raise SDMXAdapterError("resource_id is required")
        if not self.key.strip():
            raise SDMXAdapterError("key is required")
        if not self.start_period.strip():
            raise SDMXAdapterError("start_period is required")


def create_client(provider_code: str) -> Any:
    try:
        import sdmx  # type: ignore
    except ImportError as exc:
        raise SDMXAdapterError(
            "sdmx1 is not installed; install the optional 'sdmx' dependency group"
        ) from exc
    try:
        return sdmx.Client(provider_code)
    except Exception as exc:  # pragma: no cover - provider registry is external
        raise SDMXAdapterError(f"could not initialise SDMX provider {provider_code!r}: {exc}") from exc


def fetch_message(spec: SDMXQuerySpec, *, client: Any | None = None) -> Any:
    spec.validate()
    service = client if client is not None else create_client(spec.provider_code)
    params = dict(spec.params)
    params["startPeriod"] = spec.start_period
    if spec.end_period:
        params["endPeriod"] = spec.end_period
    try:
        return service.get("data", resource_id=spec.resource_id, key=spec.key, params=params)
    except Exception as exc:
        raise SDMXAdapterError(
            f"SDMX request failed for {spec.provider_code}/{spec.resource_id}: {exc}"
        ) from exc
