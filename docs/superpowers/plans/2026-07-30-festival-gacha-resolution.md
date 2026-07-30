# Festival Gacha Resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve Uberfest, Epicfest, and Superfest without treating the advertised cat as the festival identity, and correct the current Uberfest record.

**Architecture:** Extend parsed Ponos entries with their rarity probabilities, then move name resolution from `main()` into a pure helper. The helper keeps ID and alias matching but validates festival candidates against stable probability signatures; only Superfest can be inferred from rates alone because Uberfest and Epicfest share the same rates.

**Tech Stack:** Python 3.12, standard-library `unittest`, JSON, existing `requests` dependency.

## Global Constraints

- Do not use the changing `rares`, `super_rares`, `ubers`, or `legends` arrays to identify a festival.
- Do not add a runtime dependency or external service to the scheduled workflow.
- Keep `1051 → Superfest`; add `1061 → Uberfest`.
- Superfest signature is Super Rare `2500`, Uber Rare `1000`, Legend Rare `30`.
- Uberfest/Epicfest signature is Super Rare `2600`, Uber Rare `900`, Legend Rare `30`.
- If an unknown 9% festival cannot be distinguished as Uberfest or Epicfest, retain the Ponos label instead of guessing.

---

### Task 1: Parse rates and isolate safe festival resolution

**Files:**
- Create: `tests/test_fetch_bc_schedule.py`
- Modify: `fetch_bc_schedule.py:277-320`
- Modify: `fetch_bc_schedule.py:499-549`

**Interfaces:**
- Consumes: `_extract_gacha_entries(cols: list[str]) -> list[dict]`, `_build_entry(name: str, start: str, end: str, characteristics: list[str]) -> dict`
- Produces: `_resolve_gacha_name(entry: dict, by_id: dict[int, str], alias_db: dict[str, str]) -> str | None`
- Produces these entry fields: `rare_chance`, `super_chance`, `uber_chance`, `legend_chance`

- [ ] **Step 1: Create focused parser and resolver tests**

```python
import unittest

import fetch_bc_schedule as schedule


def festival_entry(gacha_id, text, super_chance, uber_chance, legend_chance=30):
    return {
        "gacha_id": gacha_id,
        "tsv_name": text,
        "tsv_full": text,
        "super_chance": super_chance,
        "uber_chance": uber_chance,
        "legend_chance": legend_chance,
    }


class GachaEntryParsingTests(unittest.TestCase):
    def test_extracts_rarity_rates_from_standard_gacha_entry(self):
        title = "Squire Luno added! Special Capsules featuring powerful limited units!"
        cols = [
            "0", "0", "0", "0", "0", "0", "0", "0",  # no date sections
            "1", "1",                                      # type, category count
            "1061", "150", "0", "0",                      # entry header
            "0", "0", "6470", "0", "2600", "0",
            "900", "0", "30", "0", title,
        ]

        entry = schedule._extract_gacha_entries(cols)[0]

        self.assertEqual(entry["rare_chance"], 6470)
        self.assertEqual(entry["super_chance"], 2600)
        self.assertEqual(entry["uber_chance"], 900)
        self.assertEqual(entry["legend_chance"], 30)


class FestivalResolutionTests(unittest.TestCase):
    def test_known_current_pool_resolves_to_uberfest(self):
        entry = festival_entry(
            1061,
            "Squire Luno added! Special Capsules featuring powerful limited units!",
            2600,
            900,
        )

        name = schedule._resolve_gacha_name(
            entry,
            {1061: "Uberfest"},
            {},
        )

        self.assertEqual(name, "Uberfest")
        self.assertEqual(
            schedule._build_entry(name, "2026-07-29", "2026-08-03", [])["id"],
            "uberfest_2026-07-29",
        )

    def test_known_superfest_pool_remains_superfest(self):
        entry = festival_entry(
            1051,
            "New unit Lone Moon Lunos added! Special Capsules featuring powerful limited units!",
            2500,
            1000,
        )

        name = schedule._resolve_gacha_name(
            entry,
            {1051: "Superfest"},
            {},
        )

        self.assertEqual(name, "Superfest")

    def test_rejects_superfest_alias_for_nine_percent_banner(self):
        text = "A new cat! Special Capsules featuring powerful limited units!"
        entry = festival_entry(9999, text, 2600, 900)

        name = schedule._resolve_gacha_name(
            entry,
            {},
            {text.lower(): "Superfest"},
        )

        self.assertEqual(name, text)

    def test_infers_superfest_from_rates_when_featured_cat_changes(self):
        text = "Unknown future cat added! Special Capsules featuring powerful limited units!"
        entry = festival_entry(9998, text, 2500, 1000)

        name = schedule._resolve_gacha_name(entry, {}, {})

        self.assertEqual(name, "Superfest")

    def test_does_not_guess_between_unknown_uberfest_and_epicfest(self):
        text = "Unknown future cat added! Special Capsules featuring powerful limited units!"
        entry = festival_entry(9997, text, 2600, 900)

        name = schedule._resolve_gacha_name(entry, {}, {})

        self.assertEqual(name, text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the new tests and verify RED**

Run: `python -m unittest tests.test_fetch_bc_schedule -v`

Expected: the parser assertion fails because the rate fields do not exist, and resolver tests error because `_resolve_gacha_name` does not exist.

- [ ] **Step 3: Add parsed rate fields**

Inside `_extract_gacha_entries()`, read the alternating rate/guarantee fields:

```python
rare_chance   = int(cols[idx + 6])
super_chance  = int(cols[idx + 8])
uber_chance   = int(cols[idx + 10])
legend_chance = int(cols[idx + 12])
```

Add them to the returned entry:

```python
"rare_chance":   rare_chance,
"super_chance":  super_chance,
"uber_chance":   uber_chance,
"legend_chance": legend_chance,
```

- [ ] **Step 4: Add pure festival validation and resolution**

Place these helpers after `_load_name_dbs()`:

```python
FESTIVAL_RATE_SIGNATURES = {
    "Superfest": (2500, 1000, 30),
    "Uberfest": (2600, 900, 30),
    "Epicfest": (2600, 900, 30),
}
SPECIAL_FESTIVAL_TEXT = "special capsules featuring powerful limited units"


def _festival_rate_matches(name, entry):
    expected = FESTIVAL_RATE_SIGNATURES.get(name)
    if expected is None:
        return True
    actual = (
        entry.get("super_chance"),
        entry.get("uber_chance"),
        entry.get("legend_chance"),
    )
    return actual == expected


def _resolve_gacha_name(entry, by_id, alias_db):
    def valid(candidate):
        return candidate if candidate and _festival_rate_matches(candidate, entry) else None

    canonical = valid(by_id.get(entry["gacha_id"]))

    if canonical is None:
        tsv_full = entry.get("tsv_full", "")
        if tsv_full:
            canonical = valid(alias_db.get(tsv_full.lower()))

    if canonical is None:
        tsv_name = entry.get("tsv_name", "")
        if tsv_name:
            canonical = valid(alias_db.get(tsv_name.lower()))

    if canonical is None:
        tsv_full_lower = entry.get("tsv_full", "").lower()
        best_match_len = 0
        for alias_lower, candidate in alias_db.items():
            if len(alias_lower) < 8:
                continue
            if (tsv_full_lower.startswith(alias_lower)
                    or alias_lower.startswith(tsv_full_lower)
                    or alias_lower in tsv_full_lower
                    or tsv_full_lower in alias_lower):
                candidate = valid(candidate)
                if candidate and len(alias_lower) > best_match_len:
                    best_match_len = len(alias_lower)
                    canonical = candidate

    tsv_full_lower = entry.get("tsv_full", "").lower()
    if (canonical is None
            and SPECIAL_FESTIVAL_TEXT in tsv_full_lower
            and _festival_rate_matches("Superfest", entry)):
        canonical = "Superfest"

    if canonical is None:
        canonical = entry.get("tsv_name") or None

    return canonical if canonical and _is_valid_name(canonical) else None
```

Replace the five resolution-priority blocks and final validity check inside `main()` with:

```python
canonical = _resolve_gacha_name(entry, by_id, alias_db)
if canonical is None:
    continue
```

- [ ] **Step 5: Run focused tests and verify GREEN**

Run: `python -m unittest tests.test_fetch_bc_schedule -v`

Expected: six tests pass.

- [ ] **Step 6: Run the existing test suite**

Run: `python -m unittest discover -s tests -v`

Expected: all existing and new tests pass with no errors.

- [ ] **Step 7: Commit the resolver change**

```bash
git add fetch_bc_schedule.py tests/test_fetch_bc_schedule.py
git commit -m "fix: validate festival gachas by rates"
```

### Task 2: Register the current Uberfest and repair live output

**Files:**
- Modify: `gacha_id_cache.json`
- Modify: `all_gachas_en.json`
- Modify: `gachas_eventos_actualizados_en1.json`
- Test: `tests/test_fetch_bc_schedule.py`

**Interfaces:**
- Consumes: `_load_name_dbs() -> tuple[dict[int, str], dict[str, str]]`
- Consumes: `_resolve_gacha_name(entry, by_id, alias_db) -> str | None`
- Produces: persistent mapping `1061 → Uberfest`

- [ ] **Step 1: Add a failing integration test against repository data**

Append to `FestivalResolutionTests`:

```python
    def test_repository_catalog_resolves_current_and_previous_festivals(self):
        by_id, alias_db = schedule._load_name_dbs()
        current = festival_entry(
            1061,
            "Squire Luno added! Special Capsules featuring powerful limited units!",
            2600,
            900,
        )
        previous = festival_entry(
            1051,
            "New unit Lone Moon Lunos added! Special Capsules featuring powerful limited units!",
            2500,
            1000,
        )

        self.assertEqual(
            schedule._resolve_gacha_name(current, by_id, alias_db),
            "Uberfest",
        )
        self.assertEqual(
            schedule._resolve_gacha_name(previous, by_id, alias_db),
            "Superfest",
        )
```

- [ ] **Step 2: Run the repository-data test and verify RED**

Run: `python -m unittest tests.test_fetch_bc_schedule.FestivalResolutionTests.test_repository_catalog_resolves_current_and_previous_festivals -v`

Expected: FAIL because ID `1061` is absent and the current exact Ponos text is not an Uberfest alias.

- [ ] **Step 3: Update persistent festival mappings**

Add to `gacha_id_cache.json` in numeric order:

```json
"1061": "Uberfest"
```

Keep the existing line:

```json
"1051": "Superfest"
```

Update Uberfest aliases in `all_gachas_en.json` to:

```json
"aliases": [
  "New unit Squire Luno added! ★Uber Rare drop rate UP!",
  "Squire Luno added! Special Capsules featuring powerful limited units!"
]
```

Do not add a featured-cat alias to Superfest.

- [ ] **Step 4: Correct the current output identifier**

In the entry beginning on `2026-07-29`, change only:

```json
"id": "uberfest_2026-07-29",
"nombre": "Uberfest"
```

Keep `fecha_inicio`, `fecha_fin`, and `caracteristicas` unchanged.

- [ ] **Step 5: Run the repository-data test and verify GREEN**

Run: `python -m unittest tests.test_fetch_bc_schedule.FestivalResolutionTests.test_repository_catalog_resolves_current_and_previous_festivals -v`

Expected: PASS.

- [ ] **Step 6: Validate JSON and all tests**

Run:

```powershell
python -m json.tool gacha_id_cache.json > $null
python -m json.tool all_gachas_en.json > $null
python -m json.tool gachas_eventos_actualizados_en1.json > $null
python -m unittest discover -s tests -v
git diff --check
```

Expected: every command exits with code `0`; all tests pass; `git diff --check` prints nothing.

- [ ] **Step 7: Perform a network-backed dry diagnostic**

Fetch and parse current Ponos data without calling `main()` or writing the schedule. Select ID `1061`, pass it to `_resolve_gacha_name()`, and print the resolved name and built ID.

Expected:

```text
Uberfest
uberfest_2026-07-29
```

- [ ] **Step 8: Commit data corrections**

```bash
git add gacha_id_cache.json all_gachas_en.json gachas_eventos_actualizados_en1.json tests/test_fetch_bc_schedule.py
git commit -m "fix: map current Uberfest pool correctly"
```

### Task 3: Final verification

**Files:**
- Verify: `fetch_bc_schedule.py`
- Verify: `tests/test_fetch_bc_schedule.py`
- Verify: `gacha_id_cache.json`
- Verify: `all_gachas_en.json`
- Verify: `gachas_eventos_actualizados_en1.json`

**Interfaces:**
- Consumes the completed resolver and persistent data mappings.
- Produces verification evidence only; no production changes.

- [ ] **Step 1: Run syntax compilation**

Run: `python -m py_compile fetch_bc_schedule.py`

Expected: exit code `0` with no output.

- [ ] **Step 2: Run the complete test suite**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 3: Inspect committed scope**

Run:

```powershell
git status --short
git log -3 --oneline
git show --stat --oneline HEAD~1..HEAD
```

Expected: only any pre-existing `.bc_state.json` refresh remains uncommitted; the resolver and data commits contain only the planned files.
