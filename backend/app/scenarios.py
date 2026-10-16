"""Loads seeded scenarios from data/scenarios/<dir>/{scenario,request,change,expected}.json.

Swapping in the organizer's assets is a data-only change: drop new folders in, same file names.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Scenario:
    id: str
    folder: str
    name: str
    seeded_condition: str
    organizer_expected_outcome: str
    data_note: str
    request: dict[str, Any]
    change: dict[str, Any]
    expected: dict[str, Any]
    document_text: str | None = None


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_scenarios(directory: Path) -> list[Scenario]:
    scenarios: list[Scenario] = []
    for folder in sorted(p for p in directory.iterdir() if p.is_dir()):
        meta = _read(folder / "scenario.json")
        form = folder / "authorization_form.txt"
        scenarios.append(
            Scenario(
                id=meta["id"],
                folder=folder.name,
                name=meta["name"],
                seeded_condition=meta["seeded_condition"],
                organizer_expected_outcome=meta["organizer_expected_outcome"],
                data_note=meta.get("data_note", "SYNTHETIC"),
                request=_read(folder / "request.json"),
                change=_read(folder / "change.json"),
                expected=_read(folder / "expected.json"),
                document_text=form.read_text(encoding="utf-8") if form.exists() else None,
            )
        )
    return scenarios
