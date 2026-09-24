"""Saved SAP system connection profiles -- everything needed to connect EXCEPT
the password, which is only ever supplied at run time and never written to disk.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

_STORE_PATH = Path(__file__).resolve().parent.parent / "config" / "systems.json"


def _load() -> dict[str, Any]:
    if not _STORE_PATH.exists():
        return {"systems": []}
    with open(_STORE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _save(data: dict[str, Any]) -> None:
    with open(_STORE_PATH, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)


def list_systems() -> list[dict[str, Any]]:
    return _load()["systems"]


def get_system(key: str) -> dict[str, Any] | None:
    return next((s for s in list_systems() if s["key"] == key), None)


def add_system(profile: dict[str, Any]) -> dict[str, Any]:
    data = _load()
    profile = dict(profile)
    profile["key"] = uuid.uuid4().hex[:12]
    profile.pop("passwd", None)  # defensive: never persist a password even if one slips in
    odata = profile.get("odata")
    if isinstance(odata, dict):
        odata.pop("passwd", None)
    data["systems"].append(profile)
    _save(data)
    return profile


def update_system(key: str, profile: dict[str, Any]) -> dict[str, Any] | None:
    data = _load()
    idx = next((i for i, s in enumerate(data["systems"]) if s["key"] == key), None)
    if idx is None:
        return None
    updated = dict(profile)
    updated["key"] = key
    updated.pop("passwd", None)
    odata = updated.get("odata")
    if isinstance(odata, dict):
        odata.pop("passwd", None)
    data["systems"][idx] = updated
    _save(data)
    return updated


def delete_system(key: str) -> bool:
    data = _load()
    before = len(data["systems"])
    data["systems"] = [s for s in data["systems"] if s["key"] != key]
    _save(data)
    return len(data["systems"]) < before
