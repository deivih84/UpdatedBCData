# EN Gacha Alias and Pool Corrections Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Canonicalize the four EN promotional gacha names in the catalog and schedule, and validate the corrected Epicfest and Gals of Summer Sunshine pools.

**Architecture:** Exact PONOS promotional text becomes an alias in `all_gachas_en.json`, so `fetch_bc_schedule.py` resolves it without code changes. The live EN schedule stores only canonical `nombre` and IDs. A focused catalog test protects aliases, unit pools and schedule rows.

**Tech Stack:** Python 3 standard library (`json`, `unittest`), JSON data files.

## Global Constraints

- Preserve the canonical names `Gals of Summer Sunshine`, `Luga Families`, `Iron Legion` and `Epicfest`.
- Preserve campaign dates and `caracteristicas` in the EN schedule.
- Gals of Summer Sunshine Uber Rare IDs are exactly `[820, 714, 564, 438, 354, 275]`.
- Epicfest contains both Netherworld Nymph Lunacia (`787`) and Lone Moon Lunos (`859`).
- Do not modify unrelated gacha metadata, rates or unit pools.

---

### Task 1: Add failing catalog and resolver regression tests

**Files:**
- Create: `tests/test_gacha_catalog.py`
- Modify: `tests/test_fetch_bc_schedule.py`

**Interfaces:**
- Consumes: `_load_name_dbs()` and `_resolve_gacha_name(entry, by_id, alias_db)` from `fetch_bc_schedule.py`; `all_gachas_en.json`, `cats_data.json`, and `gachas_eventos_actualizados_en1.json`.
- Produces: regression coverage for exact aliases, canonical schedule records, and pools.

- [x] **Step 1: Write the failing resolver test**

Add to `FestivalResolutionTests`:

```python
def test_repository_catalog_resolves_lone_moon_lunos_to_epicfest(self):
    by_id, alias_db = schedule._load_name_dbs()
    entry = festival_entry(
        9996,
        "Lone Moon Lunos added! Special Capsules featuring powerful limited units!",
        2600,
        900,
    )
    self.assertEqual(schedule._resolve_gacha_name(entry, by_id, alias_db), "Epicfest")
```

- [x] **Step 2: Write the failing data test**

Create `tests/test_gacha_catalog.py` with tests asserting all four exact promotional aliases map to their canonical banner, Sunshine's `ubers` list equals `[820, 714, 564, 438, 354, 275]`, Epicfest includes `787` and `859`, and each affected date in the schedule has its expected canonical `id` and `nombre`.

- [x] **Step 3: Run the focused tests and verify failure**

Run: `python -m unittest tests.test_fetch_bc_schedule tests.test_gacha_catalog -v`

Expected: FAIL because the catalog and schedule currently retain the raw texts, Sunshine has the mixed Blue Ocean units, and Epicfest omits `859`.

### Task 2: Normalize aliases, pools and live schedule

**Files:**
- Modify: `all_gachas_en.json`
- Modify: `gachas_eventos_actualizados_en1.json`

**Interfaces:**
- Consumes: exact PONOS promotional titles and unit metadata in `cats_data.json`.
- Produces: aliases loaded by `_load_name_dbs()` and canonical entries consumed by the app.

- [x] **Step 1: Add exact aliases and correct pools**

Update the four canonical records with their full PONOS texts. Replace Sunshine's `ubers` with `[820, 714, 564, 438, 354, 275]` and insert `859` in Epicfest's `ubers` list next to the current high-ID releases.

- [x] **Step 2: Canonicalize the live schedule**

Replace the four raw schedule `nombre` values and their ID prefixes for all campaigns: Sunshine on `2026-08-07`, Luga Families on `2026-08-07` and `2026-08-21`, Iron Legion on `2026-08-10` and `2026-08-21`, and Epicfest on `2026-08-14`. Keep each row's date range and characteristics byte-for-byte equivalent.

- [x] **Step 3: Run focused tests and verify success**

Run: `python -m unittest tests.test_fetch_bc_schedule tests.test_gacha_catalog -v`

Expected: all focused tests PASS.

### Task 3: Validate repository outputs

**Files:**
- Verify: `all_gachas_en.json`
- Verify: `gachas_eventos_actualizados_en1.json`
- Verify: `tests/`

**Interfaces:**
- Consumes: corrected catalog, schedule and test suite.
- Produces: parseable JSON and a passing repository test suite.

- [x] **Step 1: Validate JSON and schedule uniqueness**

Run the following:

```powershell
@'
import json
for path in ('all_gachas_en.json', 'gachas_eventos_actualizados_en1.json'):
    json.load(open(path, encoding='utf-8'))
schedule = json.load(open('gachas_eventos_actualizados_en1.json', encoding='utf-8'))['gachas']
assert len({entry['id'] for entry in schedule}) == len(schedule)
print('JSON and gacha IDs validated')
'@ | python -
```

Expected: `JSON and gacha IDs validated`.

- [x] **Step 2: Run the full suite**

Run: `python -m unittest discover -s tests -p "test_*.py" -v`

Expected: PASS.

- [x] **Step 3: Inspect and commit the focused diff**

Run:

```powershell
git diff --check
git diff -- all_gachas_en.json gachas_eventos_actualizados_en1.json tests
git add all_gachas_en.json gachas_eventos_actualizados_en1.json tests
git commit -m "fix: normalize EN gacha banners and pools"
```

Expected: no whitespace errors; only aliases, pool IDs, schedule canonicalization and tests change.
