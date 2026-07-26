# Complete Gacha Unit IDs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fill every unit-bearing banner in `all_gachas_en.json` that currently has no unit IDs, using the latest released EN lineup represented by that banner.

**Architecture:** Rare Capsule lineups come from the latest matching BC Godfat event and retain the existing rarity-separated fields. Event Capsule lineups use the app-supported `gatos_ids` field because their obtainable cats are EX units and must not be mislabeled as Rare, Super Rare, Uber Rare, or Legend Rare. Promotional banners which award no units remain empty.

**Tech Stack:** JSON, Python 3 validation, BC Godfat event data, `cats_data.json`, PONOS/event-capsule reference data.

## Global Constraints

- Modify unit pools in `all_gachas_en.json`; do not alter images, aliases, schedule files, or unrelated banner metadata.
- Preserve 0-based Battle Cats unit IDs.
- Keep `Halloween Party` and `Premium Fair` empty because they award items rather than units.
- Treat the existing `Summer Break Survival Capsules` entry according to its current Castaway banner image.
- Do not add unreleased EN units 869 or 872.

---

### Task 1: Fill empty Rare Capsule pools

**Files:**
- Modify: `all_gachas_en.json`

**Interfaces:**
- Consumes: BC Godfat events `2026-07-20_939`, `2025-10-27_861`, `2025-09-12_1001`, `2025-09-20_1014`, `2025-11-07_926`, `2026-06-26_1052`, and `2026-06-26_1053`.
- Produces: rarity-separated rates and unit ID arrays for Busterfest, Royalfest, both Gals of Summer banners, Halloween Gacha, and both duplicate Best of the Best records.

- [x] **Step 1: Record the current incomplete-entry baseline**

Run:

```powershell
@'
import json
d = json.load(open("all_gachas_en.json", encoding="utf-8"))["gachas"]
for g in d:
    if not any(g.get(k) for k in ("gatos_ids", "rares", "super_rares", "ubers", "legends")):
        print(g["nombre"])
'@ | python -
```

Expected: the currently empty banners are listed, including the seven Rare Capsule records targeted by this task.

- [x] **Step 2: Apply the verified BC Godfat pools**

Update each target's four chance fields and four rarity arrays with the exact values returned by its source event. Map `2025-09-20_1014` to `Gals of Summer Sunshine`, `2025-09-12_1001` to `Gals of Summer Blue Ocean`, `2026-06-26_1052` to `Best of the Best Gacha`, and `2026-06-26_1053` to `Neo Best of the Best Gacha`.

- [x] **Step 3: Verify the Rare Capsule pools**

Run:

```powershell
@'
import json
d = json.load(open("all_gachas_en.json", encoding="utf-8"))["gachas"]
targets = {
    "Busterfest": (25, 24, 46, 0),
    "Royalfest": (25, 17, 14, 11),
    "Gals of Summer Sunshine": (25, 23, 6, 0),
    "Gals of Summer Blue Ocean": (25, 23, 6, 0),
    "Halloween Gacha": (25, 22, 6, 0),
}
for name, counts in targets.items():
    g = next(x for x in d if x["nombre"] == name)
    assert tuple(len(g[k]) for k in ("rares", "super_rares", "ubers", "legends")) == counts
for name in ("Best of the Best Gacha", "Neo Best of the Best Gacha"):
    matches = [x for x in d if x["nombre"] == name]
    assert len(matches) == 2
    assert all(any(x[k] for k in ("rares", "super_rares", "ubers", "legends")) for x in matches)
print("rare capsule pools verified")
'@ | python -
```

Expected: `rare capsule pools verified`.

### Task 2: Fill Event Capsule unit IDs

**Files:**
- Modify: `all_gachas_en.json`

**Interfaces:**
- Consumes: released EN Event Capsule lineups and the app's existing `GachaDetail.gatos_ids` compatibility field.
- Produces: `gatos_ids` for Summer Break Castaway (`765, 766, 767, 813`), Medal King's Palace (`342, 375, 635, 689, 726`), and Summer Break Paradise (`342, 375, 822, 870`).

- [x] **Step 1: Add generic EX-unit pools**

Add the following arrays without changing the zero chance values:

```json
"gatos_ids": [765, 766, 767, 813]
```

for `Summer Break Survival Capsules`;

```json
"gatos_ids": [342, 375, 635, 689, 726]
```

for `Medal King's Palace Capsules`; and

```json
"gatos_ids": [342, 375, 822, 870]
```

for `Summer Break Capsules Paradise`.

- [x] **Step 2: Verify the Event Capsule pools against local unit metadata**

Run:

```powershell
@'
import json
gachas = json.load(open("all_gachas_en.json", encoding="utf-8"))["gachas"]
units = json.load(open("cats_data.json", encoding="utf-8"))["units"]
targets = {
    "Summer Break Survival Capsules": [765, 766, 767, 813],
    "Medal King's Palace Capsules": [342, 375, 635, 689, 726],
    "Summer Break Capsules Paradise": [342, 375, 822, 870],
}
for name, expected in targets.items():
    g = next(x for x in gachas if x["nombre"] == name)
    assert g["gatos_ids"] == expected
    assert all(units[f"{cat_id:03d}"]["info"]["rarity"] == "EX" for cat_id in expected)
print("event capsule pools verified")
'@ | python -
```

Expected: `event capsule pools verified`.

### Task 3: Validate the completed catalog

**Files:**
- Verify: `all_gachas_en.json`

**Interfaces:**
- Consumes: the updated catalog.
- Produces: evidence that the JSON is parseable, IDs are valid and unique within each field, and only non-unit promotional banners remain empty.

- [x] **Step 1: Validate structure, ID bounds, and duplicates**

Run:

```powershell
@'
import json
data = json.load(open("all_gachas_en.json", encoding="utf-8"))
units = json.load(open("cats_data.json", encoding="utf-8"))["units"]
valid = {int(i) for i in units}
fields = ("gatos_ids", "rares", "super_rares", "ubers", "legends")
for g in data["gachas"]:
    for field in fields:
        ids = g.get(field, [])
        assert len(ids) == len(set(ids)), (g["nombre"], field, "duplicate")
        assert set(ids) <= valid, (g["nombre"], field, sorted(set(ids) - valid))
empty = [g["nombre"] for g in data["gachas"] if not any(g.get(k) for k in fields)]
assert empty == ["Halloween Party", "Premium Fair"], empty
print(f'{len(data["gachas"])} banners valid; intentional empty banners: {empty}')
'@ | python -
```

Expected: 55 valid banners and exactly the two intentional item-only banners.

- [x] **Step 2: Review the final diff**

Run:

```powershell
git diff --check
git diff -- all_gachas_en.json
```

Expected: no whitespace errors and only the intended pool/rate/`gatos_ids` changes.
