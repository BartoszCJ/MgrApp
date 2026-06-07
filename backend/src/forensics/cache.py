"""Dyskowy cache surowych odpowiedzi z zewnetrznych API (Etherscan, Arkham).

Po co:
- pobrac raz, zapisac na dysk, potem czytac lokalnie -> reprodukowalnosc wynikow,
  brak palenia free tier przy re-runach, mozliwosc demo offline na obronie,
- przy zmianie heurystyk/metryk przeliczamy z zapisanych danych BEZ ponownego API.

Co trzymamy: SUROWY JSON odpowiedzi API + metadane (koperta). Nigdy nie liczymy
ani nie zapisujemy klucza API - parametry sa sanityzowane (sekrety wyrzucone)
przed policzeniem klucza cache i przed zapisem na dysk.

Tryb refresh (per request, przez ContextVar): pomija odczyt z cache i nadpisuje
swiezymi danymi - do pokazania "API naprawde dziala".

Staty hit/miss (per request, przez ContextVar): zliczane per provider, endpoint
trace dopina je do wyniku, zeby bylo widac ile poszlo z cache.

Katalog cache: backend/.cache/ (override przez env FORENSICS_CACHE_DIR - uzywane
w testach). Zapis atomowy: tempfile -> os.replace (rename).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from contextvars import ContextVar
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from loguru import logger

CACHE_VERSION = 1

# backend/src/forensics/cache.py -> backend/
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CACHE_DIR = _BACKEND_ROOT / ".cache"

# Parametry-sekrety: NIGDY nie trafiaja do klucza cache ani na dysk.
_SECRET_PARAM_KEYS = {"apikey", "api_key", "api-key", "key", "token", "secret"}

# Per-request stan (ustawiany w endpointcie, czytany przez read/write).
_stats_var: ContextVar[dict[str, dict[str, int]] | None] = ContextVar(
    "forensics_cache_stats", default=None
)
_refresh_var: ContextVar[bool] = ContextVar("forensics_cache_refresh", default=False)


def cache_dir() -> Path:
    """Katalog cache. Override przez env FORENSICS_CACHE_DIR (uzywane w testach)."""
    raw = os.environ.get("FORENSICS_CACHE_DIR")
    return Path(raw) if raw else _DEFAULT_CACHE_DIR


# --- per-request kontekst -----------------------------------------------------


def begin_request(refresh: bool) -> dict[str, dict[str, int]]:
    """Reset stat + ustawienie trybu refresh dla biezacego requestu. Zwraca staty."""
    stats: dict[str, dict[str, int]] = {}
    _stats_var.set(stats)
    _refresh_var.set(refresh)
    return stats


def current_stats() -> dict[str, dict[str, int]]:
    """Staty hit/miss zebrane w biezacym requescie (per provider)."""
    stats = _stats_var.get()
    return stats if stats is not None else {}


def _record(provider: str, *, hit: bool) -> None:
    stats = _stats_var.get()
    if stats is None:
        return
    bucket = stats.setdefault(provider, {"hit": 0, "miss": 0})
    bucket["hit" if hit else "miss"] += 1


# --- klucz / sciezka ----------------------------------------------------------


def _sanitize_params(params: dict[str, Any]) -> dict[str, Any]:
    """Usuwa sekrety (apikey/key/token/...) - reszta zostaje, posortowana po kluczu."""
    return {str(k): v for k, v in params.items() if k.lower() not in _SECRET_PARAM_KEYS}


def _key_hash(provider: str, action: str, sanitized: dict[str, Any]) -> str:
    blob = json.dumps(
        {"provider": provider, "action": action, "params": sanitized},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:32]


def _safe(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in "-_")


def _path_for(provider: str, action: str, sanitized: dict[str, Any]) -> Path:
    h = _key_hash(provider, action, sanitized)
    return cache_dir() / f"{_safe(provider)}__{_safe(action)}__{h}.json"


# --- read / write -------------------------------------------------------------


def read(provider: str, action: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Zwraca koperte (dict) z cache albo None. Respektuje tryb refresh.

    W trybie refresh zawsze zwraca None (liczone jako miss) - wymusza fetch.
    """
    sanitized = _sanitize_params(params)
    if _refresh_var.get():
        _record(provider, hit=False)
        logger.opt(colors=True).debug(
            "Cache | {} | <yellow>refresh</yellow> {} -> pomijam cache", provider, action
        )
        return None

    path = _path_for(provider, action, sanitized)
    if not path.exists():
        _record(provider, hit=False)
        logger.opt(colors=True).debug("Cache | {} | <red>MISS</red> {}", provider, action)
        return None

    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        logger.warning("Cache | {} | uszkodzony plik {}: {}", provider, path.name, exc)
        _record(provider, hit=False)
        return None

    if not isinstance(envelope, dict) or envelope.get("cache_version") != CACHE_VERSION:
        # inny/stary format - traktujemy jak miss (nadpiszemy przy zapisie)
        _record(provider, hit=False)
        return None

    _record(provider, hit=True)
    logger.opt(colors=True).debug("Cache | {} | <green>HIT</green> {}", provider, action)
    return envelope


def write(
    provider: str,
    action: str,
    params: dict[str, Any],
    payload: Any,
    status_code: int,
) -> None:
    """Atomowo zapisuje koperte na dysk (.tmp -> rename). Sekrety odsiane."""
    sanitized = _sanitize_params(params)
    path = _path_for(provider, action, sanitized)
    envelope = {
        "cache_version": CACHE_VERSION,
        "provider": provider,
        "action": action,
        "params": sanitized,
        "fetched_at": datetime.now(UTC).isoformat(),
        "status_code": status_code,
        "payload": payload,
    }
    directory = path.parent
    try:
        directory.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=directory, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(envelope, fh, ensure_ascii=False, default=str)
            os.replace(tmp_name, path)  # atomowy rename
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp_name)
            raise
    except OSError as exc:
        logger.warning("Cache | {} | zapis nieudany {}: {}", provider, path.name, exc)


# --- zarzadzanie --------------------------------------------------------------


def clear() -> int:
    """Usuwa wszystkie pliki cache z backend/.cache/. Zwraca liczbe usunietych.

    UWAGA: czysci TYLKO katalog cache. Nie rusza results/ ani niczego innego.
    """
    directory = cache_dir()
    if not directory.exists():
        return 0
    deleted = 0
    for f in directory.glob("*.json"):
        try:
            f.unlink()
            deleted += 1
        except OSError as exc:
            logger.warning("Cache | nie moge usunac {}: {}", f.name, exc)
    logger.info("Cache | wyczyszczono {} plikow z {}", deleted, directory)
    return deleted


def status() -> dict[str, Any]:
    """Statystyki cache: liczba plikow per provider, rozmiar, wersja, sciezka."""
    directory = cache_dir()
    providers: dict[str, int] = {}
    total_files = 0
    total_bytes = 0
    if directory.exists():
        for f in directory.glob("*.json"):
            total_files += 1
            with contextlib.suppress(OSError):
                total_bytes += f.stat().st_size
            provider = f.name.split("__", 1)[0]
            providers[provider] = providers.get(provider, 0) + 1
    return {
        "cache_version": CACHE_VERSION,
        "dir": str(directory),
        "total_files": total_files,
        "total_bytes": total_bytes,
        "providers": providers,
    }
