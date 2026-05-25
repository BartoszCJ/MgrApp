"""Testy modulu metrics.py: precision, recall, coverage, latency."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from forensics.core.models import (
    AddressLabel,
    Alert,
    GraphEdge,
    GraphNode,
    TraceGraph,
    TraceResult,
    Transaction,
)
from forensics.metrics import (
    GroundTruthError,
    compute_metrics,
    load_ground_truth,
)

ROOT = "0x098B716B8Aaf21512996dC57EB0615e2383E2f96"  # Ronin attacker (z ronin.json)
HUOBI_DEPOSIT = "0x17A96cd2afF8BeCE22b54a83955FbAB5C92A98ca"
FTX_DEPOSIT = "0x036587E77eABE6a7E181886A5a6ed10dC25654f9"
RANDOM = "0x" + "1" * 40


def _make_result(
    *,
    graph_addresses: list[str] | None = None,
    alerts: list[Alert] | None = None,
    labels: list[AddressLabel] | None = None,
) -> TraceResult:
    """Buduje TraceResult z konkretnymi adresami w grafie i listą alertow."""
    graph_addresses = graph_addresses or []
    nodes = [
        GraphNode(address=addr, depth=i, is_root=(i == 0))
        for i, addr in enumerate(graph_addresses)
    ]
    graph = TraceGraph(
        nodes=nodes,
        edges=[],
        root_address=graph_addresses[0] if graph_addresses else ROOT,
        hops=2,
        fetched_addresses=len(graph_addresses),
    )
    return TraceResult(
        root_address=graph_addresses[0] if graph_addresses else ROOT,
        transactions=[],
        labels=labels or [],
        alerts=alerts or [],
        graph=graph,
        total_transactions=0,
    )


def _alert(alert_type: str, metadata: dict | None = None) -> Alert:
    return Alert(
        type=alert_type,
        severity="critical" if "tornado" in alert_type else "warning",
        title=f"test {alert_type}",
        message="",
        metadata=metadata or {},
    )


# load_ground_truth ----------------------------------------------------------


def test_load_ground_truth_ronin_loads() -> None:
    gt = load_ground_truth("ronin")
    assert gt["case"] == "Ronin Bridge"
    assert gt["attack_block"] == 14442835
    assert "addresses" in gt
    assert "expected_heuristic_hits" in gt


def test_load_ground_truth_euler_loads() -> None:
    gt = load_ground_truth("euler")
    assert gt["case"] == "Euler Finance"


def test_load_ground_truth_nomad_loads() -> None:
    gt = load_ground_truth("nomad")
    assert gt["case"] == "Nomad Bridge"


def test_load_ground_truth_missing_case_raises() -> None:
    with pytest.raises(GroundTruthError):
        load_ground_truth("nieistniejacy_case_12345")


# compute_metrics: address recall --------------------------------------------


def test_address_recall_zero_when_only_root_in_graph() -> None:
    """Graf zawiera tylko root - brak adresow z ground truth -> recall 0."""
    result = _make_result(graph_addresses=[ROOT])
    metrics = compute_metrics(result, "ronin", latency_seconds=1.0)
    # ROOT jest w ronin.json jako attacker_root, wiec 1 z 23 znalezione = ~0.04
    assert metrics.address_recall > 0.0
    assert metrics.address_recall < 0.1
    assert metrics.breakdown["addresses_found"] == 1
    assert metrics.breakdown["addresses_expected"] > 20


def test_address_recall_partial_when_some_addresses_found() -> None:
    """Graf zawiera root + 2 znane adresy z ronin.json."""
    result = _make_result(graph_addresses=[ROOT, HUOBI_DEPOSIT, FTX_DEPOSIT])
    metrics = compute_metrics(result, "ronin", latency_seconds=1.0)
    assert metrics.breakdown["addresses_found"] == 3
    assert metrics.address_recall > 0.1


def test_address_recall_ignores_unknown_addresses() -> None:
    """Adresy spoza ground truth nie psuja recall (ale tez nie pomagaja)."""
    result = _make_result(graph_addresses=[ROOT, RANDOM])
    metrics = compute_metrics(result, "ronin", latency_seconds=1.0)
    # tylko ROOT z ground truth, RANDOM nie liczy sie
    assert metrics.breakdown["addresses_found"] == 1


# compute_metrics: heuristic precision/recall --------------------------------


def test_heuristic_recall_full_when_all_expected_hit() -> None:
    """Ronin oczekuje tornado_cash + cex + bridges. Trafiamy wszystkie 3."""
    result = _make_result(
        graph_addresses=[ROOT],
        alerts=[
            _alert("tornado_cash_deposit"),
            _alert("cex_outgoing", metadata={"name": "Huobi"}),
            _alert("bridge_outgoing"),
        ],
    )
    metrics = compute_metrics(result, "ronin", latency_seconds=1.0)
    assert metrics.heuristic_recall == 1.0
    assert metrics.heuristic_precision == 1.0
    assert metrics.breakdown["heuristics_false_positives"] == []


def test_heuristic_recall_partial() -> None:
    """Tylko 1 z 3 oczekiwanych heurystyk trafiona."""
    result = _make_result(
        graph_addresses=[ROOT],
        alerts=[_alert("tornado_cash_deposit")],
    )
    metrics = compute_metrics(result, "ronin", latency_seconds=1.0)
    # 1 z 3 (tornado, cex, bridges) trafionych
    assert metrics.heuristic_recall == pytest.approx(1 / 3, abs=0.01)
    assert metrics.heuristic_precision == 1.0  # to co trafione, trafione poprawnie


def test_heuristic_precision_drops_on_false_positive() -> None:
    """Euler NIE oczekuje CEX (case 'failed laundering'). Alert CEX = fałszywy alarm."""
    result = _make_result(
        graph_addresses=[ROOT],
        alerts=[
            _alert("tornado_cash_deposit"),
            _alert("cex_outgoing", metadata={"name": "Binance"}),
        ],
    )
    metrics = compute_metrics(result, "euler", latency_seconds=1.0)
    # tornado dobry, cex fałszywy alarm -> precision 1/2 = 0.5
    assert metrics.heuristic_precision == 0.5
    assert "cex" in metrics.breakdown["heuristics_false_positives"]


def test_heuristic_recall_zero_when_no_alerts() -> None:
    result = _make_result(graph_addresses=[ROOT])
    metrics = compute_metrics(result, "ronin", latency_seconds=1.0)
    assert metrics.heuristic_recall == 0.0
    assert metrics.heuristic_precision == 0.0  # 0/0 -> 0.0 wg _safe_div


# compute_metrics: cex coverage ----------------------------------------------


def test_cex_coverage_full_when_all_exchanges_found() -> None:
    """Ronin oczekuje Huobi, FTX, Crypto.com - trafiamy wszystkie 3."""
    result = _make_result(
        graph_addresses=[ROOT],
        alerts=[
            _alert("cex_outgoing", metadata={"name": "Huobi"}),
            _alert("cex_outgoing", metadata={"name": "FTX"}),
            _alert("cex_outgoing", metadata={"name": "Crypto.com"}),
        ],
    )
    metrics = compute_metrics(result, "ronin", latency_seconds=1.0)
    assert metrics.cex_coverage == 1.0
    assert len(metrics.breakdown["cex_exchanges_found"]) == 3


def test_cex_coverage_partial() -> None:
    """Tylko Huobi z 3 oczekiwanych gield."""
    result = _make_result(
        graph_addresses=[ROOT],
        alerts=[_alert("cex_outgoing", metadata={"name": "Huobi Hot Wallet 7"})],
    )
    metrics = compute_metrics(result, "ronin", latency_seconds=1.0)
    assert metrics.cex_coverage == pytest.approx(1 / 3, abs=0.01)


def test_cex_coverage_normalizes_exchange_name() -> None:
    """'Binance Hot Wallet 7' -> 'binance' do porownania."""
    result = _make_result(
        graph_addresses=[ROOT],
        alerts=[_alert("cex_outgoing", metadata={"name": "Huobi Cold Storage"})],
    )
    metrics = compute_metrics(result, "ronin", latency_seconds=1.0)
    assert "huobi" in metrics.breakdown["cex_exchanges_found"]


# compute_metrics: latency + notes ------------------------------------------


def test_latency_passed_through() -> None:
    result = _make_result(graph_addresses=[ROOT])
    metrics = compute_metrics(result, "ronin", latency_seconds=2.345)
    assert metrics.latency_seconds == 2.345


def test_notes_flag_missing_heuristics() -> None:
    """Gdy nic nie trafione, notes wymienia czego brakuje."""
    result = _make_result(graph_addresses=[ROOT])
    metrics = compute_metrics(result, "ronin", latency_seconds=1.0)
    assert any("Brakujace heurystyki" in note for note in metrics.notes)


def test_notes_flag_false_positives() -> None:
    """Euler + alert CEX -> notes pokazuje fałszywy alarm."""
    result = _make_result(
        graph_addresses=[ROOT],
        alerts=[_alert("cex_outgoing", metadata={"name": "Binance"})],
    )
    metrics = compute_metrics(result, "euler", latency_seconds=1.0)
    assert any("Fałszywe alarmy" in note or "alszywe" in note for note in metrics.notes)


def test_metrics_report_serializable() -> None:
    """MetricsReport powinien dac sie zserializowac do JSON (przez FastAPI)."""
    result = _make_result(graph_addresses=[ROOT])
    metrics = compute_metrics(result, "ronin", latency_seconds=1.0)
    payload = metrics.model_dump()
    assert payload["case_name"] == "ronin"
    assert 0.0 <= payload["address_recall"] <= 1.0
    assert "breakdown" in payload


def test_labels_count_as_found_addresses() -> None:
    """Adresy z Arkham labels tez powinny liczyc sie jako 'znalezione'."""
    result = _make_result(
        graph_addresses=[ROOT],
        labels=[AddressLabel(address=HUOBI_DEPOSIT, label="Huobi", category="cex")],
    )
    metrics = compute_metrics(result, "ronin", latency_seconds=1.0)
    # ROOT + HUOBI_DEPOSIT z ground truth
    assert metrics.breakdown["addresses_found"] >= 2


def test_transaction_addresses_count_as_found() -> None:
    """Adresy z transactions (from/to) tez licza sie jako 'znalezione'."""
    tx = Transaction(
        hash="0x" + "0" * 64,
        block_number=14442835,
        timestamp=datetime(2022, 3, 23, tzinfo=UTC),
        from_address=ROOT,
        to_address=HUOBI_DEPOSIT,
        value_wei="1000000000000000000",
        value_eth=1.0,
    )
    graph = TraceGraph(
        nodes=[GraphNode(address=ROOT, depth=0, is_root=True)],
        edges=[
            GraphEdge(
                source=ROOT, target=HUOBI_DEPOSIT, tx_hash=tx.hash, value=1.0, block=14442835
            )
        ],
        root_address=ROOT,
        hops=2,
    )
    result = TraceResult(
        root_address=ROOT,
        transactions=[tx],
        graph=graph,
    )
    metrics = compute_metrics(result, "ronin", latency_seconds=1.0)
    assert metrics.breakdown["addresses_found"] >= 2
