#!/usr/bin/env python3
"""
Resolve Battle Cats sale.tsv event IDs from a local BCData dump.

Ponos sale.tsv rows only contain numeric pack IDs. The app data contains many
of the human names in local CSV/TSV resources, so this module builds a small
read-only index from the latest EN BCData version folder.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional


SCRIPT_DIR = Path(__file__).parent

DEFAULT_MANUAL_NAMES = {
    102: "EoC/ItF/CotC Half Energy Cost",
    15082: "13th Anniversary",
    18007: "Wildcat Slots",
}

INCLUDED_CALENDAR_SOURCES = {
    "Manual",
    "All_day_event",
    "DailyLoginEventText",
    "GamatotoEvent",
}


@dataclass(frozen=True)
class EventNameHit:
    event_id: int
    name: str
    source: str
    priority: int


def _version_key(path: Path):
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)en$", path.name)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def discover_bcdata_root() -> Optional[Path]:
    env_root = os.environ.get("BCDATA_DIR")
    candidates = []
    if env_root:
        candidates.append(Path(env_root))
    candidates.extend([
        SCRIPT_DIR.parent / "BCData",
        Path.home() / "Documents" / "GitHub" / "BCData",
    ])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def discover_bcdata_version_dir(root: Path) -> Optional[Path]:
    candidates = []
    for child in root.iterdir() if root.exists() else []:
        if not child.is_dir():
            continue
        key = _version_key(child)
        if key is not None:
            candidates.append((key, child))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return candidates[0][1]


def _clean_name(value: str) -> str:
    value = value.split("\t", 1)[0]
    value = re.sub(r"<br\s*/?>", " ", value, flags=re.IGNORECASE)
    value = value.replace("%@", "").replace("%d", "")
    value = re.sub(r"\s+", " ", value)
    return value.strip(" \ufeff")


def _iter_text_lines(path: Path) -> Iterable[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8-sig", errors="replace").splitlines()


class BCEventNameResolver:
    def __init__(self, bcdata_path: Optional[Path] = None, manual_names: Optional[Dict[int, str]] = None):
        self.manual_names = dict(DEFAULT_MANUAL_NAMES)
        if manual_names:
            self.manual_names.update({int(k): v for k, v in manual_names.items()})

        self.version_dir = self._resolve_version_dir(bcdata_path)
        self.by_id: Dict[int, List[EventNameHit]] = {}
        self.available = self.version_dir is not None

        self._load_manual_names()
        if self.version_dir:
            self._load_all_day_events()
            self._load_pipe_csv("Map_Name.csv", source="Map_Name", priority=30)
            self._load_pipe_csv("Mission_Name.csv", source="Mission_Name", priority=60)
            self._load_daily_login_texts()
            self._load_gamatoto_events()

    def _resolve_version_dir(self, bcdata_path: Optional[Path]) -> Optional[Path]:
        root = Path(bcdata_path) if bcdata_path else discover_bcdata_root()
        if not root:
            return None
        if (root / "resLocal").exists() or (root / "DataLocal").exists():
            return root
        return discover_bcdata_version_dir(root)

    @property
    def res_dir(self) -> Path:
        return self.version_dir / "resLocal"

    @property
    def data_dir(self) -> Path:
        return self.version_dir / "DataLocal"

    def _add_hit(self, event_id: int, name: str, source: str, priority: int):
        name = _clean_name(name)
        if not name or name == "@":
            return
        hit = EventNameHit(int(event_id), name, source, priority)
        self.by_id.setdefault(hit.event_id, []).append(hit)

    def _load_manual_names(self):
        for event_id, name in self.manual_names.items():
            self._add_hit(event_id, name, "Manual", 0)

    def _load_all_day_events(self):
        path = self.res_dir / "All_day_event.tsv"
        for line in _iter_text_lines(path):
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            try:
                event_id = int(parts[1])
            except ValueError:
                continue
            self._add_hit(event_id, parts[0], "All_day_event", 10)

    def _load_pipe_csv(self, filename: str, source: str, priority: int):
        path = self.res_dir / filename
        for line in _iter_text_lines(path):
            if "|" not in line:
                continue
            id_part, name = line.split("|", 1)
            try:
                event_id = int(id_part)
            except ValueError:
                continue
            self._add_hit(event_id, name.split("|", 1)[0], source, priority)

    def _load_daily_login_texts(self):
        pattern = re.compile(r"DailyLoginEventText_(\d+)_en\.tsv$", re.IGNORECASE)
        for path in self.res_dir.glob("DailyLoginEventText_*_en.tsv"):
            match = pattern.match(path.name)
            if not match:
                continue
            event_id = int(match.group(1))
            lines = [line for line in _iter_text_lines(path) if line.strip()]
            if not lines:
                continue
            name = re.split(r"<br\s*/?>", lines[0], maxsplit=1, flags=re.IGNORECASE)[0]
            self._add_hit(event_id, name, "DailyLoginEventText", 20)

    def _load_gamatoto_events(self):
        names_path = self.res_dir / "GamatotoExpedition_Stage_nameEvent_en.csv"
        data_path = self.data_dir / "GamatotoExpedition_Stage_EVENT.csv"
        names = []
        for line in _iter_text_lines(names_path):
            names.append(_clean_name(line.split("|", 1)[0]))

        event_ids = []
        for line in _iter_text_lines(data_path):
            data_part = line.split("//", 1)[0].strip().rstrip(",")
            if not data_part:
                continue
            parts = [part.strip() for part in data_part.split(",")]
            if len(parts) < 7:
                continue
            try:
                event_ids.append(int(parts[6]))
            except ValueError:
                continue

        if len(names) > len(event_ids):
            names = names[-len(event_ids):]

        for event_id, name in zip(event_ids, names):
            self._add_hit(event_id, name, "GamatotoEvent", 25)

    def hits(self, event_id: int) -> List[EventNameHit]:
        return sorted(self.by_id.get(int(event_id), []), key=lambda hit: (hit.priority, hit.source, hit.name))

    def best_hit(self, event_id: int) -> Optional[EventNameHit]:
        hits = self.hits(event_id)
        return hits[0] if hits else None

    def best_name(self, event_id: int) -> Optional[str]:
        hit = self.best_hit(event_id)
        return hit.name if hit else None

    def is_calendar_hit(self, hit: EventNameHit) -> bool:
        return hit.source in INCLUDED_CALENDAR_SOURCES
