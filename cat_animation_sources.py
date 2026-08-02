"""Inspect Battle Cats install bundles and decrypt animation resources."""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Optional, Sequence
import zipfile

from tbcml import core

from cat_animation_sync import parse_resource_name


PACKAGE_REGIONS = {
    "jp.co.ponos.battlecats": "jp",
    "jp.co.ponos.battlecatsen": "en",
    "jp.co.ponos.battlecatskr": "kr",
    "jp.co.ponos.battlecatstw": "tw",
}
COUNTRY_CODES = {
    "jp": core.CountryCode.JP,
    "en": core.CountryCode.EN,
    "kr": core.CountryCode.KR,
    "tw": core.CountryCode.TW,
}
REQUIRED_PACKS = ("ImageDataLocal", "NumberLocal")


class SourceInspectionError(RuntimeError):
    pass


@dataclass(frozen=True)
class PackageIdentity:
    package_name: str
    region: str
    version: tuple[int, int, int]


@dataclass(frozen=True, order=True)
class SourcePackage:
    version: tuple[int, int, int]
    region: str
    path: Path = field(compare=False)
    install_pack_member: Optional[str] = field(compare=False)
    base_apk_member: Optional[str] = field(compare=False)

    @property
    def version_text(self) -> str:
        return ".".join(map(str, self.version))

    @property
    def key(self) -> tuple[str, str]:
        return self.region, self.version_text


def parse_badging(output: str) -> PackageIdentity:
    package_match = re.search(r"package: name='([^']+)'", output)
    version_match = re.search(r"versionName='([^']+)'", output)
    if package_match is None or version_match is None:
        raise SourceInspectionError("aapt output is missing package or version")
    package_name = package_match.group(1)
    if package_name not in PACKAGE_REGIONS:
        raise SourceInspectionError(
            f"Unsupported Battle Cats package: {package_name}"
        )
    version_text = version_match.group(1)
    parts = version_text.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        raise SourceInspectionError(
            f"Unsupported dotted game version: {version_text}"
        )
    return PackageIdentity(
        package_name=package_name,
        region=PACKAGE_REGIONS[package_name],
        version=tuple(int(part) for part in parts),
    )


def _version_tuple(text: str) -> tuple[int, ...]:
    return tuple(int(part) if part.isdigit() else 0 for part in text.split("."))


def find_aapt(explicit: Optional[Path] = None) -> Path:
    candidates: list[Path] = []
    if explicit is not None:
        candidates.append(explicit)
    for variable in ("ANDROID_HOME", "ANDROID_SDK_ROOT"):
        value = os.environ.get(variable)
        if value:
            candidates.extend(
                Path(value).glob("build-tools/*/aapt.exe")
            )
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        candidates.extend(
            Path(local_app_data).glob(
                "Android/Sdk/build-tools/*/aapt.exe"
            )
        )
    existing = [path for path in candidates if path.is_file()]
    if not existing:
        raise SourceInspectionError("Could not locate Android aapt.exe")
    return max(existing, key=lambda path: _version_tuple(path.parent.name))


def _read_badging(apk_path: Path, aapt_path: Path) -> PackageIdentity:
    result = subprocess.run(
        [str(aapt_path), "dump", "badging", str(apk_path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if result.returncode != 0:
        raise SourceInspectionError(
            f"aapt failed for {apk_path.name}: {result.stderr.strip()}"
        )
    return parse_badging(result.stdout)


def _validate_install_pack_bytes(data: bytes, label: str) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as install_pack:
            names = set(install_pack.namelist())
    except zipfile.BadZipFile as error:
        raise SourceInspectionError(f"Invalid install APK: {label}") from error
    missing = [
        f"assets/{pack}.{extension}"
        for pack in REQUIRED_PACKS
        for extension in ("list", "pack")
        if f"assets/{pack}.{extension}" not in names
    ]
    if missing:
        raise SourceInspectionError(
            f"{label} is missing required packs: {', '.join(missing)}"
        )


def inspect_source(
    path: Path, aapt_path: Optional[Path] = None
) -> SourcePackage:
    """Inspect package identity and locate the split that owns local packs."""

    path = path.resolve()
    if not path.is_file():
        raise SourceInspectionError(f"Source does not exist: {path}")
    aapt = find_aapt(aapt_path)

    if path.suffix.lower() == ".apk":
        identity = _read_badging(path, aapt)
        _validate_install_pack_bytes(path.read_bytes(), path.name)
        return SourcePackage(
            version=identity.version,
            region=identity.region,
            path=path,
            install_pack_member=None,
            base_apk_member=None,
        )

    if path.suffix.lower() not in {".xapk", ".apks"}:
        raise SourceInspectionError(f"Unsupported source type: {path.suffix}")

    try:
        with zipfile.ZipFile(path) as outer:
            members = outer.namelist()
            install_member = next(
                (
                    name
                    for name in members
                    if Path(name).name.lower() == "installpack.apk"
                ),
                None,
            )
            if install_member is None:
                raise SourceInspectionError(
                    f"{path.name} does not contain InstallPack.apk"
                )
            _validate_install_pack_bytes(
                outer.read(install_member), f"{path.name}!{install_member}"
            )
            base_candidates = [
                name
                for name in members
                if name.lower().endswith(".apk")
                and name != install_member
                and not Path(name).name.lower().startswith("config.")
            ]
            with tempfile.TemporaryDirectory() as temporary:
                temporary_root = Path(temporary)
                failures: list[str] = []
                for index, member in enumerate(base_candidates):
                    candidate = temporary_root / f"base-{index}.apk"
                    candidate.write_bytes(outer.read(member))
                    try:
                        identity = _read_badging(candidate, aapt)
                    except SourceInspectionError as error:
                        failures.append(str(error))
                        continue
                    return SourcePackage(
                        version=identity.version,
                        region=identity.region,
                        path=path,
                        install_pack_member=install_member,
                        base_apk_member=member,
                    )
    except zipfile.BadZipFile as error:
        raise SourceInspectionError(f"Invalid archive: {path}") from error
    raise SourceInspectionError(
        f"No supported Battle Cats base APK in {path.name}"
    )


def discover_sources(bcdata: Path, region: str) -> list[SourcePackage]:
    sources: list[SourcePackage] = []
    for path in sorted(bcdata.iterdir()):
        if path.suffix.lower() not in {".apk", ".xapk", ".apks"}:
            continue
        try:
            source = inspect_source(path)
        except SourceInspectionError:
            continue
        if source.region == region:
            sources.append(source)
    return sorted(sources)


def select_pending_sources(
    sources: Sequence[SourcePackage],
    applied: set[tuple[str, str]],
    desired_version: tuple[int, int, int],
    force: bool,
) -> list[SourcePackage]:
    selected = [
        source
        for source in sources
        if source.version <= desired_version
        and (force or source.key not in applied)
    ]
    return sorted(selected)


def _install_pack_bytes(source: SourcePackage) -> bytes:
    if source.install_pack_member is None:
        return source.path.read_bytes()
    try:
        with zipfile.ZipFile(source.path) as outer:
            return outer.read(source.install_pack_member)
    except (zipfile.BadZipFile, KeyError) as error:
        raise SourceInspectionError(
            f"Cannot read {source.install_pack_member} from {source.path.name}"
        ) from error


def decrypt_animation_resources(source: SourcePackage) -> dict[str, bytes]:
    """Decrypt exact cat-animation resources from the two local packs."""

    key = (
        core.Hash(core.HashAlgorithm.MD5)
        .get_hash(core.Data("pack"), 8)
        .to_hex()
    )
    country_code = COUNTRY_CODES[source.region]
    game_version = core.GameVersion.from_string(source.version_text)
    resources: dict[str, bytes] = {}
    install_bytes = _install_pack_bytes(source)
    try:
        install_pack = zipfile.ZipFile(io.BytesIO(install_bytes))
    except zipfile.BadZipFile as error:
        raise SourceInspectionError(
            f"Invalid InstallPack.apk in {source.path.name}"
        ) from error
    with install_pack:
        for pack_name in REQUIRED_PACKS:
            try:
                encrypted_list = core.Data(
                    install_pack.read(f"assets/{pack_name}.list")
                )
                encrypted_pack = core.Data(
                    install_pack.read(f"assets/{pack_name}.pack")
                )
            except KeyError as error:
                raise SourceInspectionError(
                    f"{source.path.name} is missing {pack_name}"
                ) from error
            list_data = core.AesCipher(key.encode("utf-8")).decrypt(
                encrypted_list
            )
            table = core.CSV(list_data)
            header = table.read_line()
            if header is None:
                raise SourceInspectionError(f"Empty {pack_name}.list")
            try:
                total = int(header[0])
            except (ValueError, IndexError) as error:
                raise SourceInspectionError(
                    f"Invalid {pack_name}.list header"
                ) from error
            for _ in range(total):
                row = table.read_line()
                if row is None or len(row) < 3:
                    raise SourceInspectionError(
                        f"Truncated {pack_name}.list in {source.path.name}"
                    )
                raw_name = row[0]
                parsed = parse_resource_name(raw_name)
                if parsed is None:
                    continue
                try:
                    start, size = int(row[1]), int(row[2])
                except ValueError as error:
                    raise SourceInspectionError(
                        f"Invalid offset for {raw_name}"
                    ) from error
                game_file = core.GameFile.from_enc_data(
                    encrypted_pack[start : start + size],
                    raw_name,
                    pack_name,
                    country_code,
                    game_version,
                )
                data = game_file.dec_data.to_bytes()
                previous = resources.get(parsed.canonical_name)
                if previous is not None and previous != data:
                    raise SourceInspectionError(
                        "Conflicting resources have the same canonical name: "
                        f"{parsed.canonical_name}"
                    )
                resources[parsed.canonical_name] = data
    return resources
