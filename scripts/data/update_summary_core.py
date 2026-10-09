from __future__ import annotations

# Both direct invocation and python -m work from any current directory.
import os as _workspace_os
import sys as _workspace_sys
from pathlib import Path as _WorkspacePath
if __package__ in (None, ''):
    _workspace_sys.path.insert(0, str(_WorkspacePath(__file__).resolve().parents[2]))
from workspace_paths import Workspace, latest_version_dir, run_generator
paths = Workspace.load(_workspace_os.environ.get('UPDATED_BCDATA_ROOT'))

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


HASH_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def utcish_now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def load_json_file(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _require_string(errors: list[str], obj: dict[str, Any], key: str, label: str) -> None:
    if not isinstance(obj.get(key), str) or not obj.get(key):
        errors.append(f"{label} is required")


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if manifest.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1")
    _require_string(errors, manifest, "lastUpdate", "lastUpdate")
    regions = manifest.get("regions")
    if not isinstance(regions, dict):
        errors.append("regions is required")
        return errors

    for region, entry in regions.items():
        if region not in {"en", "jp"}:
            errors.append(f"regions.{region} is not supported")
            continue
        if not isinstance(entry, dict):
            errors.append(f"regions.{region} must be an object")
            continue
        status = entry.get("status")
        if status not in {"draft", "blocked", "published"}:
            errors.append(f"regions.{region}.status must be draft, blocked, or published")
        if status == "published":
            _require_string(errors, entry, "gameVersion", f"regions.{region}.gameVersion")
            _require_string(errors, entry, "summaryPath", f"regions.{region}.summaryPath")
        if "buttonImageUrl" in entry and not isinstance(entry["buttonImageUrl"], str):
            errors.append(f"regions.{region}.buttonImageUrl must be a string")
    return errors


def validate_summary(summary: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if summary.get("schemaVersion") != 1:
        errors.append("schemaVersion must be 1")
    for key in ["gameVersion", "region", "status", "generatedAt"]:
        _require_string(errors, summary, key, key)
    if summary.get("region") not in {"en", "jp", "shared"}:
        errors.append("region must be en, jp, or shared")
    if summary.get("status") not in {"draft", "blocked", "published"}:
        errors.append("status must be draft, blocked, or published")
    if not isinstance(summary.get("revision"), int) or summary.get("revision", 0) < 1:
        errors.append("revision must be a positive integer")

    source_hashes = summary.get("sourceHashes")
    if not isinstance(source_hashes, dict) or not source_hashes:
        errors.append("sourceHashes is required")
    else:
        for name, value in source_hashes.items():
            if not isinstance(name, str) or not isinstance(value, str) or not HASH_RE.match(value):
                errors.append(f"sourceHashes.{name} must be a sha256 hash")

    sections = summary.get("sections")
    if not isinstance(sections, list):
        errors.append("sections must be a list")
    else:
        for index, section in enumerate(sections):
            if not isinstance(section, dict):
                errors.append(f"sections[{index}] must be an object")
                continue
            _require_string(errors, section, "type", f"sections[{index}].type")
            _require_string(errors, section, "title", f"sections[{index}].title")
            if not isinstance(section.get("items"), list):
                errors.append(f"sections[{index}].items must be a list")

    copy = summary.get("copy")
    if isinstance(copy, dict) and copy.get("source") == "ai_draft" and summary.get("needsHumanReview") is not True:
        errors.append("AI copy requires needsHumanReview=true")
    if not isinstance(summary.get("reviewNotes", []), list):
        errors.append("reviewNotes must be a list")
    return errors


def published_regions(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    regions = manifest.get("regions")
    if not isinstance(regions, dict):
        return {}
    return {
        region: entry
        for region, entry in regions.items()
        if isinstance(entry, dict)
        and region in {"en", "jp"}
        and entry.get("status") == "published"
        and isinstance(entry.get("gameVersion"), str)
        and isinstance(entry.get("summaryPath"), str)
    }


def summary_filename(version: str, revision: int) -> str:
    if revision <= 1:
        return f"{version}.json"
    return f"{version}-r{revision}.json"


def next_revision(existing_names: list[str], version: str) -> int:
    revision = 1
    base = f"{version}.json"
    if base in existing_names:
        revision = 2
    pattern = re.compile(rf"^{re.escape(version)}-r(\d+)\.json$")
    for name in existing_names:
        match = pattern.match(name)
        if match:
            revision = max(revision, int(match.group(1)) + 1)
    return revision


def already_published(
    manifest: dict[str, Any],
    region: str,
    version: str,
    source_hashes: dict[str, str],
) -> bool:
    regions = manifest.get("regions")
    entry = regions.get(region) if isinstance(regions, dict) else None
    return (
        isinstance(entry, dict)
        and entry.get("status") == "published"
        and entry.get("gameVersion") == version
        and entry.get("sourceHashes") == source_hashes
    )


def make_blocked_report(
    region: str,
    version: str | None,
    errors: list[str],
    source_hashes: dict[str, str],
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "status": "blocked",
        "region": region,
        "detectedVersion": version,
        "generatedAt": utcish_now_string(),
        "errors": errors,
        "sourceHashes": source_hashes,
        "suggestedNextAction": "Fix the failed source data or validation errors, then rerun build_update_summary.py.",
    }


RARITY_LABELS = {
    "N": "Normal",
    "EX": "Special",
    "R": "Rare",
    "SR": "Super Rare",
    "UR": "Uber Rare",
    "LR": "Legend Rare",
}


def detect_game_version(data_version: dict[str, Any], cats_data: dict[str, Any]) -> str | None:
    value = data_version.get("gameVersion")
    if value:
        return str(value)
    metadata = cats_data.get("metadata")
    if isinstance(metadata, dict) and metadata.get("version") is not None:
        return str(metadata["version"])
    return None


def choose_game_version(override: str, data_version: dict[str, Any], cats_data: dict[str, Any]) -> str | None:
    if override.strip():
        return override.strip()
    return detect_game_version(data_version, cats_data)


def _cat_units(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    units = data.get("units")
    return units if isinstance(units, dict) else {}


def _enemy_map(data: dict[str, Any]) -> dict[int, dict[str, Any]]:
    raw = data.get("enemies")
    if isinstance(raw, dict):
        iterable = raw.values()
    elif isinstance(raw, list):
        iterable = raw
    else:
        iterable = []
    result: dict[int, dict[str, Any]] = {}
    for enemy in iterable:
        if isinstance(enemy, dict) and isinstance(enemy.get("id"), int):
            result[enemy["id"]] = enemy
    return result


def _subchapter_map(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    chapters = data.get("chapters")
    for chapter in chapters if isinstance(chapters, list) else []:
        if not isinstance(chapter, dict):
            continue
        chapter_id = str(chapter.get("id", ""))
        chapter_name = str(chapter.get("name", chapter_id))
        subchapters = chapter.get("subChapters")
        for sub in subchapters if isinstance(subchapters, list) else []:
            if not isinstance(sub, dict):
                continue
            sub_id = str(sub.get("id", ""))
            stages = sub.get("stages")
            result[f"{chapter_id}/{sub_id}"] = {
                "chapterId": chapter_id,
                "chapter": chapter_name,
                "subChapterId": sub_id,
                "subChapter": str(sub.get("name", sub_id)),
                "stageCount": len(stages) if isinstance(stages, list) else 0,
            }
    return result


def build_fact_sections(previous: dict[str, dict], current: dict[str, dict]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []

    previous_units = _cat_units(previous.get("cats", {}))
    current_units = _cat_units(current.get("cats", {}))
    new_cat_items = []
    for cat_id in sorted(set(current_units) - set(previous_units), key=lambda value: int(value) if value.isdigit() else value):
        info = current_units.get(cat_id, {}).get("info", {})
        if not isinstance(info, dict):
            info = {}
        rarity = str(info.get("rarity", ""))
        names = [str(info.get("name_basic", "")).strip()]
        evolved = str(info.get("names_evolved", "")).strip()
        if evolved:
            names.extend([name.strip() for name in evolved.split("|") if name.strip()])
        new_cat_items.append({
            "catId": int(cat_id) if str(cat_id).isdigit() else cat_id,
            "name": names[0] if names and names[0] else f"Cat #{cat_id}",
            "rarity": RARITY_LABELS.get(rarity, rarity),
            "forms": [name for name in names if name],
        })
    if new_cat_items:
        sections.append({"type": "new_cats", "title": "New Cats", "items": new_cat_items})

    previous_enemies = _enemy_map(previous.get("enemies", {}))
    current_enemies = _enemy_map(current.get("enemies", {}))
    new_enemy_items = []
    for enemy_id in sorted(set(current_enemies) - set(previous_enemies)):
        enemy = current_enemies[enemy_id]
        new_enemy_items.append({
            "enemyId": enemy_id,
            "name": str(enemy.get("name", f"Enemy #{enemy_id}")),
            "traits": enemy.get("traits", []) if isinstance(enemy.get("traits"), list) else [],
        })
    if new_enemy_items:
        sections.append({"type": "new_enemies", "title": "New Enemies", "items": new_enemy_items})

    previous_subs = _subchapter_map(previous.get("stages", {}))
    current_subs = _subchapter_map(current.get("stages", {}))
    new_sub_items = [current_subs[key] for key in sorted(set(current_subs) - set(previous_subs))]
    if new_sub_items:
        sections.append({"type": "new_subchapters", "title": "New Stage Maps", "items": new_sub_items})

    return sections
