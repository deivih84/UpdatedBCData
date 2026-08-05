# Summer Break Cats Paradise Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish the correct Summer Break Cats Paradise banner, pool identity and Sunshine Uber Rare rotation.

**Architecture:** The existing Paradise image URL remains stable while its file is replaced with the supplied PNG. Exact aliases let the parser translate `Limited Capsules` to the canonical Event Capsule, and focused tests validate catalog, schedule and unit IDs.

**Tech Stack:** JSON, PNG asset, Python 3 standard-library tests.

## Global Constraints

- Canonical name: `Summer Break Cats Paradise`; aliases retain `Summer Break Capsules Paradise` and `Limited Capsules`.
- Paradise units remain `[342, 375, 822, 870]`.
- Sunshine Ubers are exactly `[820, 666, 563, 438, 354, 275]`; do not retain `714` or `564`.
- Copy `C:\Users\forex\Downloads\Gatya_e_bnr51_en.png` to `images/gacha/banner_gatcha_summer_break_paradise.png`.
- Preserve all unrelated schedule dates, characteristics, pools and assets.

---

### Task 1: Add failing coverage for the corrected capsule and rotation

**Files:**
- Modify: `tests/test_gacha_catalog.py`

**Interfaces:**
- Consumes: `all_gachas_en.json` and `gachas_eventos_actualizados_en1.json`.
- Produces: regression tests for canonical banner resolution, Paradise units and Sunshine's six Ubers.

- [x] **Step 1: Write failing assertions**

Add tests asserting that `Limited Capsules` maps to `Summer Break Cats Paradise`, its `gatos_ids` are `[342, 375, 822, 870]`, Sunshine's `ubers` equal `[820, 666, 563, 438, 354, 275]`, and the schedule contains `summer_break_cats_paradise_2026-08-15`.

- [x] **Step 2: Verify the tests fail**

Run: `python -m unittest tests.test_gacha_catalog -v`

Expected: FAIL because the old canonical name, raw schedule title and incorrect Sunshine values remain.

### Task 2: Correct published data and banner asset

**Files:**
- Modify: `all_gachas_en.json`
- Modify: `gachas_eventos_actualizados_en1.json`
- Modify: `images/gacha/banner_gatcha_summer_break_paradise.png`

**Interfaces:**
- Consumes: supplied PNG at `C:\Users\forex\Downloads\Gatya_e_bnr51_en.png`.
- Produces: a stable raw GitHub image URL, canonical parser aliases and live schedule entry.

- [x] **Step 1: Update catalog JSON**

Rename the existing Paradise entry to `Summer Break Cats Paradise`, add both historical/raw aliases, keep `[342, 375, 822, 870]`, and set Sunshine `ubers` to `[820, 666, 563, 438, 354, 275]`.

- [x] **Step 2: Update schedule and image**

Change the August 15 schedule row to ID `summer_break_cats_paradise_2026-08-15` and name `Summer Break Cats Paradise`; copy the supplied PNG over the existing Paradise banner path.

- [x] **Step 3: Verify focused tests pass**

Run: `python -m unittest tests.test_gacha_catalog -v`

Expected: PASS.

### Task 3: Validate and commit

**Files:**
- Verify: corrected JSON, banner and tests.

**Interfaces:**
- Consumes: changed catalog, schedule, image and tests.
- Produces: valid published game data.

- [x] **Step 1: Run checks**

Run: `python -m json.tool all_gachas_en.json > $null; python -m json.tool gachas_eventos_actualizados_en1.json > $null; python update_cat_animations.py --dry-run; python -m unittest discover -s tests -p "test_*.py" -v`

Expected: JSON parses, zero animation changes and all tests pass.

- [x] **Step 2: Commit the scoped diff**

Run: `git diff --check; git add all_gachas_en.json gachas_eventos_actualizados_en1.json images/gacha/banner_gatcha_summer_break_paradise.png tests/test_gacha_catalog.py; git commit -m "fix: correct summer break paradise banner"`

Expected: only approved data, asset and test changes are committed.
