# Gacha Catalog Sync Implementation Plan

> **For agentic workers:** Execute inline with superpowers:executing-plans.
> Track steps below; do not delegate implementation.

**Goal:** Maintain the EN banner catalogue and images without periodic manual searches.

**Architecture:** Parse game pools and PONOS events, calculate a validated catalogue
plan, then publish it atomically. Resolve identity conservatively and retain
distinct scheduled variants. Source adapters isolate HTTP and image retrieval.

**Tech Stack:** Python 3.9+, requests, beautifulsoup4, Pillow, unittest, GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-10-06-gacha-catalog-sync-design.md`

## Global Constraints

- Keep existing catalogue and schedule consumer formats compatible.
- Do not use fuzzy names to overwrite pools.
- Preserve repeated pool IDs and their order.
- Preserve original future permanent-capsule start dates.
- `--dry-run` writes no files.
- Do not commit account credentials.

## Review Focus

- Pool IDs reused with promotional names: conflict must retain previous data.
- Active and future permanent capsules: choose current canonical pool.
- A HTTP 200 containing HTML instead of a PNG: reject and retain prior image.
- Unknown cats or incomplete rarity data: stop without partial publication.
- Repeated runs and failed replacements: no data churn and restore original files.

### Task 1: Game sources and identity planning

**Files:** `gacha_sources.py`, `gacha_catalog_sync.py`,
`tests/test_gacha_sync.py`, `gacha_sync_config.json`.

**Interfaces:** `parse_game_data(files) -> dict`,
`scheduled_events(tsv, today) -> list`,
`plan_catalog(catalog, cache, state, events, game, series_names, metadata) -> tuple`.

- [x] Add literal fixtures for valid/interleaved TSV, pool/rarity files,
  active/future capsule variants and conflicting names.
- [x] Run `python -m unittest discover -s tests -p test_gacha_sync.py -v`;
  observe failures caused by missing sync behavior.
- [x] Implement strict parsers, exact identity and distinct variant snapshots.
- [x] Run targeted tests, then the repository suite.

### Task 2: Image sources, transaction and CLI

**Files:** `gacha_sources.py`, `gacha_catalog_sync.py`, `sync_gacha_catalog.py`,
`tests/test_gacha_sync.py`, `tests/test_gacha_sources.py`.

**Interfaces:** `BannerSource.metadata(gacha_id, option) -> dict`,
`publish(outputs, dry_run=False) -> list`, `main(argv=None) -> int`.

- [x] Add failing tests for image identity, invalid PNG, byte-identical reruns,
  dry-run and rollback using real temporary files and HTTP response fixtures.
- [x] Implement wiki ID lookup, verified PNG conversion, content-addressed URLs,
  local drawable copy, stable JSON reports and atomic publication.
- [x] Verify `python sync_gacha_catalog.py --help` and the targeted tests.
- [x] Run a real dry-run; inspect every unresolved identity before applying.

### Task 3: Initial synchronization and workflow

**Files:** `.github/workflows/update_bc_schedule.yml`, `docs/gacha-sync.md`,
`all_gachas_en.json`, `gacha_id_cache.json`, `gacha_sync_state.json`,
`gacha_sync_report.json`, `images/gacha/`, `AGENTS.md`.

- [x] Apply the checked real synchronization and regenerate the calendar.
- [x] Add scheduled execution, dependencies, private auth cache, tests, summary
  and report artifact. Restrict committed paths to public data and images.
- [x] Document commands, sources, ambiguity handling and deployment status.
- [x] Run `python sync_gacha_catalog.py --dry-run` and confirm no pending writes.
- [x] Run `python update_cat_animations.py --dry-run` and confirm zero changes.
- [x] Run `python -m unittest discover -s tests -p "test_*.py" -v`.
- [x] Review the complete diff and report local completion/deployment separately.

## Verification result

94 repository tests passed. Default real-source dry-run: zero pending file changes;
one retained artwork warning for Luga Families #986. Animation dry-run: zero
changed paths, with 27 pre-existing declared-form warning records retained.
Online Godfat pool acquisition was tested against the live PONOS schedule.
Read-only independent review found four issues; all reproduced and fixed with
regressions, including mutable historical-pool tests blocking valid future updates.
Workflow prepared locally; no commit, push or GitHub run was performed.
