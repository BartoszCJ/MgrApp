"""Spojnosc presetow frontendu z ground truth.

Adres startowy presetu (frontend/src/app/page.tsx) MUSI byc jednym z attacker_root
z backend/data/ground_truth/<case>.json. Inaczej BFS startuje ze zlego miejsca i
address_recall jest artefaktem (bug Eulera: preset spoza ground truth -> 0% recall).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_BACKEND_ROOT = Path(__file__).resolve().parent.parent  # backend/
_REPO_ROOT = _BACKEND_ROOT.parent
_PAGE_TSX = _REPO_ROOT / "frontend" / "src" / "app" / "page.tsx"
_GROUND_TRUTH = _BACKEND_ROOT / "data" / "ground_truth"

# Para key + nastepujacy po nim address w bloku presetu.
_PRESET_RE = re.compile(
    r'key:\s*"(?P<key>[^"]+)".*?address:\s*"(?P<addr>0x[0-9a-fA-F]{40})"',
    re.DOTALL,
)


def _preset_addresses() -> dict[str, str]:
    text = _PAGE_TSX.read_text(encoding="utf-8")
    out: dict[str, str] = {}
    for match in _PRESET_RE.finditer(text):
        out.setdefault(match.group("key"), match.group("addr").lower())
    return out


def _attacker_roots(case: str) -> set[str]:
    data = json.loads((_GROUND_TRUTH / f"{case}.json").read_text(encoding="utf-8"))
    roots = data.get("addresses", {}).get("attacker_root", [])
    return {e["address"].lower() for e in roots if "address" in e}


@pytest.mark.parametrize("case", ["ronin", "euler", "nomad"])
def test_preset_seed_matches_ground_truth_attacker_root(case: str) -> None:
    presets = _preset_addresses()
    assert case in presets, f"Brak presetu '{case}' w page.tsx"

    seed = presets[case]
    roots = _attacker_roots(case)
    assert roots, f"Brak attacker_root w ground_truth/{case}.json"
    assert seed in roots, (
        f"Preset '{case}' uzywa seed {seed}, ktory NIE jest attacker_root "
        f"w ground_truth/{case}.json (dozwolone: {sorted(roots)})"
    )
