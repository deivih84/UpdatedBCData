"""Validate a generated cats_data.json against Battle Cats unit CSV sources."""

from __future__ import annotations

# Both direct invocation and python -m work from any current directory.
import os as _workspace_os
import sys as _workspace_sys
from pathlib import Path as _WorkspacePath
if __package__ in (None, ''):
    _workspace_sys.path.insert(0, str(_WorkspacePath(__file__).resolve().parents[2]))
from workspace_paths import Workspace, latest_version_dir, run_generator
paths = Workspace.load(_workspace_os.environ.get('UPDATED_BCDATA_ROOT'))

import argparse
import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Mapping, Optional


UNIT_FILE_PATTERN = re.compile(r"unit(\d+)\.csv$")
REQUIRED_INFO_FIELDS = {
    "rarity",
    "name_basic",
    "names_evolved",
    "obtain_method",
}


def canonical_key(unit_id: int) -> str:
    return str(unit_id).zfill(3)


def parse_names(names_file: Path) -> Dict[int, dict]:
    names: Dict[int, dict] = {}
    with names_file.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            parts = [part.strip() for part in line.rstrip("\r\n").split("\t")]
            if len(parts) < 5:
                continue
            try:
                unit_id = int(parts[0])
            except ValueError:
                continue
            evolved_names = parts[3]
            evolved_count = len(
                [name for name in evolved_names.split("/") if name.strip()]
            )
            names[unit_id] = {
                "rarity": parts[1],
                "name_basic": parts[2],
                "names_evolved": evolved_names,
                "obtain_method": parts[4],
                "total_forms": 1 + evolved_count,
            }
    return names


def normalize_source_stats(unit_file: Path) -> List[list]:
    rows: List[list] = []
    with unit_file.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.reader(handle):
            normalized = []
            for cell in row:
                value = cell.split("//")[0].strip()
                if not value:
                    continue
                try:
                    normalized.append(float(value) if "." in value else int(value))
                except ValueError:
                    normalized.append(value)
            if normalized:
                rows.append(normalized)
    return rows


def source_units(data_local: Path) -> Dict[str, tuple[Path, List[list]]]:
    units: Dict[str, tuple[Path, List[list]]] = {}
    for unit_file in sorted(data_local.iterdir()):
        if not unit_file.is_file():
            continue
        match = UNIT_FILE_PATTERN.fullmatch(unit_file.name)
        if match is None:
            continue
        source_id = int(match.group(1))
        json_id = source_id - 1
        if json_id < 0:
            continue
        units[canonical_key(json_id)] = (
            unit_file,
            normalize_source_stats(unit_file),
        )
    return units


def validate(
    cats_json: Path,
    data_local: Path,
    names_file: Path,
    expected_version: str,
    required_min_forms: Optional[Mapping[int, int]] = None,
) -> List[str]:
    errors: List[str] = []
    try:
        data = json.loads(cats_json.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"cats_data.json cannot parse: {exc}"]

    if not isinstance(data, dict):
        return ["cats_data.json root must be an object"]

    metadata = data.get("metadata")
    units = data.get("units")
    if not isinstance(metadata, dict):
        errors.append("metadata must be an object")
        metadata = {}
    if not isinstance(units, dict):
        errors.append("units must be an object")
        units = {}

    actual_version = metadata.get("version")
    if str(actual_version) != expected_version:
        errors.append(
            f"metadata.version must be {expected_version!r}, got {actual_version!r}"
        )

    invalid_keys = sorted(
        str(key)
        for key in units
        if not str(key).isdigit() or canonical_key(int(str(key))) != str(key)
    )
    if invalid_keys:
        errors.append(f"invalid JSON unit keys: {', '.join(invalid_keys)}")

    numeric_ids = sorted(int(str(key)) for key in units if str(key).isdigit())
    expected_total = numeric_ids[-1] + 1 if numeric_ids else 0
    actual_total = metadata.get("total_units")
    if actual_total != expected_total:
        errors.append(
            f"metadata.total_units must be {expected_total}, got {actual_total}"
        )

    try:
        expected_units = source_units(data_local)
    except (OSError, UnicodeError, csv.Error) as exc:
        errors.append(f"source unit CSVs cannot parse: {exc}")
        return errors

    expected_keys = set(expected_units)
    actual_keys = {str(key) for key in units}
    missing = sorted(expected_keys - actual_keys, key=int)
    extra = sorted(actual_keys - expected_keys, key=lambda value: int(value) if value.isdigit() else value)
    if missing:
        errors.append(f"missing JSON units: {', '.join(missing)}")
    if extra:
        errors.append(f"extra JSON units: {', '.join(extra)}")

    try:
        names = parse_names(names_file)
    except (OSError, UnicodeError) as exc:
        errors.append(f"names.txt cannot parse: {exc}")
        return errors

    for key in sorted(expected_keys & actual_keys, key=int):
        unit = units[key]
        if not isinstance(unit, dict):
            errors.append(f"unit {key} must be an object")
            continue

        info = unit.get("info")
        if (
            not isinstance(info, dict)
            or not REQUIRED_INFO_FIELDS.issubset(info)
            or not str(info.get("rarity", "")).strip()
            or not str(info.get("name_basic", "")).strip()
        ):
            errors.append(f"unit {key} info is missing required fields")
        else:
            name_info = names.get(int(key))
            if name_info is not None:
                for field in REQUIRED_INFO_FIELDS:
                    if info.get(field) != name_info[field]:
                        errors.append(
                            f"unit {key} info.{field} differs from names.txt"
                        )

        stats = unit.get("stats")
        if not isinstance(stats, list) or not stats:
            errors.append(f"unit {key} stats must be a non-empty list")
            continue

        source_rows = expected_units[key][1]
        name_info = names.get(int(key))
        allowed_forms = name_info["total_forms"] if name_info is not None else 99
        expected_stats = source_rows[:allowed_forms]
        if stats != expected_stats:
            errors.append(
                f"unit {key} stats differ from source: "
                f"expected {len(expected_stats)} forms, got {len(stats)}"
            )

        for form_index, row in enumerate(stats, start=1):
            if (
                not isinstance(row, list)
                or not row
                or any(not isinstance(value, (int, float)) for value in row)
            ):
                errors.append(
                    f"unit {key} form {form_index} stats must be a non-empty numeric row"
                )

    for unit_id, minimum_forms in sorted((required_min_forms or {}).items()):
        key = canonical_key(unit_id)
        unit = units.get(key)
        if not isinstance(unit, dict):
            errors.append(f"required unit {key} is missing")
            continue
        stats = unit.get("stats")
        actual_forms = len(stats) if isinstance(stats, list) else 0
        if actual_forms < minimum_forms:
            errors.append(
                f"unit {key} requires at least {minimum_forms} forms, "
                f"got {actual_forms}"
            )

    return errors


def parse_required_unit(value: str) -> tuple[int, int]:
    try:
        unit_id, forms = value.split(":", maxsplit=1)
        parsed = (int(unit_id), int(forms))
    except (ValueError, TypeError) as exc:
        raise argparse.ArgumentTypeError("expected UNIT_ID:MIN_FORMS") from exc
    if parsed[0] < 0 or parsed[1] < 1:
        raise argparse.ArgumentTypeError("unit ID must be >= 0 and forms >= 1")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("cats_json", type=Path)
    parser.add_argument("data_local", type=Path)
    parser.add_argument("names_file", type=Path)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument(
        "--require-unit",
        action="append",
        default=[],
        type=parse_required_unit,
        metavar="UNIT_ID:MIN_FORMS",
    )
    args = parser.parse_args()
    errors = validate(
        args.cats_json,
        args.data_local,
        args.names_file,
        args.expected_version,
        required_min_forms=dict(args.require_unit),
    )
    if errors:
        print(json.dumps({"status": "blocked", "errors": errors}, indent=2))
        return 1
    print(json.dumps({"status": "ok", "errors": []}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
