"""Pure helpers for merging and validating Battle Cats animation archives."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import re
import struct
from typing import Mapping, Optional, Tuple
import zipfile


FORM_ORDER = ("f", "c", "s", "u")
RESOURCE_RE = re.compile(
    r"^(?P<id>\d+)_(?P<form>[fcsu])(?P<tail>"
    r"\.(?:png|imgcut|mamodel)|(?:\d+|_[A-Za-z]+\d*)\.maanim)$",
    re.IGNORECASE,
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class ResourceName:
    unit_id: int
    form: str
    canonical_name: str
    archive_path: str


@dataclass(frozen=True)
class MergeResult:
    entries: dict[str, bytes]
    added: int
    replaced: int
    unchanged: int
    preserved: int


@dataclass(frozen=True)
class ArchiveValidation:
    forms: Tuple[str, ...]
    errors: Tuple[str, ...]


def parse_resource_name(name: str) -> Optional[ResourceName]:
    """Parse an exact unit-animation resource name and normalize its ID."""

    match = RESOURCE_RE.fullmatch(name)
    if match is None:
        return None
    unit_id = int(match.group("id"))
    form = match.group("form").lower()
    canonical = f"{unit_id}_{form}{match.group('tail')}"
    return ResourceName(
        unit_id=unit_id,
        form=form,
        canonical_name=canonical,
        archive_path=f"{unit_id}/{form}/{canonical}",
    )


def merge_entries(
    existing: Mapping[str, bytes], incoming: Mapping[str, bytes]
) -> MergeResult:
    """Overlay incremental resources without dropping absent older entries."""

    entries = dict(existing)
    added = 0
    replaced = 0
    unchanged = 0
    for name, data in incoming.items():
        previous = existing.get(name)
        if previous is None:
            added += 1
        elif previous == data:
            unchanged += 1
        else:
            replaced += 1
        entries[name] = data
    preserved = len(set(existing) - set(incoming))
    return MergeResult(entries, added, replaced, unchanged, preserved)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_deterministic_zip(unit_id: int, entries: Mapping[str, bytes]) -> bytes:
    """Build a byte-stable archive with normalized paths and timestamps."""

    output = io.BytesIO()
    with zipfile.ZipFile(
        output, "w", zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for canonical_name in sorted(entries):
            parsed = parse_resource_name(canonical_name)
            if parsed is None or parsed.unit_id != unit_id:
                raise ValueError(f"Unsafe animation entry: {canonical_name}")
            info = zipfile.ZipInfo(
                parsed.archive_path, (1980, 1, 1, 0, 0, 0)
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, entries[canonical_name])
    return output.getvalue()


def _png_error(name: str, data: bytes) -> Optional[str]:
    if not data.startswith(PNG_SIGNATURE):
        return f"{name}: invalid PNG signature"
    if len(data) < 24 or data[12:16] != b"IHDR":
        return f"{name}: missing PNG IHDR"
    width, height = struct.unpack(">II", data[16:24])
    if width < 1 or height < 1:
        return f"{name}: invalid PNG dimensions {width}x{height}"
    return None


def validate_archive(
    unit_id: int, entries: Mapping[str, bytes]
) -> ArchiveValidation:
    """Validate every form that is actually stored for one unit."""

    errors: list[str] = []
    forms: set[str] = set()
    parsed_entries: dict[str, ResourceName] = {}

    for name, data in entries.items():
        parsed = parse_resource_name(name)
        if parsed is None:
            errors.append(f"Unsafe or unknown animation entry: {name}")
            continue
        parsed_entries[name] = parsed
        forms.add(parsed.form)
        if parsed.unit_id != unit_id:
            errors.append(
                f"{name}: belongs to unit {parsed.unit_id}, expected {unit_id}"
            )
        if not data:
            errors.append(f"{name}: empty resource")
            continue
        if name.endswith(".png"):
            error = _png_error(name, data)
            if error is not None:
                errors.append(error)
        else:
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                errors.append(f"{name}: resource is not valid UTF-8")

    for form in sorted(forms, key=FORM_ORDER.index):
        prefix = f"{unit_id}_{form}"
        for extension in (".png", ".imgcut", ".mamodel"):
            required = f"{prefix}{extension}"
            if required not in parsed_entries:
                errors.append(f"Form {form} is missing {required}")
        animations = [
            name
            for name, parsed in parsed_entries.items()
            if parsed.unit_id == unit_id
            and parsed.form == form
            and name.endswith(".maanim")
        ]
        if not animations:
            errors.append(f"Form {form} is missing a {prefix}*.maanim resource")

    return ArchiveValidation(
        forms=tuple(sorted(forms, key=FORM_ORDER.index)),
        errors=tuple(errors),
    )
