"""Metryki efektywnosci sledzenia: precision, recall, coverage, latency.

Co to robi:
- laduje ground truth dla wybranego case study z `data/ground_truth/<case>.json`,
- porownuje wynik trace (graf BFS + alerty heurystyk) z oczekiwanym wynikiem,
- liczy 4 metryki + breakdown z surowymi liczbami dla UI.

Po co:
- realizuje zadanie 7 z tematu pracy magisterskiej Ruslana ("ocena efektywnosci"),
- daje konkretne liczby do rozdzialu wynikow zamiast jakosciowych ocen,
- precision/recall vs publiczne raporty (Chainalysis, Elliptic, Mandiant) to standard branzowy.

Mapowanie heurystyk -> typy alertow (z modulow heuristics/):
- tornado_cash -> 'tornado_cash_deposit', 'tornado_cash_withdraw'
- cex          -> 'cex_outgoing', 'cex_incoming'
- bridges      -> 'bridge_outgoing', 'bridge_incoming'
- peel_chain   -> 'peel_chain'
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from loguru import logger

from forensics.core.models import MetricsReport, TraceResult

_GROUND_TRUTH_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ground_truth"

# Typy alertow generowane przez kazda heurystyke (z heuristics/*.py)
_HEURISTIC_TO_ALERT_TYPES: dict[str, set[str]] = {
    "tornado_cash": {"tornado_cash_deposit", "tornado_cash_withdraw"},
    "cex": {"cex_outgoing", "cex_incoming"},
    "bridges": {"bridge_outgoing", "bridge_incoming"},
    "peel_chain": {"peel_chain"},
}


class GroundTruthError(Exception):
    """Brak pliku ground truth albo plik niepoprawny."""


@lru_cache(maxsize=8)
def load_ground_truth(case_name: str) -> dict[str, Any]:
    """Laduje plik ground truth dla case study (cache na nazwie).

    Args:
        case_name: np. 'ronin', 'euler', 'nomad' - musi byc nazwa pliku bez .json.

    Raises:
        GroundTruthError: jesli plik nie istnieje lub JSON jest popsuty.
    """
    path = _GROUND_TRUTH_DIR / f"{case_name}.json"
    if not path.exists():
        raise GroundTruthError(f"Brak ground truth dla case '{case_name}': {path}")

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GroundTruthError(f"Niepoprawny JSON w {path}: {exc}") from exc


def _extract_expected_addresses(ground_truth: dict[str, Any]) -> set[str]:
    """Zwraca zbior wszystkich 0x... adresow ze wszystkich sekcji ground_truth.addresses.*

    Pomija wartosci ktore nie sa adresami Ethereum (np. logiczne nazwy
    'tornado_cash_pools', 'renBTC_bridge' w nomad.json).
    """
    expected: set[str] = set()
    sections = ground_truth.get("addresses", {})
    for entries in sections.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            addr = entry.get("address", "")
            if isinstance(addr, str) and addr.startswith("0x") and len(addr) == 42:
                expected.add(addr.lower())
    return expected


def _extract_found_addresses(trace_result: TraceResult) -> set[str]:
    """Zwraca zbior wszystkich adresow ktore BFS znalazl w grafie.

    Bierzemy z `graph.nodes` (najpelniejsze zrodlo) + adresy z transakcji
    + adresy etykiet z Arkham. Wszystko lowercase.
    """
    found: set[str] = set()
    if trace_result.graph is not None:
        for node in trace_result.graph.nodes:
            found.add(node.address.lower())
    for tx in trace_result.transactions:
        found.add(tx.from_address.lower())
        if tx.to_address:
            found.add(tx.to_address.lower())
    for label in trace_result.labels:
        found.add(label.address.lower())
    return found


def _alert_categories_hit(trace_result: TraceResult) -> set[str]:
    """Zwraca zbior kategorii heurystyk ktore zgłosily alert.

    Kategoria = klucz z _HEURISTIC_TO_ALERT_TYPES. Jesli alert ma type
    np. 'tornado_cash_deposit', to kategoria to 'tornado_cash'.
    """
    hit: set[str] = set()
    for alert in trace_result.alerts:
        for category, alert_types in _HEURISTIC_TO_ALERT_TYPES.items():
            if alert.type in alert_types:
                hit.add(category)
                break
    return hit


def _expected_categories(ground_truth: dict[str, Any]) -> set[str]:
    """Zwraca zbior kategorii heurystyk ktore POWINNY trafic (expected=True/partial)."""
    expected: set[str] = set()
    hits = ground_truth.get("expected_heuristic_hits", {})
    for category, spec in hits.items():
        if category not in _HEURISTIC_TO_ALERT_TYPES:
            continue
        # 'expected' moze byc True, False albo 'partial' (Nomad CEX case)
        if spec.get("expected") in (True, "partial"):
            expected.add(category)
    return expected


def _allowed_categories(ground_truth: dict[str, Any]) -> set[str]:
    """Zbior kategorii ktore NIE sa fałszywym alarmem.

    Rozni sie od _expected_categories tym, ze 'partial' to nie 'expected'
    ale tez nie 'false positive'. Tu liczymy precision jako:
    hit ∩ allowed / hit -> czyli false positive tylko gdy expected=False.
    """
    allowed: set[str] = set()
    hits = ground_truth.get("expected_heuristic_hits", {})
    for category, spec in hits.items():
        if category not in _HEURISTIC_TO_ALERT_TYPES:
            continue
        if spec.get("expected") in (True, "partial"):
            allowed.add(category)
    return allowed


def _cex_exchanges_found(trace_result: TraceResult) -> set[str]:
    """Zwraca zbior nazw giełd ktore pojawily sie w alertach CEX.

    Nazwa wyciagana z `Alert.metadata.name` (ustawiane przez known_address.py).
    Lowercase do porownywania. Wycinamy szczegóły typu 'Binance Hot Wallet 7'
    do samego 'binance' przez heurystyke 'pierwsze slowo'.
    """
    exchanges: set[str] = set()
    cex_types = _HEURISTIC_TO_ALERT_TYPES["cex"]
    for alert in trace_result.alerts:
        if alert.type not in cex_types:
            continue
        name = alert.metadata.get("name", "")
        if not isinstance(name, str) or not name:
            continue
        # 'Binance Hot Wallet 7' -> 'binance'
        first_word = name.split()[0].lower()
        exchanges.add(first_word)
    return exchanges


def _cex_exchanges_expected(ground_truth: dict[str, Any]) -> set[str]:
    """Zwraca zbior nazw oczekiwanych giełd (z expected_heuristic_hits.cex.exchanges)."""
    expected: set[str] = set()
    cex_spec = ground_truth.get("expected_heuristic_hits", {}).get("cex", {})
    for exchange in cex_spec.get("exchanges", []) or []:
        if isinstance(exchange, str):
            expected.add(exchange.split()[0].lower())
    return expected


def _safe_div(numerator: int, denominator: int) -> float:
    """Bezpieczne dzielenie - zwraca 0.0 dla denominator=0 (zamiast crashu).

    Konwencja: 'brak oczekiwan = brak punktow do zdobycia = recall 0.0
    ale nie kara'. Wywolujacy moze sam zinterpretowac kontekst (notes).
    """
    if denominator == 0:
        return 0.0
    return round(numerator / denominator, 4)


def compute_metrics(
    trace_result: TraceResult,
    case_name: str,
    latency_seconds: float,
) -> MetricsReport:
    """Liczy metryki efektywnosci porownujac trace z ground truth.

    Args:
        trace_result: pelen wynik z `/api/trace` (graf + alerty + labels).
        case_name: np. 'ronin', 'euler', 'nomad'.
        latency_seconds: zmierzony czas calego endpointu.

    Raises:
        GroundTruthError: gdy nie ma pliku dla tego case'a.
    """
    ground_truth = load_ground_truth(case_name)

    # Address recall ----------------------------------------------------------
    expected_addrs = _extract_expected_addresses(ground_truth)
    found_addrs = _extract_found_addresses(trace_result)
    addrs_found = expected_addrs & found_addrs
    address_recall = _safe_div(len(addrs_found), len(expected_addrs))

    # Heuristic precision / recall -------------------------------------------
    hit_categories = _alert_categories_hit(trace_result)
    expected_categories = _expected_categories(ground_truth)
    allowed_categories = _allowed_categories(ground_truth)

    heuristics_correctly_hit = hit_categories & allowed_categories
    heuristic_precision = _safe_div(
        len(heuristics_correctly_hit),
        len(hit_categories),
    )
    heuristic_recall = _safe_div(
        len(hit_categories & expected_categories),
        len(expected_categories),
    )

    # CEX coverage ------------------------------------------------------------
    cex_expected = _cex_exchanges_expected(ground_truth)
    cex_found = _cex_exchanges_found(trace_result) & cex_expected
    cex_coverage = _safe_div(len(cex_found), len(cex_expected))

    # Notes -------------------------------------------------------------------
    notes: list[str] = []
    false_positives = hit_categories - allowed_categories
    if false_positives:
        notes.append(
            f"Fałszywe alarmy (kategorie nie oczekiwane wg ground truth): "
            f"{sorted(false_positives)}"
        )
    missing = expected_categories - hit_categories
    if missing:
        notes.append(f"Brakujace heurystyki (oczekiwane ale brak alertu): {sorted(missing)}")
    if not expected_categories:
        notes.append("Brak oczekiwan heurystyk w ground truth - heuristic_recall=0 to artefakt.")
    if len(expected_addrs) == 0:
        notes.append("Brak adresow w ground truth - address_recall=0 to artefakt.")
    if not cex_expected:
        notes.append("Brak oczekiwanych gield - cex_coverage=0 to artefakt.")

    breakdown: dict[str, Any] = {
        "addresses_found": len(addrs_found),
        "addresses_expected": len(expected_addrs),
        "addresses_in_trace": len(found_addrs),
        "heuristics_hit": sorted(hit_categories),
        "heuristics_expected": sorted(expected_categories),
        "heuristics_false_positives": sorted(false_positives),
        "heuristics_missing": sorted(missing),
        "cex_exchanges_found": sorted(cex_found),
        "cex_exchanges_expected": sorted(cex_expected),
    }

    logger.info(
        "Metryki dla {}: address_recall={:.2f}, heuristic_precision={:.2f}, "
        "heuristic_recall={:.2f}, cex_coverage={:.2f}, latency={:.2f}s",
        case_name,
        address_recall,
        heuristic_precision,
        heuristic_recall,
        cex_coverage,
        latency_seconds,
    )

    return MetricsReport(
        case_name=case_name,
        address_recall=address_recall,
        heuristic_precision=heuristic_precision,
        heuristic_recall=heuristic_recall,
        cex_coverage=cex_coverage,
        latency_seconds=round(latency_seconds, 3),
        breakdown=breakdown,
        notes=notes,
    )
