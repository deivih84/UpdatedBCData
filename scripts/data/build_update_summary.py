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
import json
import shutil
from pathlib import Path

from scripts.data.update_summary_core import (
    already_published,
    build_fact_sections,
    choose_game_version,
    load_json_file,
    make_blocked_report,
    next_revision,
    sha256_file,
    summary_filename,
    utcish_now_string,
    validate_manifest,
    validate_summary,
)


DEFAULT_UPDATED_BCDATA = Path(str(paths.root))


def read_optional_json(path: Path) -> dict:
    if not path.exists():
        return {}
    return load_json_file(path)


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_sources(root: Path) -> tuple[dict, dict, dict, dict, dict[str, str]]:
    files = {
        "cats_data.json": root / "cats_data.json",
        "stages_data.json": root / "stages_data.json",
        "enemies_data.json": root / "enemies_data.json",
        "data_version.json": root / "data_version.json",
    }
    source_hashes = {
        name: sha256_file(path)
        for name, path in files.items()
        if path.exists()
    }
    return (
        load_json_file(files["cats_data.json"]),
        load_json_file(files["stages_data.json"]),
        load_json_file(files["enemies_data.json"]),
        read_optional_json(files["data_version.json"]),
        source_hashes,
    )


def build_summary(args: argparse.Namespace) -> int:
    root = Path(args.updated_bcdata)
    summaries_root = root / "update_summaries"
    manifest_path = summaries_root / "manifest.json"
    region_dir = summaries_root / args.region
    draft_dir = summaries_root / "_draft"
    blocked_dir = summaries_root / "_blocked"

    source_hashes: dict[str, str] = {}
    version: str | None = None
    try:
        cats, stages, enemies, data_version, source_hashes = load_sources(root)
        version = choose_game_version(args.game_version, data_version, cats)
        if version is None:
            raise ValueError("Required version metadata is missing")

        manifest = read_optional_json(manifest_path)
        if manifest:
            manifest_errors = validate_manifest(manifest)
            if manifest_errors:
                raise ValueError("; ".join(manifest_errors))

        if already_published(manifest, args.region, version, source_hashes):
            print(f"No-op: {args.region} {version} with identical hashes is already published.")
            return 0

        previous = {}
        if args.previous_snapshot:
            previous_root = Path(args.previous_snapshot)
            previous = {
                "cats": read_optional_json(previous_root / "cats_data.json"),
                "stages": read_optional_json(previous_root / "stages_data.json"),
                "enemies": read_optional_json(previous_root / "enemies_data.json"),
                "data_version": read_optional_json(previous_root / "data_version.json"),
            }

        current = {
            "cats": cats,
            "stages": stages,
            "enemies": enemies,
            "data_version": data_version,
        }
        sections = build_fact_sections(previous, current)
        if not sections:
            raise ValueError("No meaningful data change exists")

        existing_names = [path.name for path in region_dir.glob(f"{version}*.json")]
        revision = next_revision(existing_names, version)
        output_name = summary_filename(version, revision)
        summary = {
            "schemaVersion": 1,
            "gameVersion": version,
            "region": args.region,
            "status": "published" if args.publish else "draft",
            "revision": revision,
            "generatedAt": utcish_now_string(),
            "needsHumanReview": bool(args.ai_draft),
            "sourceHashes": source_hashes,
            "sections": sections,
            "reviewNotes": [],
        }
        if args.ai_draft:
            summary["copy"] = {
                "source": "ai_draft",
                "headline": f"Battle Cats {version} update",
                "shortIntro": f"Version {version} brings newly detected cats, enemies, stages, or rewards.",
            }

        errors = validate_summary(summary)
        if errors:
            raise ValueError("; ".join(errors))

        draft_stamp = utcish_now_string().replace(":", "").replace(" ", "-")
        draft_path = draft_dir / f"{args.region}-{version}-{draft_stamp}.json"
        write_json(draft_path, summary)
        print(f"Draft written: {draft_path}")

        if args.publish:
            final_path = region_dir / output_name
            shutil.copyfile(draft_path, final_path)
            manifest.setdefault("schemaVersion", 1)
            manifest["lastUpdate"] = utcish_now_string()
            manifest.setdefault("regions", {})
            manifest["regions"][args.region] = {
                "gameVersion": version,
                "summaryPath": f"update_summaries/{args.region}/{output_name}",
                "buttonImageUrl": f"images/update_buttons/{args.region}_{version.replace('.', '_')}.png",
                "status": "published",
                "sourceHashes": source_hashes,
            }
            manifest_errors = validate_manifest(manifest)
            if manifest_errors:
                final_path.unlink(missing_ok=True)
                raise ValueError("; ".join(manifest_errors))
            write_json(manifest_path, manifest)
            print(f"Published: {final_path}")
            print(f"Manifest updated: {manifest_path}")
        return 0
    except Exception as exc:
        report = make_blocked_report(args.region, version, [str(exc)], source_hashes)
        report_stamp = utcish_now_string().replace(":", "").replace(" ", "-")
        report_name = f"{args.region}-{version or 'unknown'}-{report_stamp}-report.json"
        report_path = blocked_dir / report_name
        write_json(report_path, report)
        print(f"Blocked report written: {report_path}")
        print(f"Error: {exc}")
        return 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate BattleStats update summaries.")
    parser.add_argument("--region", choices=["en", "jp"], required=True)
    parser.add_argument("--ai-draft", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--updated-bcdata", default=str(DEFAULT_UPDATED_BCDATA))
    parser.add_argument("--previous-snapshot", default="")
    parser.add_argument("--game-version", default="")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(build_summary(parse_args()))
