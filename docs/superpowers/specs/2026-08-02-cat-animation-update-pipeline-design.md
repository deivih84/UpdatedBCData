# Battle Cats Animation Update Pipeline Design

**Date:** 2026-08-02

**Goal:** Make cat animation archives a reproducible, mandatory part of every
Battle Cats data update, while preserving unchanged resources and refreshing
stale archives cached by Battle Stats.

## Context

`UpdatedBCData/cats` currently contains one ZIP per animation ID. Each archive
uses this structure:

```text
cats/<id>.zip
└── <id>/<form>/
    ├── <id>_<form>.png
    ├── <id>_<form>.imgcut
    ├── <id>_<form>.mamodel
    └── <id>_<form>*.maanim
```

Forms use `f`, `c`, `s`, and `u`. The Battle Stats loader downloads
`cats/<id>.zip` from `UpdatedBCData`, parses the selected form, and stores the
raw ZIP in persistent app storage.

The existing data updater does not update these archives. It also cannot
safely rebuild them from one XAPK because PONOS installation packs are
incremental. The JP 15.5.0 package contributes 84 missing resources and five
changed resources relative to the current archives; JP 15.5.1 contributes 28
additional missing resources and two additional changes. Processing only
15.5.1 would therefore leave the update incomplete.

The initial 15.5.0/15.5.1 synchronization is expected to:

- add 112 resource files;
- replace seven resource files whose decrypted bytes changed;
- affect animation IDs 417, 455, 507, 517, 633, 725, and 866 through 872;
- create `866.zip` through `872.zip`;
- leave 842 identical resources untouched.

## Source discovery and ordering

The synchronization tool will read APK, XAPK, or APKS files stored in
`C:\Users\forex\Documents\GitHub\BCData`. It will inspect package metadata
rather than trusting filenames and accept only Battle Cats installation
packages with an `InstallPack.apk` containing the required resource packs.

Sources are identified by package region and dotted game version, then applied
in ascending semantic-version order. A source version already recorded in the
animation manifest is skipped unless explicitly requested with a force option.
The first managed run will explicitly apply JP 15.5.0 followed by JP 15.5.1 so
the new manifest starts from a known baseline. Later normal updates discover
newer compatible sources automatically.

For normal updates, JP is the preferred animation source because it receives
new game content first. Another region may be selected explicitly when needed,
but sources from different regions must not be interleaved at the same version
without an explicit override. Animation names and contents are treated as
region-independent only after package identity and version are verified.

If `BCData/latest.txt` or the selected extracted game-data directory announces
a version newer than the last animation source but no matching installation
package is available, the animation step fails before changing the manifest.
It must not silently publish an old animation revision as current.

## Resource extraction

The synchronizer reads `InstallPack.apk` directly from the outer archive and
decrypts only:

- `ImageDataLocal`: `.imgcut`, `.mamodel`, and `.maanim` resources;
- `NumberLocal`: model texture `.png` resources.

It accepts exact unit-animation names only:

- `<numeric_id>_<form>.png`
- `<numeric_id>_<form>.imgcut`
- `<numeric_id>_<form>.mamodel`
- `<numeric_id>_<form><animation_suffix>.maanim`

`form` must be one of `f`, `c`, `s`, or `u`. This excludes unrelated names
such as `000_stamp_f.*` and `006_charaawa.*`. Numeric prefixes are canonicalized
by removing leading zeroes, so PONOS resource `076_u.png` maps to archive entry
`76/u/76_u.png`.

The implementation uses `tbcml` for the established PONOS list/pack
decryption. It does not extract entire game packs or leave a temporary unpacked
asset tree in either repository.

## Incremental archive merge

Resources are grouped by canonical animation ID and form. For each affected
unit, the synchronizer reads the existing ZIP when present and creates a merged
view with these rules:

1. Preserve existing entries absent from the incoming incremental sources.
2. Add incoming entries that do not exist.
3. Replace an existing entry only when its decrypted bytes differ.
4. Apply later source versions after earlier versions, so the newest resource
   wins for duplicate names.
5. Do not rewrite an archive when its merged entry names and bytes are
   unchanged.
6. Write changed archives deterministically, ordered by normalized path, into
   a run-specific staging directory and validate the complete staged set before
   replacing any destination.
7. Replace each destination atomically while retaining run-specific backups.
   If any replacement fails, restore every destination already replaced and
   leave the old manifest and `data_version.json` unchanged.

Every stored form must contain one PNG, one `.imgcut`, one `.mamodel`, and at
least one `.maanim`. All entries must remain beneath `<id>/<form>/`, use the
same canonical ID as their ZIP, have non-zero data, and pass the applicable
PNG/text-parser smoke checks.

Some existing collaboration and egg units intentionally expose animation
assets for only a subset of their data forms. The synchronizer does not invent,
copy, or alias model assets for a form that PONOS did not supply. It validates
every form that is present, ensures every known unit has an archive, and emits
a structured warning for declared data forms without animation resources.
Those warnings are compared with the previous manifest so a newly introduced
gap is visible to the updater.

## Animation manifest

The synchronizer owns `cats/manifest.json`. Its stable schema is:

```json
{
  "schemaVersion": 1,
  "revision": "sha256:<digest>",
  "latestSource": {
    "region": "jp",
    "gameVersion": "15.5.1"
  },
  "appliedSources": [
    {"region": "jp", "gameVersion": "15.5.0"},
    {"region": "jp", "gameVersion": "15.5.1"}
  ],
  "archives": {
    "455": {"sha256": "<hex digest>", "size": 123456}
  },
  "declaredFormWarnings": {
    "870": ["f", "c"]
  }
}
```

`revision` is derived from the sorted archive ID, SHA-256, and size tuples; it
is not timestamp-based. Re-running the synchronizer without source or archive
changes produces byte-identical archives and a byte-identical manifest.

`data_version.json` gains an `animations` object containing the manifest path,
revision, source region, and source game version. The animation step stages
both JSON files and updates them only after the archives and complete manifest
pass validation. Manifest and data-version replacement participate in the same
backup-and-restore sequence as the ZIP files.

## Battle Stats cache validation

`BattleCatsAssetLoader` will fetch `cats/manifest.json` lazily and at most once
per application process. Before using a stored archive it compares the local
ZIP SHA-256 with the expected archive hash.

- Matching archive: parse and reuse it without downloading the ZIP again.
- Missing or mismatched archive: download the remote ZIP, verify its hash,
  parse it, and atomically replace the stored archive.
- Manifest unavailable: retain current offline-first behavior and try the
  stored archive.
- New ZIP download or hash verification fails: retain and try the previous
  stored archive as an offline fallback; never delete a usable archive before
  its replacement is verified.
- Archive absent from the manifest: use the existing download behavior so an
  older app remains forward-compatible with manifest mistakes or transitions.

The loader verifies the downloaded hash before parsing or persisting it. A
manifest/ZIP publication race therefore cannot poison persistent storage.

## Normal update integration

`C:\Users\forex\Downloads\A\Automatizacion\update_all.py` gains an
`animations` step in the normal default sequence. It runs after the cat data
and evolution steps, before optional publication. It can also be invoked as:

```powershell
python update_all.py --skip-pull --only animations
```

The step calls the version-controlled synchronizer in `UpdatedBCData`, passes
the BCData source directory, current public `cats_data.json`, target `cats`
directory, and `data_version.json`, and propagates a non-zero exit status. The
normal updater must not report overall success when animation synchronization
or validation fails.

The automation README documents the same command, source requirements, dry-run
mode, expected report, and recovery behavior.

## Durable agent instructions

The following repository instructions are updated so a future agent receives
the workflow without access to the conversation that created it:

- `UpdatedBCData/AGENTS.md`: animation archive format, synchronization command,
  merge rules, manifest contract, and validation requirements.
- `BCData/AGENTS.md`: retain the new installation package and run animation
  synchronization after extracting a new game version.
- `CatStats/AGENTS.md`: include animations in the mandatory `update_all.py`
  sequence and preserve the hash-aware offline cache contract.
- `Automatizacion/README.md`: operator-oriented commands and failure handling.

Instructions explicitly state that a new-version update is incomplete until
the animation step has run and its source version agrees with the current game
data version, unless the operator records a deliberate region/version exception.

## Command-line behavior and reporting

The synchronizer supports:

- normal apply mode;
- `--dry-run`, which performs discovery, decryption, comparison, and validation
  without filesystem writes;
- one or more explicit source paths for repair or initial baselining;
- a force option for intentionally reapplying a recorded source;
- explicit source-region selection.

Its final machine-readable and human-readable report includes:

- discovered, selected, applied, and skipped source versions;
- added, replaced, unchanged, and preserved resource counts;
- created, modified, and untouched ZIP counts and IDs;
- manifest revision before and after;
- complete-form validation failures;
- declared-form warnings, separated into pre-existing and newly introduced;
- exact paths changed.

Any source-identification error, decryption failure, unsafe ZIP path, corrupt
PNG, incomplete stored form, manifest mismatch, or atomic replacement failure
returns a non-zero exit code.

## Testing and verification

Python tests cover:

- exact resource-name filtering, including false-positive rejection;
- leading-zero normalization;
- ascending multi-version overlay;
- add, replace, preserve, and unchanged merge cases;
- deterministic ZIP and manifest generation;
- incomplete present-form rejection;
- declared-but-unavailable form warnings;
- dry-run immutability;
- missing-new-version source failure;
- rollback behavior when validation fails.

Android tests cover:

- matching cached hash reuse;
- mismatched cached hash redownload;
- downloaded hash mismatch rejection;
- manifest-unavailable offline fallback;
- failed replacement preserving the prior cache;
- archives absent from the manifest retaining legacy behavior.

Final verification for each game update includes:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
python update_cat_animations.py --dry-run
python update_cat_animations.py
python update_cat_animations.py --dry-run
```

The first dry run previews expected changes, the apply performs them, and the
second dry run must report zero pending archive or manifest changes.

Then run the existing CatStats data validator and Python tests, followed by:

```powershell
.\gradlew.bat testDebugUnitTest assembleDebug --console=plain
```

Scoped Git review must confirm that unrelated dirty changes in BCData,
UpdatedBCData, CatStats, and the automation folder were preserved. No pull,
commit, push, archive upload, or publication is performed by the animation
synchronizer itself.
