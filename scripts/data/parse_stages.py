"""
Parse BCData stage files and generate stages_data.json for the CatStats app.

Correct file mappings (verified against BCData 15.1.0en):
  - EoC: stageNormal0.csv (energy) + StageName_DM_en.csv (names), no enemy CSVs
  - ItF: stageW04/05/06 + StageName0_en.csv + MapStageDataB_000-002
  - CotC: stageSpace07/08/09 + StageName2_en.csv + MapStageDataB_003-005
  - Aku Realms: stageDM000 + StageName_DM_en.csv + MapStageDataDM_000
  - SoL: stageRN + StageName_RN_en.csv + MapStageDataN (maps 0-48)
  - UL: stageRNA + StageName_RNA_en.csv + MapStageDataNA (maps 13000-13048)
  - ZL: stageRND + StageName_RND_en.csv + MapStageDataND (maps 34000-34026)
  - Special/Catamin: stageRB + StageName_RB_en.csv + MapStageDataB (maps 14000+)
  - Events: stageRS + StageName_RS_en.csv + MapStageDataS (maps 1000+)
  - Gauntlets & Strikes: stageRA + StageName_RE_en.csv + MapStageDataRE (maps 24000+)

CRITICAL: Enemy IDs in stage CSV files are offset by +2 from Enemyname.tsv
indices. The game reserves IDs 0,1 for the cat base.
So: real_enemy_index = stage_file_id - 2
"""
# Both direct invocation and python -m work from any current directory.
import os as _workspace_os
import sys as _workspace_sys
from pathlib import Path as _WorkspacePath
if __package__ in (None, ''):
    _workspace_sys.path.insert(0, str(_WorkspacePath(__file__).resolve().parents[2]))
from workspace_paths import Workspace, latest_version_dir, run_generator
paths = Workspace.load(_workspace_os.environ.get('UPDATED_BCDATA_ROOT'))

import os
import json
import re
import csv
from datetime import datetime

BCDATA_ROOT = str(paths.bcdata)


def find_latest_en_dir(root=BCDATA_ROOT):
    """Return the newest extracted EN data directory by semantic version."""
    return str(latest_version_dir(_WorkspacePath(root), 'en'))


EN_DIR = JP_DIR = DATA_LOCAL = RES_LOCAL = None

def configure_sources():
    global EN_DIR, JP_DIR, DATA_LOCAL, RES_LOCAL
    EN_DIR = find_latest_en_dir()
    # JP may be ahead of EN; select independently.
    try:
        JP_DIR = str(latest_version_dir(paths.bcdata, 'jp'))
    except FileNotFoundError:
        JP_DIR = EN_DIR[:-2] + 'jp'
    DATA_LOCAL = os.path.join(EN_DIR, 'DataLocal')
    RES_LOCAL = os.path.join(EN_DIR, 'resLocal')
    if not os.path.isdir(RES_LOCAL):
        raise FileNotFoundError(f'Stage generation requires {RES_LOCAL}')

OUTPUT_APP = str(paths.data / 'stages_data.json')
OUTPUT_REMOTE = str(paths.root / 'stages_data.json')

ENEMY_ID_OFFSET = 2  # Subtract from stage file enemy IDs to get real index


# ======================== DATA LOADERS ========================

def load_item_names():
    """Load item display names from GatyaitemName.csv. Line index = item ID."""
    path = os.path.join(RES_LOCAL, "GatyaitemName.csv")
    names = {}
    if not os.path.exists(path):
        return names
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            parts = line.strip().split("|")
            if parts and parts[0].strip():
                names[i] = parts[0].strip()
    return names


def _unit_form_name(cat_id, form_idx):
    """Return the name of form `form_idx` (0=first, 1=second, 2=true, 3=ultra)
    for app cat ID `cat_id`. Unit_Explanation files are 1-based."""
    path = os.path.join(RES_LOCAL, f"Unit_Explanation{cat_id + 1}_en.csv")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        forms = [ln.split("|")[0].strip() for ln in f if ln.strip()]
    if not forms:
        return None
    # Clamp to available forms
    idx = min(form_idx, len(forms) - 1)
    return forms[idx]


def load_cat_drop_rewards():
    """Build stageDropItemID -> cat reward metadata.

    BCData stage rewards store app cat IDs as 0-based values, while
    Unit_Explanation filenames are 1-based. Keep the app ID in the JSON for
    icon lookup and add 1 only when reading names from Unit_Explanation.
    """
    result = {}

    # --- True/Ultra form unlocks from unitbuy.csv column 24 (0-indexed col 23) ---
    unitbuy_path = os.path.join(DATA_LOCAL, "unitbuy.csv")
    if os.path.exists(unitbuy_path):
        with open(unitbuy_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, start=1):
                parts = line.strip().split(",")
                if len(parts) < 24:
                    continue
                try:
                    drop_id = int(parts[23])
                except ValueError:
                    continue
                if drop_id <= 0:
                    continue
                cat_id = line_num - 1
                if 10000 < drop_id < 15000:
                    form_idx = 2   # True Form (3rd form)
                elif 15000 <= drop_id < 19000:
                    form_idx = 3   # Ultra Form (4th form)
                else:
                    continue
                name = _unit_form_name(cat_id, form_idx)
                if name:
                    result[drop_id] = {
                        "name": name,
                        "catId": cat_id,
                        "catForm": form_idx + 1,
                    }

    # --- Free cat gifts from drop_chara.csv (IDs 1000-1999) ---
    drop_chara_path = os.path.join(DATA_LOCAL, "drop_chara.csv")
    if os.path.exists(drop_chara_path):
        with open(drop_chara_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                if i == 0:  # skip header
                    continue
                parts = line.strip().split(",")
                if len(parts) < 3:
                    continue
                try:
                    drop_id = int(parts[0])
                    cat_id = int(parts[2])
                except ValueError:
                    continue
                if drop_id <= 0:
                    continue
                name = _unit_form_name(cat_id, 0)  # base form
                if name:
                    result[drop_id] = {
                        "name": name,
                        "catId": cat_id,
                        "catForm": 1,
                    }

    return result


# Medals that have no English name in medalname.tsv (newer game content).
# Key = line index in medalname.tsv.
_HARDCODED_MEDAL_NAMES = {
    50: {"name": "★ Floor 30 ★", "description": "Clear the 30th floor of Heavenly Tower"},
    51: {"name": "★ Floor 40 ★", "description": "Clear the 40th floor of Heavenly Tower"},
    52: {"name": "★ A True Master ★", "description": "Complete the FINAL LEVEL of Legend Quest."},
    79: {"name": "★ Floor 50 ★", "description": "Clear the 50th floor of Heavenly Tower"},
    93: {"name": "★ Inferno 30 ★", "description": "Clear Floor 30 of the Infernal Tower"},
    102: {"name": "★ Inferno 40 ★", "description": "Clear Floor 40 of the Infernal Tower"},
    113: {"name": "★ Inferno 50 ★", "description": "Clear Floor 50 of the Infernal Tower"},
    120: {"name": "★ Underground B100F ★", "description": "Clear Underground Labyrinth B100F"},
}

# Medals referencing more unique positive map IDs than this threshold are
# considered "broad" (e.g. "complete all SoL stages") and need a cond.map
# value to narrow them down to a specific subchapter.
_MANY_MAPS_THRESHOLD = 5

_MEDAL_LOCATION_OVERRIDES = {
    # Hidden/synthetic medal maps not represented as standalone app subchapters.
    14: [3008],    # Filibuster Obstructa -> CotC Ch. 3
    63: [26],      # Ururun Wolf -> Prisoner of Brush
    84: [1237],    # Total War all-season medal -> Winter Special
    86: [48],      # Idi:Re unlock condition -> Laboratory of Relics
    90: [30000],   # The Aku Realms is built by a custom story builder.
    114: [34008],  # Soractes is awarded in Garden of Wilted Thoughts; condition.map is the prerequisite.
    118: [13048],  # Nova unlock condition -> Sacred Forest
    121: [34019],  # Newton is awarded in Truth's Devouring Maw; condition.map is the prerequisite.
    124: [3008],   # Filibuster Zombie -> CotC Ch. 3
    126: [34030],  # Darvin is awarded in Eden of Evolution; condition.map is the prerequisite.
}


def load_medal_names():
    """Load medal display names. List index equals medal image index."""
    names_path = os.path.join(RES_LOCAL, "medalname.tsv")

    medal_names = []
    if os.path.exists(names_path):
        with open(names_path, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                name = parts[0].strip() if parts else ""
                desc = parts[1].strip() if len(parts) > 1 else ""
                medal_names.append({"name": name, "description": desc})
    return medal_names


def _resolve_medal_info(icon_idx, medal_names):
    if icon_idx in _HARDCODED_MEDAL_NAMES:
        info = _HARDCODED_MEDAL_NAMES[icon_idx]
    elif icon_idx < len(medal_names):
        info = medal_names[icon_idx]
    else:
        info = {"name": "", "description": ""}

    return {
        "name": info["name"],
        "description": info["description"].replace("<br>", " ").replace("<br/>", " ").strip(),
    }


def _positive_medal_maps(map_ids):
    maps = []
    for map_id in map_ids:
        if map_id >= 0:
            maps.append(map_id)
        elif map_id <= -1000:
            maps.append(abs(map_id))
    return maps


def _condition_maps(condition):
    maps = condition.get("map")
    if isinstance(maps, list):
        return [m for m in maps if isinstance(m, int) and m >= 0]
    return []


def _effective_medal_maps(icon_idx, map_ids, condition):
    if icon_idx in _MEDAL_LOCATION_OVERRIDES:
        return _MEDAL_LOCATION_OVERRIDES[icon_idx]

    positive_maps = _positive_medal_maps(map_ids)
    cond_maps = _condition_maps(condition)

    if positive_maps:
        if len(positive_maps) > _MANY_MAPS_THRESHOLD:
            return [max(positive_maps)]
        return positive_maps

    if cond_maps:
        if len(cond_maps) > _MANY_MAPS_THRESHOLD:
            return [max(cond_maps)]
        return cond_maps

    return []


def build_medal_catalog():
    """Parse medallist.json + medalname.tsv.
    Returns a list of all named medals ordered by image/index number."""
    list_path = os.path.join(DATA_LOCAL, "medallist.json")
    medal_names = load_medal_names()

    if not os.path.exists(list_path):
        return []

    with open(list_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    catalog = []
    for icon_idx, entry in enumerate(data.get("iconID", [])):
        info = _resolve_medal_info(icon_idx, medal_names)
        if not info["name"]:
            continue

        medal_obj = {
            "name": info["name"],
            "description": info["description"],
            "grade": entry.get("grade", 0),
            "iconIdx": icon_idx,
        }
        int_condition = {
            k: v for k, v in entry.get("condition", {}).items()
            if isinstance(v, int)
        }
        if int_condition:
            medal_obj["condition"] = int_condition
        catalog.append(medal_obj)

    return catalog


def load_medals():
    """Parse medallist.json + medalname.tsv.
    Returns dict: game_map_id -> list of medal dicts."""
    list_path = os.path.join(DATA_LOCAL, "medallist.json")
    medal_names = load_medal_names()

    medals_by_mapid = {}
    if not os.path.exists(list_path):
        return medals_by_mapid

    with open(list_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for icon_idx, entry in enumerate(data.get("iconID", [])):
        grade = entry.get("grade", 0)
        map_ids = entry.get("map", [])
        condition = entry.get("condition", {})

        info = _resolve_medal_info(icon_idx, medal_names)
        if not info["name"]:
            continue  # Skip medals with no English name (newer version / unreleased)

        effective_maps = _effective_medal_maps(icon_idx, map_ids, condition)

        if not effective_maps:
            continue

        medal_obj = {
            "name": info["name"],
            "description": info["description"],
            "grade": grade,
            "iconIdx": icon_idx,
        }
        # Build int-only condition dict (Kotlin model Map<String,Int> can't hold lists)
        int_condition = {k: v for k, v in condition.items() if isinstance(v, int)}
        if int_condition:
            medal_obj["condition"] = int_condition

        for map_id in effective_maps:
            medals_by_mapid.setdefault(map_id, []).append(medal_obj)

    return medals_by_mapid


def load_enemy_names():
    """Load enemy names from Enemyname.tsv. Line index = enemy ID."""
    path = os.path.join(RES_LOCAL, "Enemyname.tsv")
    names = {}
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            name = line.strip()
            if name:
                names[i] = name
    return names


def load_map_names():
    """Load map names from Map_Name.csv. Returns dict: mapId -> name."""
    path = os.path.join(RES_LOCAL, "Map_Name.csv")
    names = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("|", 1)
            if len(parts) >= 2:
                try:
                    names[int(parts[0])] = parts[1]
                except ValueError:
                    pass
    return names


def load_map_options():
    """Load crown/star difficulty data from Map_option.csv.
    Returns dict: mapId -> {maxCrowns, mult2, mult3, mult4}
    Columns: stageID, 星解放(maxCrowns), 裏星解放, 星1倍率, 星2倍率, 星3倍率, 星4倍率, ...
    Multiplier values are stored ×100 (e.g. 150 = 1.5×).
    """
    path = os.path.join(DATA_LOCAL, "Map_option.csv")
    options = {}
    if not os.path.exists(path):
        return options
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i == 0:  # skip header
                continue
            parts = [p.strip() for p in line.strip().split(",")]
            if len(parts) < 7:
                continue
            try:
                map_id = int(parts[0])
                max_crowns = int(parts[1])
                # parts[2] = 裏星解放 (skip), parts[3] = 星1倍率 (always 100)
                mult2 = round(int(parts[4]) / 100.0, 2)
                mult3 = round(int(parts[5]) / 100.0, 2)
                mult4 = round(int(parts[6]) / 100.0, 2)
                options[map_id] = {
                    "maxCrowns": max_crowns,
                    "mult2": mult2,
                    "mult3": mult3,
                    "mult4": mult4,
                }
            except (ValueError, IndexError):
                continue
    return options


def load_charagroups():
    """Load Charagroup.csv: group_id -> {groupId, type, catIds}.
    group_type 0 = must use these cats; 2 = banned cats.
    """
    path = os.path.join(DATA_LOCAL, "Charagroup.csv")
    groups = {}
    if not os.path.exists(path):
        return groups
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("//"):
                continue
            parts = [p.strip() for p in line.strip().rstrip(",").split(",")]
            if len(parts) < 4:
                continue
            try:
                group_id = int(parts[0])
                group_type = int(parts[2])
                cat_ids = []
                for p in parts[3:]:
                    if p:
                        try:
                            cid = int(p)
                            if cid > 0:
                                cat_ids.append(cid)
                        except ValueError:
                            pass
                groups[group_id] = {"groupId": group_id, "type": group_type, "catIds": cat_ids}
            except (ValueError, IndexError):
                continue
    return groups


def load_stage_options(charagroups):
    """Load Stage_option.csv: {map_id: {star_idx: {stage_id: restriction_dict}}}.
    star_idx: 0=crown1, 1=crown2, 2=crown3, 3=crown4, -1=all crowns (Colosseum).
    stage_id: -1=all stages in map, >=0=specific stage.
    Columns: mapID, 対応★, stageID, rarityMask, maxCats, maxSlots, minCost, maxCost, groupID.
    """
    path = os.path.join(DATA_LOCAL, "Stage_option.csv")
    options = {}
    if not os.path.exists(path):
        return options
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("//"):
                continue
            parts = [p.strip() for p in line.strip().rstrip(",").split(",")]
            if len(parts) < 8:
                continue
            try:
                map_id = int(parts[0])
                star = int(parts[1])
                stage_id = int(parts[2])
                rarity_mask = int(parts[3])
                max_cats = int(parts[4])
                max_slots = int(parts[5])
                min_cost = int(parts[6])
                max_cost = int(parts[7])
                group_id = int(parts[8]) if len(parts) > 8 and parts[8] else 0
            except (ValueError, IndexError):
                continue

            restr = {}
            if rarity_mask:
                restr["rarityMask"] = rarity_mask
            if max_cats:
                restr["maxCats"] = max_cats
            if max_slots:
                restr["maxSlots"] = max_slots
            if min_cost:
                restr["minCost"] = min_cost
            if max_cost:
                restr["maxCost"] = max_cost
            if group_id and group_id in charagroups:
                restr["colosseumGroup"] = charagroups[group_id]

            if not restr:
                continue

            options.setdefault(map_id, {}).setdefault(star, {})[stage_id] = restr

    return options


def load_stage_names_file(filename):
    """Load pipe-separated stage names. Each line = one map's stages.
    Returns [] if filename is empty/None (stages will fall back to 'Stage N' names)."""
    if not filename:
        return []
    path = os.path.join(RES_LOCAL, filename)
    if not os.path.exists(path):
        return []
    result = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            names = [n for n in line.strip().split("|") if n and n != "\uff20"]
            result.append(names)
    return result


# ======================== CSV PARSING ========================

def parse_csv_line(line):
    """Parse a CSV line, stripping comments after //."""
    pos = line.find("//")
    if pos >= 0:
        line = line[:pos]
    parts = [p.strip() for p in line.strip().rstrip(",").split(",")]
    return [p for p in parts if p != ""]


def parse_stage_file(filepath, has_castle_line=True):
    """
    Parse a stage data file.
    If has_castle_line=True (stageRN, stageRNA, stageRND, stageDM, stageRS):
        Line 0: castle config (城番号 = castle/base sprite ID)
        Line 1: stage header (width, baseHp, ..., maxEnemies, ...)
        Lines 2+: enemy entries
    If has_castle_line=False (stageW for ItF, stageSpace for CotC):
        Line 0: stage header directly
        Lines 1+: enemy entries

    Enemy IDs are adjusted by -ENEMY_ID_OFFSET to get real enemy index.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    data_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("//"):
            data_lines.append(stripped)

    min_lines = 2 if has_castle_line else 1
    if len(data_lines) < min_lines:
        return None

    # Extract castle ID and optional EX/continuation destination from line 0.
    # R-type stage header:
    # castleId, noContinues, EX chance, EX map, min EX stage, max EX stage.
    castle_id = -1
    continuation = None
    if has_castle_line:
        castle_parts = parse_csv_line(data_lines[0])
        if castle_parts:
            try:
                castle_id = int(castle_parts[0])
            except ValueError:
                castle_id = -1
        if len(castle_parts) >= 6:
            try:
                chance = int(castle_parts[2])
                if chance > 0:
                    continuation = {
                        "chance": chance,
                        "mapId": int(castle_parts[3]),
                        "minStage": int(castle_parts[4]),
                        "maxStage": int(castle_parts[5]),
                    }
            except ValueError:
                continuation = None

    # Header line depends on file format
    header_idx = 1 if has_castle_line else 0
    enemy_start = 2 if has_castle_line else 1

    header = parse_csv_line(data_lines[header_idx])
    if len(header) < 6:
        return None

    try:
        stage_width = int(header[0])
        base_hp = int(header[1])
        max_enemies = int(header[5])
    except (ValueError, IndexError):
        return None

    enemies = []
    for i in range(enemy_start, len(data_lines)):
        parts = parse_csv_line(data_lines[i])
        if len(parts) < 9:
            continue
        try:
            raw_id = int(parts[0])
            if raw_id < ENEMY_ID_OFFSET:
                continue
            enemy_id = raw_id - ENEMY_ID_OFFSET
            enemy_count = int(parts[1])
            start_frame = int(parts[2]) if len(parts) > 2 else 0
            min_respawn = int(parts[3]) if len(parts) > 3 else 0
            max_respawn = int(parts[4]) if len(parts) > 4 else 0
            base_hp_pct = int(parts[5]) if len(parts) > 5 else 100
            boss_flag = int(parts[8])
            magnification = int(parts[9]) if len(parts) > 9 else 100

            enemies.append({
                "id": enemy_id,
                "count": enemy_count,
                "boss": boss_flag != 0,
                "magnification": magnification,
                "startFrame": start_frame,
                "minRespawn": min_respawn,
                "maxRespawn": max_respawn,
                "baseHpPercent": base_hp_pct,
            })
        except (ValueError, IndexError):
            continue

    result = {
        "stageWidth": stage_width,
        "baseHp": base_hp,
        "maxEnemies": max_enemies,
        "enemies": enemies,
    }
    if castle_id >= 0:
        result["castleId"] = castle_id
    if continuation is not None:
        result["_continuation"] = continuation
    return result


def load_continuation_stage_names():
    """Load EX-stage names, filling EN gaps from the matching JP dataset.

    A few old collaboration EX stages are blank in the EN resource while the
    same game version's JP table contains the shipped fallback name.
    """
    english = load_stage_names_file("StageName_RE_en.csv")
    jp_path = os.path.join(JP_DIR, "resLocal", "StageName_RE_ja.csv")
    if not os.path.exists(jp_path):
        return english

    japanese = []
    with open(jp_path, "r", encoding="utf-8") as f:
        for row in csv.reader(f):
            japanese.append(
                [
                    name.strip()
                    for name in row
                    if name.strip() and name.strip() != "＠"
                ]
            )

    result = []
    for map_id in range(max(len(english), len(japanese))):
        primary = english[map_id] if map_id < len(english) else []
        fallback = japanese[map_id] if map_id < len(japanese) else []
        result.append(primary if primary else fallback)
    return result


def resolve_stage_continuation(reference, _active=None, _cache=None):
    """Resolve a stage header EX reference into full continuation stage data.

    Continuation payloads use stageEX files, StageName_RE_en.csv and
    MapStageDataRE files. EX stages may point to another EX map, so resolution
    is recursive. Missing or cyclic payloads abort generation rather than
    publishing silently incomplete stage data.
    """
    chance = int(reference["chance"])
    map_id = int(reference["mapId"])
    min_stage = int(reference["minStage"])
    max_stage = int(reference["maxStage"])
    if chance <= 0 or chance > 100:
        raise ValueError(f"Invalid continuation chance {chance}% for EX map {map_id:03d}")
    if min_stage < 0 or max_stage < min_stage:
        raise ValueError(
            f"Invalid continuation stage range {min_stage}..{max_stage} "
            f"for EX map {map_id:03d}"
        )

    key = (chance, map_id, min_stage, max_stage)
    active = set() if _active is None else _active
    cache = {} if _cache is None else _cache
    if key in cache:
        return cache[key]
    if key in active:
        raise ValueError(f"Cyclic continuation reference at EX map {map_id:03d}")
    active.add(key)

    names_data = load_continuation_stage_names()
    names = names_data[map_id] if map_id < len(names_data) else []
    meta_path = os.path.join(DATA_LOCAL, f"MapStageDataRE_{map_id:03d}.csv")
    if not os.path.exists(meta_path):
        raise ValueError(f"Missing continuation metadata: {os.path.basename(meta_path)}")
    meta = parse_map_stage_data(meta_path)

    stages = []
    for stage_n in range(min_stage, max_stage + 1):
        stage_path = os.path.join(DATA_LOCAL, f"stageEX{map_id:03d}_{stage_n:02d}.csv")
        if not os.path.exists(stage_path):
            raise ValueError(f"Missing continuation payload: {os.path.basename(stage_path)}")
        data = parse_stage_file(stage_path)
        if not data:
            raise ValueError(f"Invalid continuation payload: {os.path.basename(stage_path)}")
        nested_ref = data.pop("_continuation", None)
        if stage_n >= len(names) or not names[stage_n]:
            raise ValueError(
                f"Missing continuation name for EX map {map_id:03d}, stage {stage_n:02d}"
            )
        if stage_n >= len(meta):
            raise ValueError(
                f"Missing continuation metadata row for EX map {map_id:03d}, "
                f"stage {stage_n:02d}"
            )
        stage_meta = meta[stage_n]
        stage_obj = {
            "index": stage_n,
            "name": names[stage_n],
            "energy": stage_meta["energy"],
            "xp": stage_meta["xp"],
            "rewards": stage_meta.get("rewards", []),
            **data,
        }
        if nested_ref is not None:
            stage_obj["continuation"] = resolve_stage_continuation(
                nested_ref, active, cache
            )
        stages.append(stage_obj)

    active.remove(key)
    result = {"chance": chance, "stages": stages}
    cache[key] = result
    return result


def parse_stage_rewards(parts, start_idx=5):
    """
    Parse drop rewards from a MapStageData row.
    Format after the 5 fixed fields: [chance, itemID, count, (-3 separator)?, ...] -1
    -3 can appear as a separator between reward groups and should be skipped.
    Any other negative value (except -1) is also skipped.
    """
    rewards = []
    i = start_idx
    while i < len(parts):
        try:
            val = int(parts[i])
        except (ValueError, IndexError):
            break
        if val == -1:
            break
        elif val <= 0:  # 0, -3 or other separator — skip (0 is used as group separator in catfruit stages)
            i += 1
            continue
        # val = drop chance (0-100 %)
        if i + 2 < len(parts):
            try:
                item_id = int(parts[i + 1])
                count = int(parts[i + 2])
                if item_id >= 0:
                    rewards.append({"chance": val, "id": item_id, "count": count})
            except (ValueError, IndexError):
                pass
            i += 3
        else:
            break
    return rewards


def parse_map_bg_id(filepath):
    """Extract map background ID from a MapStageData file.
    It's the first value of the first non-empty/non-comment line (マップ番号)."""
    if not os.path.exists(filepath):
        return -1
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith("//"):
                continue
            parts = parse_csv_line(stripped)
            if parts:
                try:
                    return int(parts[0])
                except ValueError:
                    return -1
    return -1


def parse_map_stage_data(filepath):
    """
    Parse a MapStageData file. Skip first 2 non-empty lines (headers).
    Returns list of {energy, xp} per stage.
    """
    if not os.path.exists(filepath):
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    stages = []
    data_idx = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        data_idx += 1
        if data_idx <= 2:
            continue
        parts = parse_csv_line(stripped)
        if len(parts) >= 2:
            try:
                stages.append({
                    "energy": int(parts[0]),
                    "xp": int(parts[1]),
                    "rewards": parse_stage_rewards(parts, 5),
                })
            except ValueError:
                continue
    return stages


def parse_stage_normal_energy(filepath):
    """
    Parse energy from stageNormal CSV files (ItF/CotC/EoC map config).
    Format: First 2 non-empty lines are headers, then per-stage data where
    field 0 = energy cost.
    Returns list of energy values per stage.
    """
    if not os.path.exists(filepath):
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    energies = []
    data_idx = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        data_idx += 1
        if data_idx <= 2:
            continue
        parts = parse_csv_line(stripped)
        if parts:
            try:
                val = int(parts[0])
                if val < 0:  # terminator line (-1)
                    continue
                energies.append(val)
            except ValueError:
                continue
    return energies


def parse_stageNormal_itf_cotc(filepath):
    """
    Parse energy AND rewards from stageNormal1_X.csv / stageNormal2_X.csv.
    Format:
      - First 2 non-empty lines are headers (skipped)
      - Each stage line: field 0 = energy, fields 16+ = reward triplets
      - Reward triplets: (chance_raw, item_id, count), terminated by -1
      - Actual chance % = chance_raw // 100
    Returns list of {energy, rewards} per stage.
    """
    if not os.path.exists(filepath):
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    stages = []
    data_idx = 0
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("//"):
            continue
        data_idx += 1
        if data_idx <= 2:
            continue
        parts = parse_csv_line(stripped)
        if not parts:
            continue
        try:
            energy = int(parts[0])
            if energy < 0:
                continue
        except ValueError:
            continue

        # Rewards start at field index 16, chance expressed as raw/100
        rewards = []
        i = 16
        while i < len(parts):
            try:
                raw = int(parts[i])
            except (ValueError, IndexError):
                break
            if raw == -1:
                break
            if raw <= 0:
                i += 1
                continue
            if i + 2 < len(parts):
                try:
                    item_id = int(parts[i + 1])
                    count = int(parts[i + 2])
                    chance = raw // 100
                    if item_id >= 0 and chance > 0:
                        rewards.append({"chance": chance, "id": item_id, "count": count})
                except (ValueError, IndexError):
                    pass
                i += 3
            else:
                break

        stages.append({"energy": energy, "rewards": rewards})
    return stages


# ======================== GENERIC R-TYPE BUILDER ========================

def build_r_chapter(chapter_id, chapter_name, base_map_id,
                    stage_prefix, stage_name_file, map_data_prefix, map_names,
                    map_options=None, stage_options=None, medals_by_mapid=None,
                    fallback_name_from_stage=False):
    """
    Build chapter from R-type files (stageRN, stageRNA, stageRND, stageRS).
    Each stage has its own CSV: stage{prefix}{map:03d}_{stage:02d}.csv
    Map metadata: MapStageData{map_data_prefix}_{map:03d}.csv
    Stage names: {stage_name_file} (pipe-separated, 1 line per map)
    map_options: dict from load_map_options(), used for crown difficulty data.
    stage_options: dict from load_stage_options(), used for stage restrictions.
    fallback_name_from_stage: when True, sub-chapters absent from Map_Name.csv
        derive their display name and deduplication key from the first stage name.
        Use for chapters like Red Alert whose map IDs are not in Map_Name.csv.
    """
    if map_options is None:
        map_options = {}
    if stage_options is None:
        stage_options = {}
    stage_names_data = load_stage_names_file(stage_name_file)

    # Discover all stage files grouped by map number
    stage_files = {}
    pattern = re.compile(rf"^stage{re.escape(stage_prefix)}(\d{{3}})_(\d{{2}})\.csv$")
    for fn in os.listdir(DATA_LOCAL):
        m = pattern.match(fn)
        if m:
            map_n = int(m.group(1))
            stage_n = int(m.group(2))
            stage_files.setdefault(map_n, []).append((stage_n, fn))

    def _get_dedup_key(map_n):
        """Return the deduplication key for a given map_n."""
        real_name = map_names.get(base_map_id + map_n)
        if real_name:
            return real_name
        if fallback_name_from_stage:
            names_for_map = stage_names_data[map_n] if map_n < len(stage_names_data) else []
            first = re.sub(r'\s+', ' ', names_for_map[0]).strip() if names_for_map else ""
            if first:
                return first
        return f"__unnamed_{map_n}"

    # Deduplicate reruns: for same-named sub-chapters keep only the highest map_n.
    # BCData accumulates all historical event/collab runs; only the most recent matters.
    name_to_max: dict[str, int] = {}
    for map_n in stage_files:
        name = _get_dedup_key(map_n)
        if map_n > name_to_max.get(name, -1):
            name_to_max[name] = map_n
    keep = set(name_to_max.values())
    stage_files = {k: v for k, v in stage_files.items() if k in keep}

    sub_chapters = []
    for map_n in sorted(stage_files.keys()):
        map_id = base_map_id + map_n
        real_name = map_names.get(map_id)
        if real_name:
            map_name = real_name
        elif fallback_name_from_stage:
            names_for_map = stage_names_data[map_n] if map_n < len(stage_names_data) else []
            first = re.sub(r'\s+', ' ', names_for_map[0]).strip() if names_for_map else ""
            map_name = first if first else f"Sub-chapter {map_n}"
        else:
            map_name = f"Sub-chapter {map_n}"

        names = stage_names_data[map_n] if map_n < len(stage_names_data) else []

        msd_path = os.path.join(
            DATA_LOCAL, f"MapStageData{map_data_prefix}_{map_n:03d}.csv"
        )
        meta = parse_map_stage_data(msd_path)
        bg_id = parse_map_bg_id(msd_path)

        # Crown difficulty data from Map_option.csv
        crown = map_options.get(map_id, {})
        max_crowns = crown.get("maxCrowns", 1)
        mult2 = crown.get("mult2", 1.0)
        mult3 = crown.get("mult3", 1.0)
        mult4 = crown.get("mult4", 1.0)

        # Stage/crown restrictions from Stage_option.csv
        map_opts = stage_options.get(map_id, {})
        crown_restrictions = {}   # crown_num (int 1-4) -> restriction dict
        colosseum_group = None
        stage_restrictions = {}   # stage_n (int) -> restriction dict

        for star, star_data in map_opts.items():
            for sid, restr in star_data.items():
                cg = restr.get("colosseumGroup")
                base_restr = {k: v for k, v in restr.items() if k != "colosseumGroup"}

                if sid == -1:
                    # Map-level restriction (applies to all stages at this star level)
                    if cg and not colosseum_group:
                        colosseum_group = cg
                    if base_restr:
                        if star == -1:
                            # All crowns
                            for c in range(1, max_crowns + 1):
                                existing = crown_restrictions.get(c, {})
                                existing.update(base_restr)
                                crown_restrictions[c] = existing
                        else:
                            # Specific crown (star 0-3 → crown 1-4)
                            c = star + 1
                            existing = crown_restrictions.get(c, {})
                            existing.update(base_restr)
                            crown_restrictions[c] = existing
                else:
                    # Per-stage restriction
                    if base_restr:
                        existing = stage_restrictions.get(sid, {})
                        existing.update(base_restr)
                        stage_restrictions[sid] = existing

        stages_list = []
        for stage_n, fn in sorted(stage_files[map_n]):
            data = parse_stage_file(os.path.join(DATA_LOCAL, fn))
            if not data:
                continue
            continuation_ref = data.pop("_continuation", None)

            name = names[stage_n] if stage_n < len(names) else f"Stage {stage_n + 1}"
            energy = meta[stage_n]["energy"] if stage_n < len(meta) else 0
            xp = meta[stage_n]["xp"] if stage_n < len(meta) else 0
            rewards = meta[stage_n].get("rewards", []) if stage_n < len(meta) else []

            stage_obj = {
                "index": stage_n,
                "name": name,
                "energy": energy,
                "xp": xp,
                "rewards": rewards,
                **data,
            }
            if stage_n in stage_restrictions:
                stage_obj["restrictions"] = stage_restrictions[stage_n]
            if continuation_ref is not None:
                stage_obj["continuation"] = resolve_stage_continuation(
                    continuation_ref
                )
            stages_list.append(stage_obj)

        if stages_list:
            sub_ch = {
                "id": f"{chapter_id}_{map_n}",
                "name": map_name,
                "mapId": bg_id,
                "maxCrowns": max_crowns,
                "mult2": mult2,
                "mult3": mult3,
                "mult4": mult4,
                "stages": stages_list,
            }
            if crown_restrictions:
                sub_ch["crownRestrictions"] = crown_restrictions
            if colosseum_group:
                sub_ch["colosseum"] = colosseum_group
            if medals_by_mapid:
                medals = medals_by_mapid.get(map_id, [])
                if medals:
                    sub_ch["medals"] = medals
            sub_chapters.append(sub_ch)

    return {
        "id": chapter_id,
        "name": chapter_name,
        "mapId": base_map_id,
        "subChapters": sub_chapters,
    }


# ======================== MAIN STORY BUILDERS ========================

def build_eoc_chapter(medals_by_mapid=None):
    """
    Empire of Cats — 3 chapters, 48 stages each (47 countries + Moon).
    stageNormal0.csv for energy, StageName0_en.csv for names (one per line, reverse order).
    Enemy data from stage{NN}.csv (no castle line).
    Country stages 0-46 (Korea-Hawaii) are shared across all 3 chapters.
    Moon stage (index 47) is per-chapter: stage47 (Ch.1), stage49 (Ch.2), stage50 (Ch.3).
    stage48.csv is the Challenge Battle bonus stage (not part of the story).
    Energy indices in stageNormal0.csv: 0-46 for countries, 47=Ch.1 Moon, 49=Ch.2 Moon, 50=Ch.3 Moon.
    """
    names_data = load_stage_names_file("StageName0_en.csv")
    stage_names = [ln[0] for ln in names_data if ln] if names_data else []

    # Parse energy from stageNormal0.csv
    energies = parse_stage_normal_energy(
        os.path.join(DATA_LOCAL, "stageNormal0.csv")
    )

    # Load shared country stages 0-46 (Korea through Hawaii)
    num_countries = 47
    country_stage_data = []
    for si in range(num_countries):
        fp = os.path.join(DATA_LOCAL, f"stage{si:02d}.csv")
        data = parse_stage_file(fp, has_castle_line=False) if os.path.exists(fp) else None
        country_stage_data.append(data)

    # Per-chapter Moon stage files and their energy indices in stageNormal0.csv
    # stage47=Ch.1 Moon (The Face), stage49=Ch.2 Moon (Nyandam), stage50=Ch.3 Moon (Teacher Bun Bun)
    # stage48.csv is the Challenge Battle bonus stage, skipped here
    moon_file_indices = [47, 49, 50]  # stage47=Ch.1, stage49=Ch.2, stage50=Ch.3
    moon_stage_data = []
    for fi in moon_file_indices:
        fp = os.path.join(DATA_LOCAL, f"stage{fi:02d}.csv")
        data = parse_stage_file(fp, has_castle_line=False) if os.path.exists(fp) else None
        moon_stage_data.append(data)

    # Load rewards for each EoC stage from MapStageDataA_NNN.csv.
    # Each file covers one location (stage slot) across all 3 chapters.
    # Entry 0 = Ch.1, entry 1 = Ch.2, entry 2 = Ch.3 for that location.
    eoc_rewards_by_stage = {}  # stage_index -> list of per-chapter rewards lists
    for si in range(48):
        path_a = os.path.join(DATA_LOCAL, f"MapStageDataA_{si:03d}.csv")
        meta_a = parse_map_stage_data(path_a)
        eoc_rewards_by_stage[si] = [
            entry.get("rewards", []) for entry in meta_a
        ]

    ch_names = [
        "Empire of Cats Ch. 1",
        "Empire of Cats Ch. 2",
        "Empire of Cats Ch. 3",
    ]
    sub_chapters = []
    for ci, cn in enumerate(ch_names):
        stages = []
        # Country stages (shared, with reverse name mapping like ItF/CotC)
        for si in range(num_countries):
            base = country_stage_data[si] or {"stageWidth": 0, "baseHp": 0, "maxEnemies": 0, "enemies": []}
            ch_rewards = eoc_rewards_by_stage.get(si, [])
            rewards = ch_rewards[ci] if ci < len(ch_rewards) else []
            stages.append({
                "index": si,
                "name": _reverse_map_name(stage_names, si),
                "energy": energies[si] if si < len(energies) else 0,
                "xp": 0,
                "rewards": rewards,
                **base,
            })
        # Moon stage (per-chapter): stage index 47, name from position 47 in StageName0_en
        moon_energy_idx = moon_file_indices[ci]
        moon_base = moon_stage_data[ci] or {"stageWidth": 0, "baseHp": 0, "maxEnemies": 0, "enemies": []}
        moon_ch_rewards = eoc_rewards_by_stage.get(num_countries, [])
        moon_rewards = moon_ch_rewards[ci] if ci < len(moon_ch_rewards) else []
        stages.append({
            "index": num_countries,
            "name": _reverse_map_name(stage_names, num_countries),
            "energy": energies[moon_energy_idx] if moon_energy_idx < len(energies) else 0,
            "xp": 0,
            "rewards": moon_rewards,
            **moon_base,
        })
        map_id = 3000 + ci
        sub_ch = {"id": f"eoc_ch{ci + 1}", "name": cn, "mapId": map_id, "stages": stages}
        if medals_by_mapid:
            # Merge normal-mode and zombie-mode medals for this chapter
            medals = medals_by_mapid.get(map_id, []) + medals_by_mapid.get(20000 + ci, [])
            if medals:
                sub_ch["medals"] = medals
        sub_chapters.append(sub_ch)

    return {
        "id": "eoc",
        "name": "Empire of Cats",
        "mapId": 3000,
        "subChapters": sub_chapters,
    }


def build_aku_realms(medals_by_mapid=None):
    """Aku Realms — stageDM000_XX.csv with enemy data."""
    dm_data = load_stage_names_file("StageName_DM_en.csv")
    stage_names = dm_data[0] if dm_data else []

    msd_path = os.path.join(DATA_LOCAL, "MapStageDataDM_000.csv")
    meta = parse_map_stage_data(msd_path)

    stages = []
    for si in range(49):
        fp = os.path.join(DATA_LOCAL, f"stageDM000_{si:02d}.csv")
        if not os.path.exists(fp):
            continue
        data = parse_stage_file(fp)
        if not data:
            continue

        name = stage_names[si] if si < len(stage_names) else f"Stage {si + 1}"
        energy = meta[si]["energy"] if si < len(meta) else 0
        xp = meta[si]["xp"] if si < len(meta) else 0
        rewards = meta[si].get("rewards", []) if si < len(meta) else []

        stages.append({"index": si, "name": name, "energy": energy, "xp": xp, "rewards": rewards, **data})

    bg_id = parse_map_bg_id(msd_path)

    sub_chapter = {"id": "aku_main", "name": "The Aku Realms", "mapId": bg_id, "stages": stages}
    if medals_by_mapid:
        medals = medals_by_mapid.get(30000, [])
        if medals:
            sub_chapter["medals"] = medals

    return {
        "id": "aku_realms",
        "name": "The Aku Realms",
        "mapId": 30000,
        "subChapters": [sub_chapter],
    }


def build_legend_quest_chapter(map_options=None, medals_by_mapid=None):
    """Legend Quest — MapStageDataD_000 + StageName_RD_en.csv.

    Legend Quest reuses randomized Legend Stages layouts in-game, so BCData
    does not ship fixed stageD enemy-spawn CSVs. Keep the level list, energy,
    XP and rewards, but leave enemies empty instead of borrowing another mode's
    stage files.
    """
    if map_options is None:
        map_options = {}

    map_id = 16000
    names_data = load_stage_names_file("StageName_RD_en.csv")
    stage_names = names_data[0] if names_data else []
    msd_path = os.path.join(DATA_LOCAL, "MapStageDataD_000.csv")
    meta = parse_map_stage_data(msd_path)
    bg_id = parse_map_bg_id(msd_path)

    stages = []
    for si, stage_meta in enumerate(meta):
        name = stage_names[si] if si < len(stage_names) else f"LEVEL {si + 1}"
        stages.append({
            "index": si,
            "name": name,
            "energy": stage_meta["energy"],
            "xp": stage_meta["xp"],
            "rewards": stage_meta.get("rewards", []),
            "stageWidth": 0,
            "baseHp": 0,
            "maxEnemies": 0,
            "enemies": [],
        })

    crown = map_options.get(map_id, {})
    sub_chapter = {
        "id": "legend_quest_0",
        "name": "Legend Quest",
        "mapId": bg_id,
        "maxCrowns": crown.get("maxCrowns", 1),
        "mult2": crown.get("mult2", 1.0),
        "mult3": crown.get("mult3", 1.0),
        "mult4": crown.get("mult4", 1.0),
        "stages": stages,
    }
    if medals_by_mapid:
        medals = medals_by_mapid.get(map_id, [])
        if medals:
            sub_chapter["medals"] = medals

    return {
        "id": "legend_quest",
        "name": "Legend Quest",
        "mapId": map_id,
        "subChapters": [sub_chapter],
    }


def _reverse_map_name(names, stage_index):
    """Map play-order stage index to StageName line index.
    For ItF/CotC, the name files use map-position order, not play order.
    The mapping is: line = 45 - stage_index (for 0..45), line = stage_index (for 46+).
    """
    if stage_index < 46:
        idx = 45 - stage_index
    else:
        idx = stage_index
    return names[idx] if idx < len(names) else f"Stage {stage_index + 1}"


def build_itf_chapter(medals_by_mapid=None):
    """Into the Future — stageW04/05/06, StageName1_en.csv.
    Energy from stageNormal1_0/1/2.csv. stageW files have NO castle line.
    Names use reverse mapping from StageName1_en (map-position -> play-order)."""
    names_data = load_stage_names_file("StageName1_en.csv")
    # Flatten: each line has 1 name
    stage_names = [ln[0] for ln in names_data if ln] if names_data else []

    w_ids = [4, 5, 6]
    ch_names = [
        "Into the Future Ch. 1",
        "Into the Future Ch. 2",
        "Into the Future Ch. 3",
    ]
    normal_files = [
        "stageNormal1_0.csv",
        "stageNormal1_1.csv",
        "stageNormal1_2.csv",
    ]

    sub_chapters = []
    for ci, (wid, cn, nfn) in enumerate(zip(w_ids, ch_names, normal_files)):
        stage_meta = parse_stageNormal_itf_cotc(os.path.join(DATA_LOCAL, nfn))

        stages = []
        for si in range(48):
            fp = os.path.join(DATA_LOCAL, f"stageW{wid:02d}_{si:02d}.csv")
            if not os.path.exists(fp):
                continue
            data = parse_stage_file(fp, has_castle_line=False)
            if not data:
                continue

            name = _reverse_map_name(stage_names, si)
            energy = stage_meta[si]["energy"] if si < len(stage_meta) else 0
            rewards = stage_meta[si]["rewards"] if si < len(stage_meta) else []

            stages.append({
                "index": si, "name": name, "energy": energy, "xp": 0, "rewards": rewards, **data
            })

        map_id = 3003 + ci
        sub_ch = {"id": f"itf_ch{ci + 1}", "name": cn, "mapId": map_id, "stages": stages}
        if medals_by_mapid:
            # Merge normal-mode and zombie-mode medals
            medals = medals_by_mapid.get(map_id, []) + medals_by_mapid.get(21000 + ci, [])
            if medals:
                sub_ch["medals"] = medals
        sub_chapters.append(sub_ch)

    return {
        "id": "itf",
        "name": "Into the Future",
        "mapId": 3003,
        "subChapters": sub_chapters,
    }


def build_cotc_chapter(medals_by_mapid=None):
    """Cats of the Cosmos — stageSpace07/08/09, StageName2_en.csv.
    Energy from stageNormal2_0/1/2.csv. stageSpace files have NO castle line.
    Names use reverse mapping from StageName2_en (map-position -> play-order)."""
    names_data = load_stage_names_file("StageName2_en.csv")
    stage_names = [ln[0] for ln in names_data if ln] if names_data else []

    space_ids = [7, 8, 9]
    ch_names = [
        "Cats of the Cosmos Ch. 1",
        "Cats of the Cosmos Ch. 2",
        "Cats of the Cosmos Ch. 3",
    ]
    normal_files = [
        "stageNormal2_0.csv",
        "stageNormal2_1.csv",
        "stageNormal2_2.csv",
    ]

    sub_chapters = []
    for ci, (sid, cn, nfn) in enumerate(zip(space_ids, ch_names, normal_files)):
        stage_meta = parse_stageNormal_itf_cotc(os.path.join(DATA_LOCAL, nfn))

        stages = []
        for si in range(48):
            fp = os.path.join(DATA_LOCAL, f"stageSpace{sid:02d}_{si:02d}.csv")
            if not os.path.exists(fp):
                continue
            data = parse_stage_file(fp, has_castle_line=False)
            if not data:
                continue

            name = _reverse_map_name(stage_names, si)
            energy = stage_meta[si]["energy"] if si < len(stage_meta) else 0
            rewards = stage_meta[si]["rewards"] if si < len(stage_meta) else []

            stages.append({
                "index": si, "name": name, "energy": energy, "xp": 0, "rewards": rewards, **data
            })

        map_id = 3006 + ci
        sub_ch = {"id": f"cotc_ch{ci + 1}", "name": cn, "mapId": map_id, "stages": stages}
        if medals_by_mapid:
            # Merge normal-mode and zombie-mode medals
            medals = medals_by_mapid.get(map_id, []) + medals_by_mapid.get(22000 + ci, [])
            if medals:
                sub_ch["medals"] = medals
        sub_chapters.append(sub_ch)

    return {
        "id": "cotc",
        "name": "Cats of the Cosmos",
        "mapId": 3006,
        "subChapters": sub_chapters,
    }


# ======================== SPECIAL STAGES BUILDER ========================

def build_ex_chapter(map_names, map_options=None, stage_options=None, medals_by_mapid=None):
    """
    Special Stages / Catamin stages.

    These are map IDs 14000+, but their stage payloads live in the RB/B files:
      - stageRB{NNN}_{SS}.csv
      - MapStageDataB_{NNN}.csv
      - StageName_RB_en.csv

    stageEX files are continuation/extra payloads and are not aligned with
    Map_Name 14000+, so pairing stageEX005 with Map_Name 14005 gives
    "Facing Danger" with unrelated enemy data.
    """
    return build_r_chapter(
        "ex", "Special Stages", 14000,
        "RB", "StageName_RB_en.csv", "B",
        map_names, map_options, stage_options, medals_by_mapid,
    )


OBSOLETE_GAUNTLET_SUBCHAPTER_NAMES = {
    "Baron Seal Strikes!",
    "Baron Seal Strikes!!",
    "Baron Seal Strikes!!!",
    "Le'Grim Strikes!",
    "Le'Grim Strikes!!",
    "Le'Grim Strikes!!!",
    "Mega Menace!",
    "Mega Menace!!",
    "Mega Menace!!!",
    "Horrorpotamus!",
    "Horrorpotamus!!",
    "Horrorpotamus!!!",
}


# ======================== MAIN ========================

def iter_stage_tree(stage):
    """Yield a stage and every recursively linked continuation stage."""
    yield stage
    continuation = stage.get("continuation")
    if continuation:
        for target in continuation.get("stages", []):
            yield from iter_stage_tree(target)


def validate_stage_output(output_data):
    """Reject incomplete continuation data before either JSON is replaced."""
    continuation_count = 0
    for chapter in output_data.get("chapters", []):
        for sub in chapter.get("subChapters", []):
            for root_stage in sub.get("stages", []):
                for stage in iter_stage_tree(root_stage):
                    if "_continuation" in stage:
                        raise ValueError(
                            f"Unresolved continuation reference in stage {stage.get('name', '?')}"
                        )
                    continuation = stage.get("continuation")
                    if not continuation:
                        continue
                    continuation_count += 1
                    chance = continuation.get("chance")
                    if not isinstance(chance, int) or not 1 <= chance <= 100:
                        raise ValueError(
                            f"Invalid continuation chance in stage {stage.get('name', '?')}"
                        )
                    if not continuation.get("stages"):
                        raise ValueError(
                            f"Continuation in stage {stage.get('name', '?')} has no target stages"
                        )
    return continuation_count


def write_stage_outputs(output_data, output_paths):
    """Validate once, then atomically publish identical bytes to every target."""
    validate_stage_output(output_data)
    payload = json.dumps(
        output_data, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-8")
    temp_paths = []
    try:
        for output_path in map(os.fspath, output_paths):
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            temp_path = output_path + ".tmp"
            with open(temp_path, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            temp_paths.append((temp_path, output_path))
        for temp_path, output_path in temp_paths:
            os.replace(temp_path, output_path)
        for _, output_path in temp_paths:
            with open(output_path, "rb") as f:
                if f.read() != payload:
                    raise IOError(f"Stage output verification failed: {output_path}")
    finally:
        for temp_path, _ in temp_paths:
            if os.path.exists(temp_path):
                os.remove(temp_path)


def main():
    configure_sources()
    enemy_names = load_enemy_names()
    item_names = load_item_names()
    cat_drop_rewards = load_cat_drop_rewards()
    map_names = load_map_names()
    map_options = load_map_options()
    print(f"Loaded crown data for {len(map_options)} sub-chapters from Map_option.csv")
    charagroups = load_charagroups()
    stage_options = load_stage_options(charagroups)
    print(f"Loaded stage restrictions for {len(stage_options)} maps from Stage_option.csv "
          f"({len(charagroups)} Colosseum groups from Charagroup.csv)")
    medals_by_mapid = load_medals()
    medals = build_medal_catalog()
    print(f"Loaded {sum(len(v) for v in medals_by_mapid.values())} medals "
          f"across {len(medals_by_mapid)} sub-chapters from medallist.json")
    print(f"Loaded {len(medals)} total medals from medallist.json")
    print(f"Loaded {len(cat_drop_rewards)} cat-form drop names from unitbuy.csv + drop_chara.csv")

    def rc(chapter_id, chapter_name, base_map_id, stage_prefix, stage_name_file, map_data_prefix,
           fallback_name_from_stage=False):
        return build_r_chapter(
            chapter_id, chapter_name, base_map_id,
            stage_prefix, stage_name_file, map_data_prefix,
            map_names, map_options, stage_options, medals_by_mapid,
            fallback_name_from_stage=fallback_name_from_stage
        )

    chapters = [
        build_eoc_chapter(medals_by_mapid),
        build_itf_chapter(medals_by_mapid),
        build_cotc_chapter(medals_by_mapid),
        build_aku_realms(medals_by_mapid),
        rc("sol", "Stories of Legend", 0,       "RN",  "StageName_RN_en.csv",  "N"),
        rc("ul",  "Uncanny Legends",   13000,    "RNA", "StageName_RNA_en.csv", "NA"),
        rc("zl",  "Zero Legends",      34000,    "RND", "StageName_RND_en.csv", "ND"),
        build_ex_chapter(map_names, map_options, stage_options, medals_by_mapid),
        rc("events", "Event Stages",   1000,     "RS",  "StageName_RS_en.csv",  "S"),
        rc("towers", "Towers",         7000,     "RV",  "StageName_RV_en.csv",  "V"),
        rc("assault", "Assault Stages", 27000,   "RH",  "",  "H"),
        rc("gauntlets", "Gauntlets & Strikes", 24000, "RA", "StageName_RE_en.csv", "RE",
           fallback_name_from_stage=True),
        rc("collab", "Collaboration Stages", 2000,   "RC",  "StageName_RC_en.csv",  "C"),
        rc("colosseum", "Otherworld Colosseum", 36000, "RR", "", "R"),
        rc("catclaw", "Catclaw Championships", 37000, "G", "StageName_G_en.csv", "G"),
        build_legend_quest_chapter(map_options, medals_by_mapid),
        rc("behemoth_culling", "Behemoth Culling", 31000, "RQ", "StageName_RQ_en.csv",  "Q"),
        rc("aitum", "Aitum Fields",    25000,    "RCA", "StageName_RCA_en.csv", "CA"),
        rc("labyrinth", "Underground Labyrinth", 33000, "L", "StageName_L_en.csv", "L"),
        rc("arena", "Arena of Honor",  11000,    "RM",  "",  "M"),
        rc("ranking", "Ranking Stages", 900001,  "RSR", "StageName_RSR_en.csv", "SR"),
        rc("wanderers_trial", "Wanderer's Trial", 900002, "RT", "StageName_RT_en.csv", "T"),
    ]

    for ch in chapters:
        if ch["id"] == "gauntlets":
            before = len(ch["subChapters"])
            ch["subChapters"] = [
                sub for sub in ch["subChapters"]
                if sub["name"] not in OBSOLETE_GAUNTLET_SUBCHAPTER_NAMES
            ]
            removed = before - len(ch["subChapters"])
            if removed:
                print(f"  Removed {removed} obsolete Gauntlets & Strikes sub-chapters")

    # Permanent Special/Catamin stages must not also appear in Event Stages.
    # The RB/B versions supersede matching stageRS event reruns by subchapter name.
    ex_names = {
        sub["name"]
        for ch in chapters if ch["id"] == "ex"
        for sub in ch["subChapters"]
    }
    for ch in chapters:
        if ch["id"] == "events":
            before = len(ch["subChapters"])
            ch["subChapters"] = [s for s in ch["subChapters"] if s["name"] not in ex_names]
            removed = before - len(ch["subChapters"])
            if removed:
                print(f"  Removed {removed} Event sub-chapters superseded by Special Stages")

    # Stage CSV item IDs that diverge from GatyaitemName.csv line indices.
    # The stage data uses an older compact ID system where Cat Ticket = 11, Rare Ticket = 12,
    # while GatyaitemName.csv has those at lines 20 and 21 (new items were inserted between 6 and 20).
    STAGE_ITEM_ID_OVERRIDES = {
        11: "Cat Ticket",
        12: "Rare Ticket",
        13: "Cat Food",
    }

    # Post-process: inject enemy names and item names into rewards
    for chapter in chapters:
        for sub in chapter["subChapters"]:
            for root_stage in sub["stages"]:
                for stage in iter_stage_tree(root_stage):
                    for enemy in stage["enemies"]:
                        enemy["name"] = enemy_names.get(
                            enemy["id"], f"Enemy #{enemy['id']}"
                        )
                    for reward in stage.get("rewards", []):
                        rid = reward["id"]
                        cat_reward = cat_drop_rewards.get(rid)
                        if cat_reward:
                            reward.update(cat_reward)
                            reward["chapterId"] = chapter["id"]
                            reward["subChapterId"] = sub["id"]
                            reward["stageIndex"] = root_stage["index"]
                        else:
                            reward["name"] = (
                                STAGE_ITEM_ID_OVERRIDES.get(rid)
                                or item_names.get(rid)
                                or f"Item #{rid}"
                            )

    # Summary
    total_stages = sum(
        len(sub["stages"])
        for ch in chapters
        for sub in ch["subChapters"]
    )
    total_subs = sum(len(ch["subChapters"]) for ch in chapters)
    print(f"Generated {len(chapters)} chapters, {total_subs} sub-chapters, "
          f"{total_stages} stages")
    for ch in chapters:
        nsub = len(ch["subChapters"])
        nstg = sum(len(s["stages"]) for s in ch["subChapters"])
        print(f"  {ch['name']}: {nsub} sub-chapters, {nstg} stages")

    output_data = {
        "lastUpdate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "enemyNames": {str(k): v for k, v in enemy_names.items()},
        "medals": medals,
        "chapters": chapters,
    }

    continuation_count = validate_stage_output(output_data)
    print(f"Validated {continuation_count} continuation links")

    # The updater invokes this script directly. Publish the same validated byte
    # payload atomically to the bundled asset and UpdatedBCData copy.
    write_stage_outputs(output_data, [OUTPUT_APP, OUTPUT_REMOTE])
    for out_path in [OUTPUT_APP, OUTPUT_REMOTE]:
        size_mb = os.path.getsize(out_path) / 1024 / 1024
        print(f"\nOutput: {out_path}")
        print(f"File size: {size_mb:.1f} MB")


if __name__ == "__main__":
    run_generator(main)
