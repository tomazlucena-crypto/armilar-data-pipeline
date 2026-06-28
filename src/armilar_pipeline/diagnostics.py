from __future__ import annotations

import socket
import ssl
import time
import urllib.error
import urllib.request
from typing import Any

from .config import PipelineConfig, Source
from .util import safe_runtime_info, utc_now


def _dns_probe(hostname: str, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    old_timeout = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        records = socket.getaddrinfo(hostname, 443, type=socket.SOCK_STREAM)
        addresses = sorted({record[4][0] for record in records})
        return {
            "ok": True,
            "addresses": addresses,
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        }
    except OSError as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        }
    finally:
        socket.setdefaulttimeout(old_timeout)


def _tls_probe(hostname: str, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    context = ssl.create_default_context()
    try:
        with socket.create_connection((hostname, 443), timeout=timeout) as raw_socket:
            with context.wrap_socket(raw_socket, server_hostname=hostname) as secure_socket:
                certificate = secure_socket.getpeercert()
                return {
                    "ok": True,
                    "protocol": secure_socket.version(),
                    "cipher": secure_socket.cipher()[0] if secure_socket.cipher() else None,
                    "certificate_subject": certificate.get("subject"),
                    "certificate_not_after": certificate.get("notAfter"),
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
                }
    except (OSError, ssl.SSLError) as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        }


def _http_probe(source: Source, user_agent: str) -> dict[str, Any]:
    started = time.monotonic()
    headers = {
        "User-Agent": user_agent,
        "Accept": "*/*",
        "Range": "bytes=0-4095",
    }
    request = urllib.request.Request(source.url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=source.timeout_seconds) as response:
            sample = response.read(min(source.max_bytes, 4096))
            return {
                "ok": True,
                "status": getattr(response, "status", None),
                "final_url": response.geturl(),
                "content_type": response.headers.get("Content-Type"),
                "content_length": response.headers.get("Content-Length"),
                "sample_bytes": len(sample),
                "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "status": exc.code,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        }
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {
            "ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 2),
        }


def diagnose(config: PipelineConfig) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    dns_cache: dict[str, dict[str, Any]] = {}
    tls_cache: dict[str, dict[str, Any]] = {}

    for source in config.sources:
        if source.hostname not in dns_cache:
            dns_cache[source.hostname] = _dns_probe(source.hostname, source.timeout_seconds)
        if dns_cache[source.hostname].get("ok") and source.hostname not in tls_cache:
            tls_cache[source.hostname] = _tls_probe(source.hostname, source.timeout_seconds)

        dns_result = dns_cache[source.hostname]
        tls_result = tls_cache.get(source.hostname, {"ok": False, "skipped": "dns_failed"})
        http_result = (
            _http_probe(source, config.user_agent)
            if dns_result.get("ok")
            else {"ok": False, "skipped": "dns_failed"}
        )
        results.append(
            {
                "source_id": source.source_id,
                "provider": source.provider,
                "hostname": source.hostname,
                "required": source.required,
                "mode": source.mode,
                "dns": dns_result,
                "tls": tls_result,
                "http": http_result,
            }
        )

    required_failures = [
        result["source_id"]
        for result in results
        if result["required"] and not result["http"].get("ok")
    ]
    return {
        "schema_version": "1.0",
        "generated_at": utc_now(),
        "runtime": safe_runtime_info(),
        "summary": {
            "sources": len(results),
            "http_ok": sum(1 for item in results if item["http"].get("ok")),
            "dns_failures": sum(1 for item in results if not item["dns"].get("ok")),
            "required_failures": required_failures,
        },
        "results": results,
    }
