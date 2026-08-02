# Battle Cats Animation Update Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and run a repeatable animation synchronizer that merges new or changed PONOS cat resources into `UpdatedBCData/cats`, publishes a deterministic hash manifest, integrates with the normal update orchestrator, and makes Battle Stats refresh stale cached ZIPs safely.

**Architecture:** Keep PONOS source inspection/decryption separate from pure archive merge/validation logic. Apply incremental APK sources in semantic-version order, stage and validate every output before an atomic backup-and-replace transaction, then let the Android loader compare cached ZIP hashes against the remote manifest while preserving offline fallback behavior.

**Tech Stack:** Python 3.9, standard-library `unittest`/`zipfile`/`hashlib`, `tbcml`, Android Kotlin 2.3.10, kotlinx serialization, OkHttp, JUnit 4, Gradle.

## Global Constraints

- Preserve unrelated dirty changes in BCData and CatStats; UpdatedBCData starts implementation from the clean post-design commit `f33cf05`.
- Do not run `git pull`, push, archive upload, or automated publication.
- Do not rebuild all cat ZIPs from one XAPK; PONOS installation packs are incremental.
- Apply JP 15.5.0 before JP 15.5.1 for the first managed synchronization.
- Preserve existing ZIP entries absent from incoming sources; replace only byte-different resources.
- Canonicalize leading-zero PONOS IDs, for example `076_u.png` to `76/u/76_u.png`.
- Accept only forms `f`, `c`, `s`, and `u`, and reject unrelated lookalike resources.
- Do not rewrite byte-identical archives or a byte-identical manifest.
- Stage and validate all outputs before replacing destinations; restore already replaced destinations if any replacement fails.
- Never delete a usable Android cache entry before a verified replacement has downloaded and parsed.
- A future data update is incomplete if its game version is newer than the animation manifest source and no matching install package is available.
- Resolve the desired animation version from `cats_data.json.metadata.version` and require the JP line of `BCData/latest.txt` to agree; do not rely on `data_version.json.gameVersion`, which the orchestrator updates after its steps finish.
- The synchronizer itself never commits or publishes.

---

### Task 1: Pure resource naming, ZIP merge, and form validation

**Files:**
- Create: `cat_animation_sync.py`
- Create: `tests/test_cat_animation_sync.py`

**Interfaces:**
- Consumes: canonical or raw PONOS resource names and `dict[str, bytes]` archive entries.
- Produces: `parse_resource_name(name: str) -> ResourceName | None`, `merge_entries(existing: Mapping[str, bytes], incoming: Mapping[str, bytes]) -> MergeResult`, `validate_archive(unit_id: int, entries: Mapping[str, bytes]) -> ArchiveValidation`, and `build_deterministic_zip(unit_id: int, entries: Mapping[str, bytes]) -> bytes`.

- [ ] **Step 1: Write failing tests for exact filtering and ID normalization**

```python
VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

def complete_form_entries(unit_id: int, form: str) -> dict[str, bytes]:
    prefix = f"{unit_id}_{form}"
    return {
        f"{prefix}.png": VALID_PNG,
        f"{prefix}.imgcut": b"[imgcut]\n1\n0,0,1,1\n",
        f"{prefix}.mamodel": b"[modelanim:model]\n3\n0\n",
        f"{prefix}00.maanim": b"[modelanim:animation]\n1\n0\n",
    }

class ResourceNameTests(unittest.TestCase):
    def test_accepts_unit_assets_and_removes_leading_zeroes(self):
        parsed = parse_resource_name("076_u02.maanim")
        self.assertEqual(parsed.unit_id, 76)
        self.assertEqual(parsed.form, "u")
        self.assertEqual(parsed.canonical_name, "76_u02.maanim")
        self.assertEqual(parsed.archive_path, "76/u/76_u02.maanim")

    def test_rejects_non_unit_lookalikes(self):
        for name in ("000_stamp_f.png", "006_charaawa.maanim", "455_x.png"):
            self.assertIsNone(parse_resource_name(name), name)
```

- [ ] **Step 2: Run the focused tests and confirm RED**

Run: `python -m unittest tests.test_cat_animation_sync.ResourceNameTests -v`

Expected: import failure because `cat_animation_sync.py` does not exist.

- [ ] **Step 3: Implement the exact parser and immutable result types**

```python
FORM_CHARS = frozenset("fcsu")
RESOURCE_RE = re.compile(
    r"^(?P<id>\d+)_(?P<form>[fcsu])(?P<tail>"
    r"\.(?:png|imgcut|mamodel)|(?:\d+|_[A-Za-z]+\d*)\.maanim)$",
    re.IGNORECASE,
)

@dataclass(frozen=True)
class ResourceName:
    unit_id: int
    form: str
    canonical_name: str
    archive_path: str

@dataclass(frozen=True)
class ArchiveValidation:
    forms: tuple[str, ...]
    errors: tuple[str, ...]

def parse_resource_name(name: str) -> ResourceName | None:
    match = RESOURCE_RE.fullmatch(name)
    if match is None:
        return None
    unit_id = int(match.group("id"))
    form = match.group("form").lower()
    canonical = f"{unit_id}_{form}{match.group('tail')}"
    return ResourceName(unit_id, form, canonical, f"{unit_id}/{form}/{canonical}")
```

- [ ] **Step 4: Add failing merge and deterministic-ZIP tests**

```python
def test_merge_adds_replaces_preserves_and_counts(self):
    result = merge_entries(
        {"1_f.png": b"old", "1_f00.maanim": b"keep"},
        {"1_f.png": b"new", "1_f.imgcut": b"cut"},
    )
    self.assertEqual(result.entries["1_f.png"], b"new")
    self.assertEqual(result.entries["1_f00.maanim"], b"keep")
    self.assertEqual((result.added, result.replaced, result.preserved), (1, 1, 1))

def test_deterministic_zip_is_byte_identical(self):
    entries = complete_form_entries(1, "f")
    self.assertEqual(
        build_deterministic_zip(1, entries),
        build_deterministic_zip(1, dict(reversed(list(entries.items())))),
    )
```

- [ ] **Step 5: Run the new tests and confirm RED**

Run: `python -m unittest tests.test_cat_animation_sync -v`

Expected: failures naming `merge_entries` and `build_deterministic_zip`.

- [ ] **Step 6: Implement merge, deterministic ZIP generation, and SHA-256 helpers**

```python
@dataclass(frozen=True)
class MergeResult:
    entries: dict[str, bytes]
    added: int
    replaced: int
    unchanged: int
    preserved: int

def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def build_deterministic_zip(unit_id: int, entries: Mapping[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for canonical_name in sorted(entries):
            parsed = parse_resource_name(canonical_name)
            if parsed is None or parsed.unit_id != unit_id:
                raise ValueError(f"Unsafe animation entry: {canonical_name}")
            info = zipfile.ZipInfo(parsed.archive_path, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, entries[canonical_name])
    return output.getvalue()
```

Implement `merge_entries` by comparing exact bytes and counting added,
replaced, unchanged incoming, and preserved existing entries. It must return a
new dictionary and never mutate either input.

- [ ] **Step 7: Add failing archive-validation tests**

```python
def test_present_form_requires_core_files_and_animation(self):
    entries = complete_form_entries(455, "s")
    entries.pop("455_s.png")
    result = validate_archive(455, entries)
    self.assertIn("455_s.png", result.errors[0])

def test_png_signature_and_utf8_text_are_checked(self):
    entries = complete_form_entries(455, "s")
    entries["455_s.png"] = b"not-png"
    entries["455_s.mamodel"] = b"\xff"
    self.assertEqual(len(validate_archive(455, entries).errors), 2)
```

- [ ] **Step 8: Implement validation and run the complete focused suite GREEN**

`validate_archive` must reject unsafe paths, mismatched IDs, zero-byte files,
invalid PNG signature/IHDR data, non-UTF-8 model/animation text, and a present
form lacking `.png`, `.imgcut`, `.mamodel`, or any `.maanim`.

Run: `python -m unittest tests.test_cat_animation_sync -v`

Expected: all Task 1 tests pass with no warnings.

- [ ] **Step 9: Commit Task 1**

```powershell
git add cat_animation_sync.py tests/test_cat_animation_sync.py
git commit -m "feat: add deterministic cat animation archive core"
```

---

### Task 2: Installation-package inspection and real pack decryption

**Files:**
- Create: `cat_animation_sources.py`
- Create: `tests/test_cat_animation_sources.py`

**Interfaces:**
- Consumes: APK/XAPK/APKS paths, `aapt dump badging` output, and `tbcml` pack data.
- Produces: `SourcePackage`, `inspect_source(path: Path, aapt_path: Path | None = None) -> SourcePackage`, `discover_sources(bcdata: Path, region: str) -> list[SourcePackage]`, `select_pending_sources(sources: Sequence[SourcePackage], applied: set[tuple[str, str]], desired_version: tuple[int, int, int], force: bool) -> list[SourcePackage]`, and `decrypt_animation_resources(source: SourcePackage) -> dict[str, bytes]`.

- [ ] **Step 1: Write failing metadata and ordering tests**

```python
def source(version: str) -> SourcePackage:
    parsed = tuple(int(part) for part in version.split("."))
    return SourcePackage(
        version=parsed,
        region="jp",
        path=Path(f"jp-{version}.xapk"),
        install_pack_member="InstallPack.apk",
        base_apk_member="jp.co.ponos.battlecats.apk",
    )

def test_badging_parser_maps_jp_package_and_dotted_version(self):
    source = parse_badging(
        "package: name='jp.co.ponos.battlecats' versionCode='1505010' "
        "versionName='15.5.1'"
    )
    self.assertEqual((source.region, source.version), ("jp", (15, 5, 1)))

def test_pending_sources_are_semantically_sorted(self):
    selected = select_pending_sources(
        [source("15.5.1"), source("15.5.0"), source("15.4.1")],
        applied={("jp", "15.4.1")},
        desired_version=(15, 5, 1),
        force=False,
    )
    self.assertEqual([item.version_text for item in selected], ["15.5.0", "15.5.1"])
```

- [ ] **Step 2: Run tests and confirm RED**

Run: `python -m unittest tests.test_cat_animation_sources -v`

Expected: import failure because `cat_animation_sources.py` does not exist.

- [ ] **Step 3: Implement source identity, aapt discovery, and semantic ordering**

```python
PACKAGE_REGIONS = {
    "jp.co.ponos.battlecats": "jp",
    "jp.co.ponos.battlecatsen": "en",
    "jp.co.ponos.battlecatskr": "kr",
    "jp.co.ponos.battlecatstw": "tw",
}

class SourceInspectionError(RuntimeError):
    pass

@dataclass(frozen=True, order=True)
class SourcePackage:
    version: tuple[int, int, int]
    region: str
    path: Path = field(compare=False)
    install_pack_member: str | None = field(compare=False)
    base_apk_member: str | None = field(compare=False)

    @property
    def version_text(self) -> str:
        return ".".join(map(str, self.version))

@dataclass(frozen=True)
class PackageIdentity:
    package_name: str
    region: str
    version: tuple[int, int, int]

def parse_badging(output: str) -> PackageIdentity:
    package_name = re.search(r"package: name='([^']+)'", output).group(1)
    version_text = re.search(r"versionName='([^']+)'", output).group(1)
    if package_name not in PACKAGE_REGIONS:
        raise SourceInspectionError(f"Unsupported Battle Cats package: {package_name}")
    return PackageIdentity(
        package_name=package_name,
        region=PACKAGE_REGIONS[package_name],
        version=tuple(int(part) for part in version_text.split(".")),
    )
```

`find_aapt` must check an explicit path, `ANDROID_HOME`/`ANDROID_SDK_ROOT`, and
`%LOCALAPPDATA%/Android/Sdk/build-tools/*/aapt.exe`, choosing the highest
semantic build-tools directory. `inspect_source` must extract only the base APK
to `TemporaryDirectory`, run `aapt dump badging`, verify a package in
`PACKAGE_REGIONS`, and require `InstallPack.apk` or a direct APK containing both
`assets/ImageDataLocal.*` and `assets/NumberLocal.*`.

- [ ] **Step 4: Write a failing real pack round-trip test**

Build a synthetic `ImageDataLocal` and `NumberLocal` using tbcml's real
`PackFile.to_pack_list_file`, embed them in a synthetic `InstallPack.apk`, and
assert:

```python
VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

def write_pack(apk: zipfile.ZipFile, pack_name: str, files: dict[str, bytes]) -> None:
    pack = core.PackFile(pack_name, core.CountryCode.JP, core.GameVersion.from_string("15.5.1"))
    for name, data in files.items():
        pack.set_file(name, core.Data(data))
    _, pack_data, list_data = pack.to_pack_list_file()
    apk.writestr(f"assets/{pack_name}.pack", pack_data.to_bytes())
    apk.writestr(f"assets/{pack_name}.list", list_data.to_bytes())

install_pack = io.BytesIO()
with zipfile.ZipFile(install_pack, "w") as apk:
    write_pack(apk, "ImageDataLocal", {
        "076_u02.maanim": b"animation-data",
        "000_stamp_f.imgcut": b"not-a-unit",
    })
    write_pack(apk, "NumberLocal", {"076_u.png": VALID_PNG})
outer_path = self.temp_dir / "synthetic.xapk"
with zipfile.ZipFile(outer_path, "w") as outer:
    outer.writestr("InstallPack.apk", install_pack.getvalue())
synthetic_source = SourcePackage(
    version=(15, 5, 1), region="jp", path=outer_path,
    install_pack_member="InstallPack.apk", base_apk_member="base.apk",
)
resources = decrypt_animation_resources(synthetic_source)
self.assertEqual(resources["76_u02.maanim"], b"animation-data")
self.assertEqual(resources["76_u.png"], VALID_PNG)
self.assertNotIn("000_stamp_f.png", resources)
```

- [ ] **Step 5: Run the round-trip test and confirm RED**

Run: `python -m unittest tests.test_cat_animation_sources.PackDecryptionTests -v`

Expected: failure because `decrypt_animation_resources` is undefined.

- [ ] **Step 6: Implement decryption with tbcml and exact filtering**

For each required pack, decrypt its `.list` with the established MD5 `pack`
list key, slice encrypted bytes by list offsets, and call:

```python
game_file = core.GameFile.from_enc_data(
    encrypted_pack[start:start + size],
    raw_name,
    pack_name,
    country_code,
    core.GameVersion.from_string(source.version_text),
)
```

Pass every raw name through `parse_resource_name`; store decrypted bytes by
canonical name and reject two raw resources that canonicalize to the same name
with different bytes inside one source.

- [ ] **Step 7: Run source tests GREEN and smoke-inspect the real packages**

```powershell
python -m unittest tests.test_cat_animation_sources -v
python -c "from pathlib import Path; from cat_animation_sources import inspect_source; print(inspect_source(Path(r'C:\Users\forex\Documents\GitHub\BCData\15-5-0.xapk'))); print(inspect_source(Path(r'C:\Users\forex\Documents\GitHub\BCData\jp.co.ponos.battlecats_15.5.1.xapk')))"
```

Expected: tests pass; inspection reports JP `15.5.0` then JP `15.5.1`.

- [ ] **Step 8: Commit Task 2**

```powershell
git add cat_animation_sources.py tests/test_cat_animation_sources.py
git commit -m "feat: inspect and decrypt Battle Cats animation sources"
```

---

### Task 3: Manifest planning, transactional apply, CLI, and reports

**Files:**
- Modify: `cat_animation_sync.py`
- Create: `update_cat_animations.py`
- Create: `tests/test_update_cat_animations.py`

**Interfaces:**
- Consumes: ordered `SourcePackage` resources, current ZIPs, `cats_data.json`, `cats/manifest.json`, and `data_version.json`.
- Produces: `overlay_resources(existing: Mapping[str, bytes], ordered_sources: Sequence[tuple[str, Mapping[str, bytes]]]) -> dict[str, bytes]`, `plan_update(config: SyncConfig) -> UpdatePlan`, `apply_update(plan: UpdatePlan, replace_file: Callable = os.replace) -> UpdateReport`, CLI exit status, deterministic `cats/manifest.json`, and updated `data_version.json["animations"]`.

- [ ] **Step 1: Write failing planning and manifest tests**

```python
def test_plan_overlays_versions_and_preserves_absent_entries(self):
    entries = overlay_resources(
        {"455_f.png": b"old", "455_f00.maanim": b"preserve"},
        [
            ("15.5.0", {"455_f.png": b"middle"}),
            ("15.5.1", {"455_f.png": b"new"}),
        ],
    )
    self.assertEqual(entries["455_f.png"], b"new")
    self.assertEqual(entries["455_f00.maanim"], b"preserve")

def test_manifest_revision_is_content_derived_and_deterministic(self):
    records = {
        455: ArchiveRecord(sha256="a" * 64, size=100),
        456: ArchiveRecord(sha256="b" * 64, size=200),
    }
    sources = (
        AppliedSource(region="jp", game_version="15.5.0"),
        AppliedSource(region="jp", game_version="15.5.1"),
    )
    first = build_manifest(records, sources)
    second = build_manifest(dict(reversed(list(records.items()))), sources)
    self.assertEqual(serialize_manifest(first), serialize_manifest(second))

def fixture_config(
    root: Path,
    data_game_version: str,
    applied_sources: tuple[AppliedSource, ...],
    discovered_sources: tuple[SourcePackage, ...],
) -> SyncConfig:
    cats_dir = root / "cats"
    cats_dir.mkdir()
    (root / "cats_data.json").write_text(
        json.dumps({"metadata": {"version": data_game_version}, "units": {}}),
        encoding="utf-8",
    )
    (root / "bcdata").mkdir()
    (root / "bcdata" / "latest.txt").write_text(
        f"15.4.1en\n{data_game_version}jp\n13.4.0kr\n14.7.0tw\n",
        encoding="utf-8",
    )
    (root / "data_version.json").write_text(
        json.dumps({"gameVersion": data_game_version}), encoding="utf-8"
    )
    (cats_dir / "manifest.json").write_text(
        json.dumps({
            "schemaVersion": 1,
            "appliedSources": [
                {"region": item.region, "gameVersion": item.game_version}
                for item in applied_sources
            ],
            "archives": {},
        }),
        encoding="utf-8",
    )
    return SyncConfig(
        bcdata=root / "bcdata", cats_dir=cats_dir,
        cats_data=root / "cats_data.json", data_version=root / "data_version.json",
        sources=(), region="jp", force=False, dry_run=True,
        source_discovery=lambda _path, _region: list(discovered_sources),
    )

def test_plan_rejects_new_data_version_without_matching_source(self):
    config = fixture_config(
        Path(self.temp_dir.name),
        data_game_version="15.6.0",
        applied_sources=(AppliedSource("jp", "15.5.1"),),
        discovered_sources=(),
    )
    with self.assertRaisesRegex(SourceSelectionError, "15.6.0"):
        plan_update(config)
```

Define `SourceSelectionError` as a dedicated `RuntimeError` subclass so CLI
maps this case to exit code `2`.

- [ ] **Step 2: Run tests and confirm RED**

Run: `python -m unittest tests.test_update_cat_animations -v`

Expected: failures for missing planning and manifest functions.

- [ ] **Step 3: Implement the plan/report/manifest models and declared-form audit**

```python
@dataclass(frozen=True)
class SyncConfig:
    bcdata: Path
    cats_dir: Path
    cats_data: Path
    data_version: Path
    sources: tuple[Path, ...]
    region: str
    force: bool
    dry_run: bool
    source_discovery: Callable[[Path, str], list[SourcePackage]] = discover_sources

@dataclass(frozen=True)
class ArchiveRecord:
    sha256: str
    size: int

@dataclass(frozen=True)
class AppliedSource:
    region: str
    game_version: str

@dataclass(frozen=True)
class PlannedArchive:
    unit_id: int
    entries: dict[str, bytes]
    output_bytes: bytes
    existed_before: bool
    changed: bool

@dataclass(frozen=True)
class UpdatePlan:
    config: SyncConfig
    archives: dict[int, PlannedArchive]
    manifest_bytes: bytes
    data_version_bytes: bytes
    applied_sources: tuple[AppliedSource, ...]
    report: "UpdateReport"

class TransactionError(RuntimeError):
    pass

@dataclass(frozen=True)
class UpdateReport:
    discovered_sources: tuple[str, ...]
    selected_sources: tuple[str, ...]
    applied_sources: tuple[str, ...]
    skipped_sources: tuple[str, ...]
    added_resources: int
    replaced_resources: int
    unchanged_resources: int
    preserved_resources: int
    created_archives: tuple[int, ...]
    modified_archives: tuple[int, ...]
    untouched_archives: tuple[int, ...]
    previous_revision: str | None
    new_revision: str
    preexisting_form_warnings: dict[int, tuple[str, ...]]
    new_form_warnings: dict[int, tuple[str, ...]]
    changed_paths: tuple[str, ...]
```

Read declared form counts from `cats_data.json["units"][id]["stats"]`. Require
an archive for every declared unit ID, validate every form actually stored, and
record absent declared forms as warnings instead of synthesizing resources.
Read the desired source version from `cats_data.json["metadata"]["version"]`.
Parse the JP line of `BCData/latest.txt`, strip its `jp` suffix, and reject a
mismatch before source selection. Use `data_version.json` only as the target for
the new `animations` object, not as the desired-version authority.

- [ ] **Step 4: Add failing dry-run and transaction rollback tests**

```python
def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): sha256_hex(path.read_bytes())
        for path in root.rglob("*") if path.is_file()
    }

class FailOnNthReplace:
    def __init__(self, failure_index: int):
        self.failure_index = failure_index
        self.calls = 0

    def __call__(self, source: Path, destination: Path) -> None:
        self.calls += 1
        if self.calls == self.failure_index:
            raise OSError("injected replacement failure")
        os.replace(source, destination)

def transaction_fixture(root: Path, dry_run: bool) -> UpdatePlan:
    cats_dir = root / "cats"
    cats_dir.mkdir()
    (cats_dir / "1.zip").write_bytes(b"old-zip")
    (cats_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
    (root / "data_version.json").write_text("{}\n", encoding="utf-8")
    config = SyncConfig(
        bcdata=root / "bcdata", cats_dir=cats_dir,
        cats_data=root / "cats_data.json", data_version=root / "data_version.json",
        sources=(), region="jp", force=False, dry_run=dry_run,
    )
    report = UpdateReport(
        discovered_sources=(), selected_sources=(), applied_sources=(), skipped_sources=(),
        added_resources=1, replaced_resources=0, unchanged_resources=0,
        preserved_resources=0, created_archives=(), modified_archives=(1,),
        untouched_archives=(), previous_revision=None, new_revision="sha256:new",
        preexisting_form_warnings={}, new_form_warnings={},
        changed_paths=("cats/1.zip", "cats/manifest.json", "data_version.json"),
    )
    entries = {
        "1_f.png": base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        ),
        "1_f.imgcut": b"[imgcut]\n1\n0,0,1,1\n",
        "1_f.mamodel": b"[modelanim:model]\n3\n0\n",
        "1_f00.maanim": b"[modelanim:animation]\n1\n0\n",
    }
    return UpdatePlan(
        config=config,
        archives={1: PlannedArchive(1, entries, build_deterministic_zip(1, entries), True, True)},
        manifest_bytes=b'{"schemaVersion":1}\n',
        data_version_bytes=b'{"animations":{}}\n',
        applied_sources=(), report=report,
    )

def test_dry_run_leaves_tree_byte_identical(self):
    self.root = Path(self.temp_dir.name)
    plan = transaction_fixture(self.root, dry_run=True)
    before = tree_hashes(self.root)
    report = apply_update(plan)
    self.assertTrue(report.changed_paths)
    self.assertEqual(tree_hashes(self.root), before)

def test_failed_replace_restores_all_prior_destinations(self):
    self.root = Path(self.temp_dir.name)
    plan = transaction_fixture(self.root, dry_run=False)
    before = tree_hashes(self.root)
    replacer = FailOnNthReplace(2)
    with self.assertRaises(TransactionError):
        apply_update(plan, replace_file=replacer)
    self.assertEqual(tree_hashes(self.root), before)
```

- [ ] **Step 5: Run transaction tests and confirm RED**

Run: `python -m unittest tests.test_update_cat_animations.TransactionTests -v`

Expected: failures because dry-run and transaction functions are absent.

- [ ] **Step 6: Implement staging and backup-and-restore transaction**

Use `TemporaryDirectory(dir=cats_dir.parent)` with `staged/` and `backup/`.
Generate every changed ZIP plus staged manifest/data-version JSON, validate the
complete staged view, then replace destinations in this order: ZIPs sorted by
numeric ID, `cats/manifest.json`, `data_version.json`. Before each replacement,
copy an existing destination to the matching backup path. On any exception,
restore replaced paths in reverse order and remove destinations that did not
exist before the run.

- [ ] **Step 7: Implement CLI parsing and explicit exit behavior**

```python
parser.add_argument("--bcdata", type=Path, default=Path(r"C:\Users\forex\Documents\GitHub\BCData"))
parser.add_argument("--cats-dir", type=Path, default=Path(__file__).parent / "cats")
parser.add_argument("--cats-data", type=Path, default=Path(__file__).parent / "cats_data.json")
parser.add_argument("--data-version", type=Path, default=Path(__file__).parent / "data_version.json")
parser.add_argument("--source", type=Path, action="append", default=[])
parser.add_argument("--region", choices=("jp", "en", "kr", "tw"), default="jp")
parser.add_argument("--force", action="store_true")
parser.add_argument("--dry-run", action="store_true")
parser.add_argument("--report-json", type=Path)
```

Print selected/applied/skipped sources, resource counts, ZIP IDs, revisions,
form warnings, and changed paths. Write the same fields as JSON when
`--report-json` is present. Return `2` for argument/source-selection errors,
`3` for decryption/validation errors, and `4` for transaction failures.

- [ ] **Step 8: Run CLI/unit tests GREEN and verify help text**

```powershell
python -m unittest tests.test_update_cat_animations -v
python update_cat_animations.py --help
```

Expected: all tests pass and help lists every argument above.

- [ ] **Step 9: Commit Task 3**

```powershell
git add cat_animation_sync.py update_cat_animations.py tests/test_update_cat_animations.py
git commit -m "feat: add transactional cat animation synchronizer"
```

---

### Task 4: Run the initial JP 15.5.0/15.5.1 synchronization

**Files:**
- Create: `cats/manifest.json`
- Create: `cats/866.zip` through `cats/872.zip`
- Modify: affected existing ZIPs under `cats/`
- Modify: `data_version.json`

**Interfaces:**
- Consumes: the validated CLI from Task 3 and the two known JP XAPKs.
- Produces: the 15.5.1 archive baseline and manifest used by future automatic discovery.

- [ ] **Step 1: Capture scoped baselines and run the preview**

```powershell
git status --short
python update_cat_animations.py --dry-run `
  --source "C:\Users\forex\Documents\GitHub\BCData\15-5-0.xapk" `
  --source "C:\Users\forex\Documents\GitHub\BCData\jp.co.ponos.battlecats_15.5.1.xapk" `
  --report-json "$env:TEMP\cat-animation-preview.json"
```

Expected: 112 additions, seven replacements, new ZIP IDs 866–872, affected
IDs 417, 455, 507, 517, 633, 725, and 866–872, with no writes.

- [ ] **Step 2: Apply exactly the previewed sources**

```powershell
python update_cat_animations.py `
  --source "C:\Users\forex\Documents\GitHub\BCData\15-5-0.xapk" `
  --source "C:\Users\forex\Documents\GitHub\BCData\jp.co.ponos.battlecats_15.5.1.xapk" `
  --report-json "$env:TEMP\cat-animation-apply.json"
```

Expected: the same resource counts and a successful transaction.

- [ ] **Step 3: Verify concrete Momoko and new-unit contents**

```powershell
@'
import json, zipfile
from pathlib import Path
root = Path("cats")
with zipfile.ZipFile(root / "455.zip") as archive:
    names = set(archive.namelist())
required = {
    "455/s/455_s.png", "455/s/455_s.imgcut", "455/s/455_s.mamodel",
    "455/s/455_s00.maanim", "455/s/455_s01.maanim",
    "455/s/455_s02.maanim", "455/s/455_s03.maanim",
}
assert required <= names
assert all((root / f"{unit_id}.zip").exists() for unit_id in range(873))
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
assert manifest["latestSource"] == {"region": "jp", "gameVersion": "15.5.1"}
assert set(map(int, manifest["archives"])) == set(range(873))
'@ | python -
```

- [ ] **Step 4: Prove idempotence**

Run: `python update_cat_animations.py --dry-run`

Expected: zero pending resources, ZIPs, manifest changes, or data-version
changes; the reported revision equals the applied revision.

- [ ] **Step 5: Run all UpdatedBCData Python tests**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: all tests pass.

- [ ] **Step 6: Commit the generated baseline separately**

```powershell
git add cats data_version.json
git commit -m "data: sync cat animations through JP 15.5.1"
```

---

### Task 5: Integrate the mandatory animation step and durable instructions

**Files:**
- Modify: `C:\Users\forex\Downloads\A\Automatizacion\update_all.py`
- Modify: `C:\Users\forex\Downloads\A\Automatizacion\README.md`
- Create: `C:\Users\forex\Downloads\A\Automatizacion\test_update_all.py`
- Modify: `AGENTS.md`
- Modify: `C:\Users\forex\Documents\GitHub\BCData\AGENTS.md`
- Modify: `C:\Users\forex\StudioProjects\CatStats\AGENTS.md`

**Interfaces:**
- Consumes: `update_cat_animations.py` and the existing normal update sequence.
- Produces: default and `--only animations` orchestration plus repository-local instructions visible to future agents.

- [ ] **Step 1: Write the failing orchestrator contract test**

```python
class UpdateAllAnimationStepTests(unittest.TestCase):
    def test_animation_step_is_after_evolution_and_uses_versioned_script(self):
        module = import_update_all_without_running_main()
        ids = [step["id"] for step in module.STEPS]
        self.assertEqual(ids[-2:], ["evolution", "animations"])
        step = module.STEPS[-1]
        self.assertEqual(step["script"], str(Path(module.UPDATED_BCDATA) / "update_cat_animations.py"))
```

- [ ] **Step 2: Run the test and confirm RED**

Run from the automation directory: `python -m unittest test_update_all -v`

Expected: failure because `animations` is absent from `STEPS`.

- [ ] **Step 3: Add the animation step and update orchestrator usage text**

```python
{
    "id": "animations",
    "name": "Sync Cat Animations",
    "script": os.path.join(UPDATED_BCDATA, "update_cat_animations.py"),
},
```

Place it immediately after `evolution`. Keep `run_step` exit propagation so a
non-zero synchronizer exit makes the overall run fail. Add `animations` to the
module docstring's numbered sequence and document
`python update_all.py --skip-pull --only animations` in the README.

- [ ] **Step 4: Run the orchestrator test GREEN**

Run: `python -m unittest test_update_all -v`

Expected: pass without invoking `main()` or changing data files.

- [ ] **Step 5: Add exact future-agent rules to all three AGENTS files**

Each file must state:

```text
A game-data update is incomplete until update_cat_animations.py succeeds.
Run the normal update_all.py flow, or use --only animations for repair.
PONOS packs are incremental: apply every unrecorded source in semantic-version order.
Never replace an archive from one pack wholesale; merge entries and replace byte-different files only.
Require a second --dry-run with zero pending changes before reporting completion.
Require cats/manifest.json latestSource.gameVersion to match the selected game-data version unless a documented region/version exception exists.
```

`BCData/AGENTS.md` must additionally require retaining the source XAPK/APKS/APK.
`CatStats/AGENTS.md` must additionally preserve the manifest hash/offline cache
fallback contract. `UpdatedBCData/AGENTS.md` must list the ZIP structure and
manifest validation command.

- [ ] **Step 6: Verify instructions and scoped diffs**

```powershell
rg -n "update_cat_animations|incremental|manifest.json|--only animations" `
  AGENTS.md `
  "C:\Users\forex\Documents\GitHub\BCData\AGENTS.md" `
  "C:\Users\forex\StudioProjects\CatStats\AGENTS.md" `
  "C:\Users\forex\Downloads\A\Automatizacion\README.md"
git diff --check
```

Expected: all four operator/agent locations contain the workflow; UpdatedBCData
has no whitespace errors. Confirm the 32,594 pre-existing BCData changes and
the three pre-existing CatStats paths are otherwise unchanged.

- [ ] **Step 7: Commit each repository's instruction change without staging unrelated work**

```powershell
git -C "C:\Users\forex\Documents\GitHub\UpdatedBCData" add AGENTS.md
git -C "C:\Users\forex\Documents\GitHub\UpdatedBCData" commit -m "docs: require animation sync for game updates"
git -C "C:\Users\forex\Documents\GitHub\BCData" add AGENTS.md
git -C "C:\Users\forex\Documents\GitHub\BCData" commit -m "docs: require animation sync after extraction"
git -C "C:\Users\forex\StudioProjects\CatStats" add AGENTS.md
git -C "C:\Users\forex\StudioProjects\CatStats" commit -m "docs: document animation cache update workflow"
```

Before each commit, inspect `git diff --cached --name-only` and require exactly
`AGENTS.md`. The automation folder is not committed by this step. Preserve its
updated `update_all.py`, `README.md`, and contract test in place.

---

### Task 6: Pure Android manifest and cache-resolution policy

**Files:**
- Create: `C:\Users\forex\StudioProjects\CatStats\app\src\main\java\cat\battlestats\animation\loader\AnimationArchiveResolver.kt`
- Create: `C:\Users\forex\StudioProjects\CatStats\app\src\test\java\cat\battlestats\animation\AnimationArchiveResolverTest.kt`

**Interfaces:**
- Consumes: manifest JSON, optional cached ZIP bytes, and a suspend downloader.
- Produces: `AnimationArchiveManifest`, `AnimationArchiveEntry`, `AnimationManifestProvider`, `AnimationArchiveDownloader`, and `AnimationArchiveResolver.resolve(unitId, cachedBytes, validator) -> ResolvedArchive`.

- [ ] **Step 1: Write failing tests for manifest parsing and SHA decisions**

```kotlin
private fun manifestJson(unitId: String, hash: String): String = """
    {
      "schemaVersion": 1,
      "revision": "sha256:test",
      "archives": {"$unitId": {"sha256": "$hash", "size": 6}}
    }
""".trimIndent()

private fun resolver(
    expectedHash: String,
    download: suspend () -> ByteArray
): AnimationArchiveResolver = AnimationArchiveResolver(
    manifestProvider = AnimationManifestProvider {
        AnimationArchiveManifest.decode(manifestJson("455", expectedHash))
    },
    downloader = AnimationArchiveDownloader { download() },
)

@Test
fun `matching cached hash avoids download`() = runTest {
    val cached = "cached".encodeToByteArray()
    var downloads = 0
    val resolver = resolver(expectedHash = cached.sha256Hex()) {
        downloads++
        "remote".encodeToByteArray()
    }
    val result = resolver.resolve(455, cached) { true }
    assertArrayEquals(cached, result.bytes)
    assertFalse(result.shouldPersist)
    assertEquals(0, downloads)
}

@Test
fun `manifest JSON maps unit id to archive hash`() {
    val manifest = AnimationArchiveManifest.decode(manifestJson("455", "abcd"))
    assertEquals("abcd", manifest.archives["455"]?.sha256)
}
```

- [ ] **Step 2: Run the focused Gradle test and confirm RED**

Run: `.\gradlew.bat testDebugUnitTest --tests "cat.battlestats.animation.AnimationArchiveResolverTest" --console=plain`

Expected: Kotlin compilation failure because resolver types do not exist.

- [ ] **Step 3: Implement serializable manifest models and hash helpers**

```kotlin
@Serializable
data class AnimationArchiveEntry(val sha256: String, val size: Long)

@Serializable
data class AnimationArchiveManifest(
    val schemaVersion: Int,
    val revision: String,
    val archives: Map<String, AnimationArchiveEntry>
) {
    companion object {
        fun decode(text: String): AnimationArchiveManifest =
            Json { ignoreUnknownKeys = true }.decodeFromString(text)
    }
}

internal fun ByteArray.sha256Hex(): String =
    MessageDigest.getInstance("SHA-256").digest(this).joinToString("") { "%02x".format(it) }
```

- [ ] **Step 4: Add failing stale/offline/hash-mismatch tests**

Cover these exact cases:

```kotlin
`stale cache downloads valid replacement and marks it for persistence`
`downloaded hash mismatch keeps valid old cache`
`download failure keeps valid old cache`
`manifest failure uses old cache without download`
`no cache and no manifest uses legacy download behavior`
`replacement parse failure falls back to parseable old cache`
```

Implement them with explicit byte arrays and assertions:

```kotlin
@Test
fun `stale cache downloads valid replacement and marks it for persistence`() = runTest {
    val fresh = "fresh".encodeToByteArray()
    val result = resolver(fresh.sha256Hex()) { fresh }
        .resolve(455, "stale".encodeToByteArray()) { true }
    assertArrayEquals(fresh, result.bytes)
    assertTrue(result.shouldPersist)
}

@Test
fun `downloaded hash mismatch keeps valid old cache`() = runTest {
    val stale = "stale".encodeToByteArray()
    val result = resolver("a".repeat(64)) { "wrong".encodeToByteArray() }
        .resolve(455, stale) { it.contentEquals(stale) }
    assertArrayEquals(stale, result.bytes)
    assertFalse(result.shouldPersist)
}

@Test
fun `download failure keeps valid old cache`() = runTest {
    val stale = "stale".encodeToByteArray()
    val result = resolver("a".repeat(64)) { throw IOException("offline") }
        .resolve(455, stale) { it.contentEquals(stale) }
    assertArrayEquals(stale, result.bytes)
}

@Test
fun `manifest failure uses old cache without download`() = runTest {
    var downloads = 0
    val resolver = AnimationArchiveResolver(
        AnimationManifestProvider { null },
        AnimationArchiveDownloader { downloads++; "remote".encodeToByteArray() },
    )
    val stale = "stale".encodeToByteArray()
    assertArrayEquals(stale, resolver.resolve(455, stale) { true }.bytes)
    assertEquals(0, downloads)
}

@Test
fun `no cache and no manifest uses legacy download behavior`() = runTest {
    val remote = "remote".encodeToByteArray()
    val resolver = AnimationArchiveResolver(
        AnimationManifestProvider { null }, AnimationArchiveDownloader { remote },
    )
    val result = resolver.resolve(455, null) { true }
    assertArrayEquals(remote, result.bytes)
    assertTrue(result.shouldPersist)
}

@Test
fun `replacement parse failure falls back to parseable old cache`() = runTest {
    val stale = "stale".encodeToByteArray()
    val fresh = "fresh".encodeToByteArray()
    val result = resolver(fresh.sha256Hex()) { fresh }
        .resolve(455, stale) { it.contentEquals(stale) }
    assertArrayEquals(stale, result.bytes)
    assertFalse(result.shouldPersist)
}
```

- [ ] **Step 5: Implement resolver behavior**

```kotlin
fun interface AnimationManifestProvider {
    suspend fun get(): AnimationArchiveManifest?
}

fun interface AnimationArchiveDownloader {
    suspend fun download(unitId: Int): ByteArray
}

data class ResolvedArchive(val bytes: ByteArray, val shouldPersist: Boolean)
```

`resolve` obtains the expected hash, returns a matching/valid cache immediately,
downloads when absent or stale, rejects a downloaded hash or validator failure,
and falls back to a valid cached archive. It throws the download/validation
error only when no valid cached archive exists. If the manifest or archive
entry is absent, preserve legacy cache-first behavior.

- [ ] **Step 6: Run resolver tests GREEN**

Run: `.\gradlew.bat testDebugUnitTest --tests "cat.battlestats.animation.AnimationArchiveResolverTest" --console=plain`

Expected: all resolver tests pass.

- [ ] **Step 7: Commit only Task 6 CatStats files**

```powershell
git add app/src/main/java/cat/battlestats/animation/loader/AnimationArchiveResolver.kt `
        app/src/test/java/cat/battlestats/animation/AnimationArchiveResolverTest.kt
git commit -m "feat: add hash-aware animation archive resolver"
```

Do not stage the user's existing `app/build.gradle.kts`,
`CatClassification.kt`, or enum-classification tests.

---

### Task 7: Wire hash-aware resolution into BattleCatsAssetLoader

**Files:**
- Modify: `C:\Users\forex\StudioProjects\CatStats\app\src\main\java\cat\battlestats\animation\loader\BattleCatsAssetLoader.kt`
- Modify: `C:\Users\forex\StudioProjects\CatStats\app\src\test\java\cat\battlestats\animation\AnimationStorageContractTest.kt`
- Create: `C:\Users\forex\StudioProjects\CatStats\app\src\test\java\cat\battlestats\animation\RemoteAnimationManifestProviderTest.kt`

**Interfaces:**
- Consumes: Task 6 resolver and `https://raw.githubusercontent.com/deivih84/UpdatedBCData/main/cats/manifest.json`.
- Produces: one manifest fetch per process, verified ZIP replacement, and stale-cache fallback.

- [ ] **Step 1: Write failing loader contract and provider-cache tests**

Update `AnimationStorageContractTest` to require these source-level contracts:

```kotlin
assertTrue(loader.contains("MANIFEST_URL"))
assertTrue(loader.contains("AnimationArchiveResolver"))
assertTrue(loader.contains("cachedArchiveBytes"))
assertTrue(loader.contains("shouldPersist"))
assertTrue(loader.contains("parseZipContents"))
```

In `RemoteAnimationManifestProviderTest`, use an injected fetch lambda and call
`get()` twice; assert the lambda runs once and both calls return the same
manifest. Add a failure case proving one failed session fetch returns `null`
without deleting cache state.

```kotlin
@Test
fun `provider fetches manifest once per process session`() = runTest {
    var calls = 0
    val provider = RemoteAnimationManifestProvider {
        calls++
        manifestJson("455", "a".repeat(64))
    }
    assertNotNull(provider.get())
    assertNotNull(provider.get())
    assertEquals(1, calls)
}

@Test
fun `provider caches a session fetch failure as null`() = runTest {
    var calls = 0
    val provider = RemoteAnimationManifestProvider {
        calls++
        throw IOException("offline")
    }
    assertNull(provider.get())
    assertNull(provider.get())
    assertEquals(1, calls)
}
```

- [ ] **Step 2: Run the focused tests and confirm RED**

```powershell
.\gradlew.bat testDebugUnitTest `
  --tests "cat.battlestats.animation.AnimationStorageContractTest" `
  --tests "cat.battlestats.animation.RemoteAnimationManifestProviderTest" `
  --console=plain
```

Expected: contract/provider failures because loader integration is absent.

- [ ] **Step 3: Implement the process-cached remote manifest provider**

Add `RemoteAnimationManifestProvider` beside the resolver. It accepts a suspend
`fetchText: suspend () -> String`, guards the first fetch with `Mutex`, caches a
successful parsed manifest or a session failure result, and never throws to the
loader. Production wiring fetches `MANIFEST_URL` with the existing OkHttp
client and returns `null` on non-2xx, empty body, JSON error, or I/O failure.
Expose one `sharedManifestProvider` from `BattleCatsAssetLoader`'s companion
object so separate screen-level loader instances share the same process cache.

- [ ] **Step 4: Refactor loader archive flow without changing parsing semantics**

Change `loadUnit` to:

```kotlin
val cachedArchiveBytes = readStoredArchive(unitId)
val resolved = archiveResolver.resolve(unitId, cachedArchiveBytes) { bytes ->
    parseZipContents(unitId, form, bytes) != null
}
val model = parseZipContents(unitId, form, resolved.bytes)
    ?: return@withContext Result.failure(Exception("Failed to parse unit $unitId data"))
if (resolved.shouldPersist) saveToStorage(unitId, resolved.bytes)
return@withContext Result.success(model)
```

Replace `loadFromStorage` with `readStoredArchive`, retaining legacy-cache
migration only after the bytes validate. Keep `saveToStorage`, storage trimming,
`isUnitDownloaded`, and `clearCache` behavior. The old archive remains on disk
until the replacement hash and selected-form parse both succeed.

- [ ] **Step 5: Run focused tests GREEN, then all Android unit tests**

```powershell
.\gradlew.bat testDebugUnitTest `
  --tests "cat.battlestats.animation.AnimationStorageContractTest" `
  --tests "cat.battlestats.animation.AnimationArchiveResolverTest" `
  --tests "cat.battlestats.animation.RemoteAnimationManifestProviderTest" `
  --console=plain
.\gradlew.bat testDebugUnitTest --console=plain
```

Expected: focused and complete unit-test tasks pass.

- [ ] **Step 6: Commit only loader integration files**

```powershell
git add app/src/main/java/cat/battlestats/animation/loader/BattleCatsAssetLoader.kt `
        app/src/main/java/cat/battlestats/animation/loader/AnimationArchiveResolver.kt `
        app/src/test/java/cat/battlestats/animation/AnimationStorageContractTest.kt `
        app/src/test/java/cat/battlestats/animation/RemoteAnimationManifestProviderTest.kt
git commit -m "feat: refresh stale cached cat animations"
```

---

### Task 8: Full workflow and regression verification

**Files:**
- Read: all scoped outputs from Tasks 1–7.
- Modify only if a failing test identifies a scoped defect: the exact production/test file responsible for that defect.

**Interfaces:**
- Consumes: final synchronizer, archives, manifest, orchestration, documentation, and Android integration.
- Produces: fresh evidence that the update is reproducible and app-compatible.

- [ ] **Step 1: Run every UpdatedBCData test and idempotence check**

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python update_cat_animations.py --dry-run
```

Expected: all tests pass and dry-run reports zero pending changes.

- [ ] **Step 2: Validate all ZIPs against the manifest**

Run a read-only Python verification that recomputes SHA-256 and sizes for all
`0.zip` through `872.zip`, checks exact equality with all 873 manifest entries,
opens every ZIP with `ZipFile.testzip()`, validates every present form with
`validate_archive`, and confirms no archive ID is missing or extra.

Expected: 873 archives, 873 manifest entries, zero corrupt ZIPs, zero stored-form
errors, and only declared-form warnings recorded in the manifest.

- [ ] **Step 3: Run the established cats-data validation and Python suites**

```powershell
python scripts\validate_cats_data.py `
  C:\Users\forex\Documents\GitHub\UpdatedBCData\cats_data.json `
  C:\Users\forex\Documents\GitHub\BCData\15.5.1jp\DataLocal `
  app\src\main\assets\data\names.txt `
  --expected-version 15.5.1
python -m unittest discover -s scripts\tests -p "test_*.py" -v
```

Run from `C:\Users\forex\StudioProjects\CatStats`.

Expected: exact source/JSON unit coverage and all script tests pass.

- [ ] **Step 4: Run Android unit tests and build**

```powershell
.\gradlew.bat testDebugUnitTest assembleDebug --console=plain
```

Expected: both Gradle tasks succeed.

- [ ] **Step 5: Exercise the normal animation-only operator path**

Run from `C:\Users\forex\Downloads\A\Automatizacion`:

```powershell
python update_all.py --skip-pull --only animations
```

Expected: animation step succeeds and reports no pending changes. It must not
alter cats data, stages, enemies, or unrelated files.

- [ ] **Step 6: Review scoped repository state**

```powershell
git -C "C:\Users\forex\Documents\GitHub\UpdatedBCData" status --short
git -C "C:\Users\forex\Documents\GitHub\BCData" status --short
git -C "C:\Users\forex\StudioProjects\CatStats" status --short
```

Confirm UpdatedBCData changes are limited to the planned scripts/tests/docs,
`cats/`, and `data_version.json`; BCData retains its pre-existing 32,594-change
baseline plus only its AGENTS edit; CatStats retains its pre-existing three
paths plus only the planned loader/tests/AGENTS edits.

- [ ] **Step 7: Record final evidence**

Report source versions applied, 112 added and seven replaced resources, created
and modified ZIP IDs, manifest revision, 873/873 archive coverage, Momoko's
seven `455_s` files, declared-form warning counts, Python test totals, Gradle
results, and retained unrelated dirty paths. Do not push or publish.
