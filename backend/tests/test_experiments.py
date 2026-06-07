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
    metrics = MetricsReport(
        case_name="ronin",
        address_recall=0.8,
        heuristic_precision=1.0,
        heuristic_recall=0.5,
        cex_coverage=1.0,
        latency_seconds=12.3,
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
                metrics=metrics,
                cache={"mode": "normal"},
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

    # JSON: pelne metadane
    data = json.loads(next(results_dir.glob("*.json")).read_text(encoding="utf-8"))
    assert data["cache_mode"] == "normal"
    assert data["timestamp"] == result.timestamp
    assert len(data["cases"]) == 2
    assert data["cases"][0]["case"] == "ronin"
    assert data["cases"][0]["metrics"]["address_recall"] == 0.8

    # MD: tabela do pracy, z bledem case'a euler
    md = next(results_dir.glob("*.md")).read_text(encoding="utf-8")
    assert "ronin" in md
    assert "80%" in md
    assert "boom" in md

    # CSV: header + 2 wiersze
    lines = next(results_dir.glob("*.csv")).read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    assert lines[0].startswith("case,address,hops")
