"""Zapis wynikow eksperymentu (3 case'y) do results/experiments/ z metadanymi.

Pliki: <timestamp>__experiment.{json,md,csv}
- json: pelne dane + metadane (timestamp, commit_hash, cache_mode, per-case wszystko),
- md:   tabela do wklejenia w rozdzial wynikow pracy,
- csv:  do dalszej obrobki / wykresow.

Zapis atomowy (tempfile -> os.replace). commit_hash pobierany z gita (best-effort,
None gdy brak gita / poza repo).
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from loguru import logger

from forensics.core.models import (
    ExperimentCaseResult,
    ExperimentSaveRequest,
    ExperimentSaveResult,
)

# backend/src/forensics/experiments.py -> backend/ -> MgrApp/
_BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
_REPO_ROOT = _BACKEND_ROOT.parent
_RESULTS_DIR = _REPO_ROOT / "results" / "experiments"


def _commit_hash() -> str | None:
    """Krotki hash HEAD z gita. None gdy git niedostepny lub poza repo."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        logger.warning("commit_hash niedostepny: {}", exc)
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _pct(v: float) -> str:
    return f"{round(v * 100)}%"


def _build_markdown(request: ExperimentSaveRequest, timestamp: str, commit: str | None) -> str:
    lines = [
        f"# Eksperyment {timestamp}",
        "",
        f"- commit: `{commit or 'n/a'}`",
        f"- cache_mode: `{request.cache_mode}`",
        "",
        "| Case | Address Recall | Heur. Precision | Heur. Recall | CEX Coverage "
        "| Węzły | Krawędzie | Alerty | Etykiety | Latency [s] |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in request.cases:
        if c.metrics is not None:
            m = c.metrics
            lines.append(
                f"| {c.case} | {_pct(m.address_recall)} | {_pct(m.heuristic_precision)} "
                f"| {_pct(m.heuristic_recall)} | {_pct(m.cex_coverage)} | {c.nodes} "
                f"| {c.edges} | {c.alerts} | {c.labels} | {m.latency_seconds:.2f} |"
            )
        else:
            lines.append(
                f"| {c.case} | — | — | — | — | — | — | — | — | {c.error or 'błąd'} |"
            )
    return "\n".join(lines) + "\n"


def _csv_cell(value: object) -> str:
    return "" if value is None else str(value)


def _build_csv(request: ExperimentSaveRequest) -> str:
    head = (
        "case,address,hops,start_block,end_block,cache_mode,address_recall,"
        "heuristic_precision,heuristic_recall,cex_coverage,nodes,edges,alerts,"
        "labels,latency_s,error"
    )
    rows = [head]
    for c in request.cases:
        m = c.metrics
        rows.append(
            ",".join(
                _csv_cell(x)
                for x in (
                    c.case,
                    c.address,
                    c.hops,
                    c.start_block,
                    c.end_block,
                    request.cache_mode,
                    m.address_recall if m else None,
                    m.heuristic_precision if m else None,
                    m.heuristic_recall if m else None,
                    m.cex_coverage if m else None,
                    c.nodes,
                    c.edges,
                    c.alerts,
                    c.labels,
                    m.latency_seconds if m else None,
                    c.error,
                )
            )
        )
    return "\n".join(rows) + "\n"


def _case_payload(c: ExperimentCaseResult) -> dict:
    return c.model_dump(mode="json")


def write_experiment(request: ExperimentSaveRequest) -> ExperimentSaveResult:
    """Zapisuje eksperyment jako json+md+csv do results/experiments/ z metadanymi."""
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    commit = _commit_hash()
    base = _RESULTS_DIR / f"{timestamp}__experiment"

    json_payload = {
        "timestamp": timestamp,
        "commit_hash": commit,
        "cache_mode": request.cache_mode,
        "cases": [_case_payload(c) for c in request.cases],
    }
    _atomic_write(
        base.with_suffix(".json"),
        json.dumps(json_payload, ensure_ascii=False, indent=2, default=str),
    )
    _atomic_write(base.with_suffix(".md"), _build_markdown(request, timestamp, commit))
    _atomic_write(base.with_suffix(".csv"), _build_csv(request))

    files = [base.with_suffix(suffix).name for suffix in (".json", ".md", ".csv")]
    logger.info("Eksperyment zapisany: {} ({} plikow)", base.name, len(files))
    return ExperimentSaveResult(
        timestamp=timestamp,
        commit_hash=commit,
        files=files,
        saved_dir=str(_RESULTS_DIR),
    )
