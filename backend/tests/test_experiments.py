"""Testy zapisu eksperymentu (forensics.experiments.write_experiment).

Sprawdzamy, ze powstaja 3 pliki (json/md/csv) z metadanymi: timestamp,
cache_mode, per-case metryki, oraz ze blad case'a jest obsluzony.
Izolacja: katalog wynikow podmieniany na tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from forensics import experiments
from forensics.core.models import (
    ExperimentCaseResult,
    ExperimentSaveRequest,
    MetricsReport,
)


@pytest.fixture(autouse=True)
def _isolated_results_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(experiments, "_RESULTS_DIR", tmp_path)
    return tmp_path


def test_write_experiment_creates_json_md_csv(_isolated_results_dir: Path) -> None:
    results_dir = _isolated_results_dir
    ronin_metrics = MetricsReport(
        case_name="ronin",
        address_recall=0.8,
        heuristic_precision=1.0,
        heuristic_recall=0.5,
        cex_coverage=1.0,
        latency_seconds=12.3,
        breakdown={
            "cex_destination_addresses_found": 8,
            "cex_destination_addresses_expected": 8,  # applicable
        },
    )
    nomad_metrics = MetricsReport(
        case_name="nomad",
        address_recall=0.75,
        heuristic_precision=0.5,
        heuristic_recall=0.33,
        cex_coverage=0.0,
        latency_seconds=6.0,
        breakdown={"cex_destination_addresses_expected": 0},  # brak -> N/A
    )
    request = ExperimentSaveRequest(
        cache_mode="normal",
        cases=[
            ExperimentCaseResult(
                case="ronin",
                address="0xabc",
                hops=2,
                start_block=1,
                end_block=2,
                nodes=10,
                edges=9,
                alerts=3,
                labels=4,
                metrics=ronin_metrics,
                cache={"mode": "normal"},
            ),
            ExperimentCaseResult(
                case="nomad",
                address="0xfff",
                hops=2,
                nodes=20,
                edges=19,
                alerts=5,
                labels=2,
                metrics=nomad_metrics,
            ),
            ExperimentCaseResult(
                case="euler",
                address="0xdef",
                hops=2,
                metrics=None,
                error="boom",
            ),
        ],
    )

    result = experiments.write_experiment(request)

    assert len(result.files) == 3
    assert result.commit_hash is None or isinstance(result.commit_hash, str)

    suffixes = sorted(p.suffix for p in results_dir.glob("*"))
    assert suffixes == [".csv", ".json", ".md"]

    # JSON: surowe dane (pelny zapis, bez logiki N/A)
    data = json.loads(next(results_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert data["cache_mode"] == "normal"
    assert len(data["cases"]) == 3
    assert data["cases"][0]["metrics"]["address_recall"] == 0.8

    # MD: ronin applicable -> %, nomad N/A, euler blad, + wiersz Srednia
    md = next(results_dir.glob("*.md")).read_text(encoding="utf-8")
    assert "ronin" in md
    assert "N/A" in md  # CEX nomada (brak destinations_cex)
    assert "boom" in md
    assert "Średnia" in md

    # CSV: nowe kolumny + puste cex_coverage dla N/A (zostaje liczbowe)
    lines = next(results_dir.glob("*.csv")).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4  # header + 3 case'y
    header = lines[0]
    assert header.startswith("case,address,hops")
    assert "cex_coverage_applicable" in header
    assert "cex_destination_addresses_found" in header
    assert "cex_destination_addresses_expected" in header
    ronin_line = next(line for line in lines if line.startswith("ronin,"))
    assert "true" in ronin_line
    nomad_line = next(line for line in lines if line.startswith("nomad,"))
    assert "false" in nomad_line
