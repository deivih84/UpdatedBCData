"""Synchronize Battle Cats animation archives from verified game packages."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile
from typing import Callable, Mapping, Optional, Sequence
import zipfile

from cat_animation_sources import (
    SourcePackage,
    decrypt_animation_resources,
    discover_sources,
    inspect_source,
    select_pending_sources,
)
from cat_animation_sync import (
    FORM_ORDER,
    build_deterministic_zip,
    parse_resource_name,
    sha256_hex,
    validate_archive,
)


class SourceSelectionError(RuntimeError):
    """Raised when the data version cannot be backed by an install package."""


class AnimationValidationError(RuntimeError):
    """Raised when an input or generated animation archive is invalid."""


class TransactionError(RuntimeError):
    """Raised when publishing failed and the original tree was restored."""


@dataclass(frozen=True)
class AppliedSource:
    region: str
    game_version: str

    @property
    def key(self) -> tuple[str, str]:
        return self.region, self.game_version


@dataclass(frozen=True)
class ArchiveRecord:
    sha256: str
    size: int


@dataclass(frozen=True)
class SyncConfig:
    bcdata: Path
    cats_dir: Path
    cats_data: Path
    data_version: Path
    sources: tuple[Path, ...] = ()
    region: str = "jp"
    force: bool = False
    dry_run: bool = False


@dataclass(frozen=True)
class UpdateReport:
    selected_sources: tuple[AppliedSource, ...]
    added_resources: int
    replaced_resources: int
    unchanged_resources: int
    preserved_resources: int
    created_archives: tuple[int, ...]
    modified_archives: tuple[int, ...]
    preexisting_form_warnings: Mapping[int, tuple[str, ...]]
    new_form_warnings: Mapping[int, tuple[str, ...]]
    revision: str
    changed_paths: tuple[Path, ...]


@dataclass(frozen=True)
class UpdatePlan:
    config: SyncConfig
    archive_outputs: Mapping[int, bytes]
    manifest: Mapping[str, object]
    manifest_bytes: bytes
    data_version_bytes: bytes
    report: UpdateReport


def serialize_json(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _version_tuple(text: str) -> tuple[int, int, int]:
    parts = text.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise SourceSelectionError(f"Invalid game version: {text}")
    return tuple(int(part) for part in parts)  # type: ignore[return-value]


def _latest_version(bcdata: Path, region: str) -> str:
    latest_path = bcdata / "latest.txt"
    try:
        lines = latest_path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise SourceSelectionError(f"Cannot read {latest_path}") from error
    for line in lines:
        value = line.strip()
        if value.lower().endswith(region.lower()):
            version = value[: -len(region)]
            _version_tuple(version)
            return version
    raise SourceSelectionError(
        f"latest.txt does not declare a version for region {region}"
    )


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise AnimationValidationError(f"Cannot read JSON: {path}") from error
    if not isinstance(value, dict):
        raise AnimationValidationError(f"Expected a JSON object: {path}")
    return value


def _read_archive(path: Path, unit_id: int) -> dict[str, bytes]:
    entries: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                if member.is_dir():
                    continue
                member_path = PurePosixPath(member.filename)
                parsed = parse_resource_name(member_path.name)
                if (
                    parsed is None
                    or parsed.unit_id != unit_id
                    or member_path.as_posix() != parsed.archive_path
                ):
                    raise AnimationValidationError(
                        f"Unsafe entry in {path.name}: {member.filename}"
                    )
                if parsed.canonical_name in entries:
                    raise AnimationValidationError(
                        f"Duplicate entry in {path.name}: {parsed.canonical_name}"
                    )
                entries[parsed.canonical_name] = archive.read(member)
    except (OSError, zipfile.BadZipFile) as error:
        raise AnimationValidationError(f"Invalid archive: {path}") from error
    result = validate_archive(unit_id, entries)
    if result.errors:
        raise AnimationValidationError(
            f"{path.name}: " + "; ".join(result.errors)
        )
    return entries


def _load_manifest(path: Path) -> dict:
    if not path.is_file():
        return {}
    return _read_json(path)


def _applied_sources(manifest: Mapping[str, object]) -> list[AppliedSource]:
    output: list[AppliedSource] = []
    raw_sources = manifest.get("appliedSources", [])
    if not isinstance(raw_sources, list):
        return output
    for raw in raw_sources:
        if not isinstance(raw, dict):
            continue
        region = raw.get("region")
        version = raw.get("gameVersion")
        if isinstance(region, str) and isinstance(version, str):
            output.append(AppliedSource(region, version))
    return output


def _form_warnings(
    units: Mapping[str, object], archives: Mapping[int, Mapping[str, bytes]]
) -> dict[int, tuple[str, ...]]:
    warnings: dict[int, tuple[str, ...]] = {}
    for raw_id, raw_unit in units.items():
        try:
            unit_id = int(raw_id)
        except (TypeError, ValueError) as error:
            raise AnimationValidationError(
                f"Invalid unit ID in cats_data.json: {raw_id}"
            ) from error
        if not isinstance(raw_unit, dict):
            raise AnimationValidationError(f"Invalid unit record: {raw_id}")
        stats = raw_unit.get("stats", [])
        declared_count = len(stats) if isinstance(stats, list) else 0
        expected = FORM_ORDER[: min(declared_count, len(FORM_ORDER))]
        actual = {
            parsed.form
            for name in archives[unit_id]
            for parsed in [parse_resource_name(name)]
            if parsed is not None
        }
        missing = tuple(form for form in expected if form not in actual)
        if missing:
            warnings[unit_id] = missing
    return warnings


def build_manifest(
    records: Mapping[int, ArchiveRecord],
    sources: Sequence[AppliedSource],
    warnings: Mapping[int, Sequence[str]],
) -> dict:
    digest_input = "\n".join(
        f"{unit_id}:{records[unit_id].sha256}:{records[unit_id].size}"
        for unit_id in sorted(records)
    ).encode("utf-8")
    revision = "sha256:" + hashlib.sha256(digest_input).hexdigest()
    applied = [
        {"region": source.region, "gameVersion": source.game_version}
        for source in sources
    ]
    latest = applied[-1] if applied else None
    return {
        "schemaVersion": 1,
        "revision": revision,
        "latestSource": latest,
        "appliedSources": applied,
        "archives": {
            str(unit_id): {
                "sha256": records[unit_id].sha256,
                "size": records[unit_id].size,
            }
            for unit_id in sorted(records)
        },
        "declaredFormWarnings": {
            str(unit_id): list(warnings[unit_id])
            for unit_id in sorted(warnings)
        },
    }


def _inspect_requested_sources(
    config: SyncConfig,
    inspector: Callable[[Path], SourcePackage],
    discovery: Callable[[Path, str], Sequence[SourcePackage]],
) -> list[SourcePackage]:
    if config.sources:
        sources = [inspector(path) for path in config.sources]
    else:
        sources = list(discovery(config.bcdata, config.region))
    wrong_regions = [source for source in sources if source.region != config.region]
    if wrong_regions:
        details = ", ".join(
            f"{source.path.name}={source.region}" for source in wrong_regions
        )
        raise SourceSelectionError(
            f"Expected region {config.region}, found {details}"
        )
    unique: dict[tuple[str, str], SourcePackage] = {}
    for source in sources:
        previous = unique.get(source.key)
        if previous is not None and previous.path != source.path:
            raise SourceSelectionError(
                f"Multiple packages claim {source.region} {source.version_text}"
            )
        unique[source.key] = source
    return sorted(unique.values())


def plan_update(
    config: SyncConfig,
    *,
    inspector: Callable[[Path], SourcePackage] = inspect_source,
    discovery: Callable[[Path, str], Sequence[SourcePackage]] = discover_sources,
    decryptor: Callable[[SourcePackage], Mapping[str, bytes]] = decrypt_animation_resources,
) -> UpdatePlan:
    cats_data = _read_json(config.cats_data)
    metadata = cats_data.get("metadata")
    units = cats_data.get("units")
    if not isinstance(metadata, dict) or not isinstance(units, dict):
        raise AnimationValidationError(
            "cats_data.json must contain metadata and units objects"
        )
    desired_text = metadata.get("version")
    if not isinstance(desired_text, str):
        raise AnimationValidationError("cats_data metadata.version is missing")
    desired_version = _version_tuple(desired_text)
    latest_text = _latest_version(config.bcdata, config.region)
    if latest_text != desired_text:
        raise SourceSelectionError(
            f"cats_data version {desired_text} does not match "
            f"latest.txt {config.region} version {latest_text}"
        )

    manifest_path = config.cats_dir / "manifest.json"
    old_manifest = _load_manifest(manifest_path)
    applied = _applied_sources(old_manifest)
    applied_keys = {source.key for source in applied}
    available = _inspect_requested_sources(config, inspector, discovery)
    selected = select_pending_sources(
        available, applied_keys, desired_version, config.force
    )
    desired_key = (config.region, desired_text)
    if desired_key not in applied_keys and not any(
        source.key == desired_key for source in available
    ):
        raise SourceSelectionError(
            f"No verified {config.region} source matches data version {desired_text}"
        )

    current_bytes: dict[int, bytes] = {}
    archives: dict[int, dict[str, bytes]] = {}
    for path in sorted(config.cats_dir.glob("*.zip")):
        if not path.stem.isdigit():
            continue
        unit_id = int(path.stem)
        if unit_id in archives:
            raise AnimationValidationError(
                f"Duplicate numeric archive ID: {unit_id}"
            )
        current_bytes[unit_id] = path.read_bytes()
        archives[unit_id] = _read_archive(path, unit_id)

    original_names = {
        (unit_id, name) for unit_id, entries in archives.items() for name in entries
    }
    incoming_names: set[tuple[int, str]] = set()
    added = replaced = unchanged = 0
    changed_units: set[int] = set()
    for source in selected:
        incoming = decryptor(source)
        for name in sorted(incoming):
            parsed = parse_resource_name(name)
            if parsed is None or parsed.canonical_name != name:
                raise AnimationValidationError(
                    f"Decryptor returned an invalid resource name: {name}"
                )
            incoming_names.add((parsed.unit_id, name))
            entries = archives.setdefault(parsed.unit_id, {})
            previous = entries.get(name)
            if previous is None:
                added += 1
                changed_units.add(parsed.unit_id)
            elif previous == incoming[name]:
                unchanged += 1
            else:
                replaced += 1
                changed_units.add(parsed.unit_id)
            entries[name] = incoming[name]

    archive_outputs: dict[int, bytes] = {}
    for unit_id in sorted(changed_units):
        validation = validate_archive(unit_id, archives[unit_id])
        if validation.errors:
            raise AnimationValidationError(
                f"Generated {unit_id}.zip is invalid: "
                + "; ".join(validation.errors)
            )
        archive_outputs[unit_id] = build_deterministic_zip(
            unit_id, archives[unit_id]
        )

    declared_ids: set[int] = set()
    for raw_id in units:
        try:
            unit_id = int(raw_id)
        except (TypeError, ValueError) as error:
            raise AnimationValidationError(
                f"Invalid unit ID in cats_data.json: {raw_id}"
            ) from error
        declared_ids.add(unit_id)
        if unit_id not in archives:
            raise AnimationValidationError(
                f"No animation archive exists for declared unit {unit_id}"
            )

    warnings = _form_warnings(units, archives)
    previous_warnings: dict[int, tuple[str, ...]] = {}
    raw_previous_warnings = old_manifest.get("declaredFormWarnings", {})
    if isinstance(raw_previous_warnings, dict):
        for raw_id, raw_forms in raw_previous_warnings.items():
            if str(raw_id).isdigit() and isinstance(raw_forms, list):
                previous_warnings[int(raw_id)] = tuple(
                    form for form in raw_forms if isinstance(form, str)
                )
    preexisting_warnings = {
        unit_id: forms
        for unit_id, forms in warnings.items()
        if previous_warnings.get(unit_id) == forms
    }
    new_warnings = {
        unit_id: forms
        for unit_id, forms in warnings.items()
        if previous_warnings.get(unit_id) != forms
    }

    all_sources = list(applied)
    known_source_keys = {source.key for source in all_sources}
    selected_records: list[AppliedSource] = []
    for source in selected:
        record = AppliedSource(source.region, source.version_text)
        selected_records.append(record)
        if record.key not in known_source_keys:
            all_sources.append(record)
            known_source_keys.add(record.key)
    all_sources.sort(key=lambda source: (_version_tuple(source.game_version), source.region))

    records: dict[int, ArchiveRecord] = {}
    for unit_id in sorted(archives):
        data = archive_outputs.get(unit_id, current_bytes.get(unit_id))
        if data is None:
            raise AnimationValidationError(
                f"Could not build archive bytes for unit {unit_id}"
            )
        records[unit_id] = ArchiveRecord(sha256_hex(data), len(data))
    manifest = build_manifest(records, all_sources, warnings)
    manifest_bytes = serialize_json(manifest)

    data_version = _read_json(config.data_version)
    latest_source = manifest.get("latestSource")
    if not isinstance(latest_source, dict):
        raise SourceSelectionError(
            f"No applied source reaches data version {desired_text}"
        )
    if latest_source.get("gameVersion") != desired_text:
        raise SourceSelectionError(
            f"Latest applied source {latest_source.get('gameVersion')} does not "
            f"reach data version {desired_text}"
        )
    data_version["animations"] = {
        "manifest": "cats/manifest.json",
        "revision": manifest["revision"],
        "sourceRegion": latest_source["region"],
        "sourceGameVersion": latest_source["gameVersion"],
    }
    data_version_bytes = serialize_json(data_version)

    changed_paths: list[Path] = []
    for unit_id in sorted(archive_outputs):
        destination = config.cats_dir / f"{unit_id}.zip"
        if not destination.is_file() or destination.read_bytes() != archive_outputs[unit_id]:
            changed_paths.append(destination)
    if not manifest_path.is_file() or manifest_path.read_bytes() != manifest_bytes:
        changed_paths.append(manifest_path)
    if (
        not config.data_version.is_file()
        or config.data_version.read_bytes() != data_version_bytes
    ):
        changed_paths.append(config.data_version)

    created = tuple(
        unit_id for unit_id in sorted(archive_outputs) if unit_id not in current_bytes
    )
    modified = tuple(
        unit_id for unit_id in sorted(archive_outputs) if unit_id in current_bytes
    )
    report = UpdateReport(
        selected_sources=tuple(selected_records),
        added_resources=added,
        replaced_resources=replaced,
        unchanged_resources=unchanged,
        preserved_resources=len(original_names - incoming_names),
        created_archives=created,
        modified_archives=modified,
        preexisting_form_warnings=preexisting_warnings,
        new_form_warnings=new_warnings,
        revision=str(manifest["revision"]),
        changed_paths=tuple(changed_paths),
    )
    return UpdatePlan(
        config=config,
        archive_outputs=archive_outputs,
        manifest=manifest,
        manifest_bytes=manifest_bytes,
        data_version_bytes=data_version_bytes,
        report=report,
    )


def apply_update(
    plan: UpdatePlan,
    *,
    replace_file: Callable[[Path, Path], None] = os.replace,
) -> UpdateReport:
    if plan.config.dry_run or not plan.report.changed_paths:
        return plan.report

    destination_data: dict[Path, bytes] = {
        plan.config.cats_dir / f"{unit_id}.zip": data
        for unit_id, data in plan.archive_outputs.items()
    }
    destination_data[plan.config.cats_dir / "manifest.json"] = plan.manifest_bytes
    destination_data[plan.config.data_version] = plan.data_version_bytes
    destinations = [
        path for path in plan.report.changed_paths if path in destination_data
    ]
    plan.config.cats_dir.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="cat-animation-update-", dir=plan.config.cats_dir.parent
    ) as temporary:
        stage = Path(temporary)
        staged: dict[Path, Path] = {}
        backups: dict[Path, Optional[Path]] = {}
        for index, destination in enumerate(destinations):
            staged_path = stage / "new" / f"{index}.tmp"
            staged_path.parent.mkdir(parents=True, exist_ok=True)
            staged_path.write_bytes(destination_data[destination])
            staged[destination] = staged_path
            if destination.exists():
                backup = stage / "backup" / f"{index}.bak"
                backup.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(destination, backup)
                backups[destination] = backup
            else:
                backups[destination] = None

        published: list[Path] = []
        try:
            for destination in destinations:
                destination.parent.mkdir(parents=True, exist_ok=True)
                replace_file(staged[destination], destination)
                published.append(destination)
        except Exception as error:
            restore_errors: list[str] = []
            for destination in reversed(published):
                backup = backups[destination]
                try:
                    if backup is None:
                        if destination.exists():
                            destination.unlink()
                    else:
                        os.replace(backup, destination)
                except OSError as restore_error:
                    restore_errors.append(f"{destination}: {restore_error}")
            detail = f"Cat animation update failed: {error}"
            if restore_errors:
                detail += "; rollback errors: " + "; ".join(restore_errors)
            raise TransactionError(detail) from error
    return plan.report


def _default_paths() -> tuple[Path, Path]:
    repository = Path(__file__).resolve().parent
    return repository, repository.parent / "BCData"


def _parser() -> argparse.ArgumentParser:
    repository, bcdata = _default_paths()
    parser = argparse.ArgumentParser(
        description="Extract and transactionally update Battle Cats animations"
    )
    parser.add_argument("--bcdata", type=Path, default=bcdata)
    parser.add_argument("--cats-dir", type=Path, default=repository / "cats")
    parser.add_argument("--cats-data", type=Path, default=repository / "cats_data.json")
    parser.add_argument("--data-version", type=Path, default=repository / "data_version.json")
    parser.add_argument("--source", action="append", type=Path, default=[])
    parser.add_argument("--region", choices=("jp", "en", "kr", "tw"), default="jp")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _print_report(report: UpdateReport, dry_run: bool) -> None:
    mode = "DRY RUN" if dry_run else "APPLIED"
    print(f"[{mode}] animation revision {report.revision}")
    if report.selected_sources:
        print(
            "Sources: "
            + ", ".join(
                f"{source.region} {source.game_version}"
                for source in report.selected_sources
            )
        )
    else:
        print("Sources: no pending packages")
    print(
        "Resources: "
        f"+{report.added_resources}, ~{report.replaced_resources}, "
        f"={report.unchanged_resources}, preserved={report.preserved_resources}"
    )
    print(
        f"Archives: created={list(report.created_archives)}, "
        f"modified={list(report.modified_archives)}"
    )
    print(f"Changed paths: {len(report.changed_paths)}")
    if report.new_form_warnings:
        print(f"New declared-form warnings: {dict(report.new_form_warnings)}")


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    config = SyncConfig(
        bcdata=args.bcdata,
        cats_dir=args.cats_dir,
        cats_data=args.cats_data,
        data_version=args.data_version,
        sources=tuple(args.source),
        region=args.region,
        force=args.force,
        dry_run=args.dry_run,
    )
    try:
        plan = plan_update(config)
        report = apply_update(plan)
    except (SourceSelectionError, AnimationValidationError, TransactionError) as error:
        print(f"ERROR: {error}")
        return 1
    _print_report(report, config.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
