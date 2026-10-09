"""
Consolidate all enemy data files into a single enemies_data.json.

Reads:
  - enemy_data.csv (stats: HP, KB, speed, attack, etc.)
  - enemy_backswings.txt (TBA for enemies with rawInterval == 0)
  - descriptions/{lang}/enemy_names_{lang}.tsv (names per language)
  - descriptions/{lang}/enemy_descriptions_{lang}.tsv (descriptions per language)

Outputs:
  - enemies_data.json to app assets AND UpdatedBCData
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
from datetime import datetime

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = str(paths.data)
OUTPUT_APP = os.path.join(ASSETS_DIR, "enemies_data.json")
OUTPUT_REMOTE = os.environ.get("UPDATED_BC_DATA_ENEMIES_JSON", str(paths.root / "enemies_data.json"))

LANGUAGES = ["en", "es", "jp", "kr", "zh", "fr", "it", "de", "th", "tw"]

# Trait column indices in enemy_data.csv
TRAIT_COLUMNS = {
    10: "Red",
    13: "Floating",
    14: "Black",
    15: "Metal",
    16: "Traitless",
    17: "Angel",
    18: "Alien",
    19: "Zombie",
    72: "Relic",
    93: "Aku",
    48: "Witch",
    71: "Eva",
    94: "Colossus",
    101: "Beast",
    104: "Sage",
    110: "Villain",
}


def load_backswings():
    """Load enemy backswings from enemy_backswings.txt."""
    result = {}
    path = os.path.join(ASSETS_DIR, "enemy_backswings.txt")
    if not os.path.exists(path):
        return result
    with open(path, "r", encoding="utf-8") as f:
        current_name = ""
        for line in f:
            trimmed = line.strip()
            if trimmed.startswith("---"):
                current_name = trimmed.strip("-").strip()
            elif trimmed and current_name:
                try:
                    result[current_name] = int(trimmed)
                except ValueError:
                    pass
    return result


def load_names(lang):
    """Load enemy names for a language. Returns list indexed by enemy ID."""
    path = os.path.join(ASSETS_DIR, "descriptions", lang, f"enemy_names_{lang}.tsv")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f]


def load_descriptions(lang):
    """Load enemy descriptions for a language. Returns list of description line lists."""
    path = os.path.join(ASSETS_DIR, "descriptions", lang, f"enemy_descriptions_{lang}.tsv")
    if not os.path.exists(path):
        return []
    results = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            raw = line.strip()
            clean = raw.replace("%s|", "").split("|") if raw else []
            results.append(clean)
    return results


def col_int(parts, idx, default=0):
    """Safely get int from CSV column."""
    try:
        return int(parts[idx])
    except (IndexError, ValueError):
        return default


def parse_abilities(parts):
    """Parse ability flags from CSV columns, returning list of dicts with params."""
    abilities = []

    # Attack type
    if col_int(parts, 11) == 1:
        abilities.append({"type": "attack_area"})
    else:
        abilities.append({"type": "attack_single"})

    # Range type
    r1 = col_int(parts, 35)
    r2 = col_int(parts, 36)
    if r1 != 0 or r2 != 0:
        range_data = {"startRange": r1, "rangeExtension": r2}
        if r2 <= 0:
            abilities.append({"type": "attack_omnistrike", **range_data})
        else:
            abilities.append({"type": "attack_long_range", **range_data})

    # Knockback
    kb_chance = col_int(parts, 20)
    if kb_chance > 0:
        abilities.append({"type": "trait_knockback", "chance": kb_chance})

    # Freeze
    freeze_chance = col_int(parts, 21)
    freeze_dur = col_int(parts, 22)
    if freeze_chance > 0 and freeze_dur > 0:
        abilities.append({"type": "trait_freeze", "chance": freeze_chance, "duration": freeze_dur})

    # Slow
    slow_chance = col_int(parts, 23)
    slow_dur = col_int(parts, 24)
    if slow_chance > 0 and slow_dur > 0:
        abilities.append({"type": "trait_slow", "chance": slow_chance, "duration": slow_dur})

    # Weaken
    weaken_chance = col_int(parts, 29)
    weaken_dur = col_int(parts, 30)
    weaken_mult = col_int(parts, 31)
    if weaken_chance > 0:
        ab = {"type": "trait_weaken", "chance": weaken_chance}
        if weaken_dur > 0:
            ab["duration"] = weaken_dur
        if weaken_mult > 0:
            ab["multiplier"] = weaken_mult
        abilities.append(ab)

    # Warp
    warp_chance = col_int(parts, 65)
    warp_dur = col_int(parts, 66)
    if warp_chance > 0 and warp_dur > 0:
        abilities.append({"type": "trait_warp", "chance": warp_chance, "duration": warp_dur})

    # Curse
    curse_chance = col_int(parts, 73)
    curse_dur = col_int(parts, 74)
    if curse_chance > 0 and curse_dur > 0:
        abilities.append({"type": "trait_curse", "chance": curse_chance, "duration": curse_dur})

    # Dodge
    dodge_chance = col_int(parts, 77)
    dodge_dur = col_int(parts, 78)
    if dodge_chance > 0 and dodge_dur > 0:
        abilities.append({"type": "trait_dodge", "chance": dodge_chance, "duration": dodge_dur})

    # Toxic
    toxic_chance = col_int(parts, 79)
    toxic_dmg = col_int(parts, 80)
    if toxic_chance > 0 and toxic_dmg > 0:
        abilities.append({"type": "trait_toxic", "chance": toxic_chance, "damage": toxic_dmg})

    # Survive
    survive_chance = col_int(parts, 34)
    if survive_chance > 0:
        abilities.append({"type": "effect_survive", "chance": survive_chance})

    # Strengthen
    strengthen_threshold = col_int(parts, 32)
    strengthen_boost = col_int(parts, 33)
    if strengthen_threshold > 0 and strengthen_boost > 0:
        abilities.append({"type": "effect_strengthen", "threshold": strengthen_threshold, "boost": strengthen_boost})

    # Base Destroyer
    if col_int(parts, 26) == 1:
        abilities.append({"type": "effect_base_destroyer"})

    # Critical
    critical_chance = col_int(parts, 25)
    if critical_chance > 0:
        abilities.append({"type": "effect_critical", "chance": critical_chance})

    # Barrier
    barrier_hp = col_int(parts, 64)
    if barrier_hp > 0:
        abilities.append({"type": "barrier", "hp": barrier_hp})

    # Shield
    shield_hp = col_int(parts, 87)
    if shield_hp > 0:
        abilities.append({"type": "shield", "hp": shield_hp})

    # Savage Blow
    savage_chance = col_int(parts, 75)
    if savage_chance > 0:
        abilities.append({"type": "effect_savage_blow", "chance": savage_chance})

    # Wave / Mini-Wave
    wave_chance = col_int(parts, 27)
    wave_level = col_int(parts, 28)
    is_mini_wave = col_int(parts, 86)
    if wave_chance > 0 and wave_level > 0:
        wave_type = "effect_mini_wave" if is_mini_wave == 1 else "effect_wave"
        abilities.append({"type": wave_type, "chance": wave_chance, "level": wave_level})

    # Surge / Mini-Surge
    surge_chance = col_int(parts, 81)
    surge_level = col_int(parts, 84)
    is_mini_surge = col_int(parts, 102)
    if surge_chance > 0:
        surge_type = "effect_mini_surge" if is_mini_surge == 1 else "effect_surge"
        ab = {"type": surge_type, "chance": surge_chance}
        if surge_level > 0:
            ab["level"] = surge_level
        abilities.append(ab)

    # Death Surge
    death_surge_chance = col_int(parts, 89)
    death_surge_level = col_int(parts, 92)
    if death_surge_chance > 0:
        ab = {"type": "effect_death_surge", "chance": death_surge_chance}
        if death_surge_level > 0:
            ab["level"] = death_surge_level
        abilities.append(ab)

    # Counter Surge
    if col_int(parts, 103) == 1:
        abilities.append({"type": "effect_counter_surge"})

    # Explosion
    explossion_chance = col_int(parts, 106)
    if explossion_chance > 0:
        abilities.append({"type": "effect_explossion", "chance": explossion_chance})

    # Immunities
    immunity_cols = {
        39: "immune_to_knockback",
        40: "immune_to_freeze",
        41: "immune_to_slow",
        42: "immune_to_weaken",
        37: "immune_to_wave",
        85: "immune_to_surge",
        109: "immune_to_explossion",
        70: "immune_to_warp",
        105: "immune_to_curse",
    }
    for col, name in immunity_cols.items():
        if col_int(parts, col) == 1:
            abilities.append({"type": name})

    return abilities


def parse_traits(parts):
    """Parse trait flags from CSV columns."""
    traits = []
    for col, name in TRAIT_COLUMNS.items():
        if col == 45:  # Base has special logic
            if col_int(parts, 45) > 0:
                traits.append("Bases")
        elif col_int(parts, col) == 1:
            traits.append(name)
    # Base check (separate since it's not in TRAIT_COLUMNS with value 1)
    if col_int(parts, 45) > 0 and "Bases" not in traits:
        traits.append("Bases")
    return traits


def main():
    backswings = load_backswings()

    # Load names and descriptions per language
    all_names = {}
    all_descs = {}
    for lang in LANGUAGES:
        all_names[lang] = load_names(lang)
        all_descs[lang] = load_descriptions(lang)

    # Load stats CSV
    # t_unit.csv has 2 placeholder/dummy rows at the start (indices 0 and 1)
    # that don't correspond to real enemies. Skip them so that CSV row 2
    # (Doge) aligns with names index 0.
    stats_path = os.path.join(ASSETS_DIR, "enemy_data.csv")
    with open(stats_path, "r", encoding="utf-8") as f:
        stats_lines = [line.strip() for line in f if line.strip()]
    stats_lines = stats_lines[2:]

    enemies = []
    for index, line in enumerate(stats_lines):
        parts = line.split(",")
        if len(parts) < 7:
            continue

        hp = col_int(parts, 0)
        kbs = col_int(parts, 1, 1)
        speed = col_int(parts, 2)
        attack = col_int(parts, 3)
        raw_interval = col_int(parts, 4)
        foreswing = col_int(parts, 12)
        rng = col_int(parts, 5)
        attack_range_start = col_int(parts, 35)
        attack_range_extension = col_int(parts, 36)
        attack_range_2_start = col_int(parts, 96) if col_int(parts, 95) != 0 else 0
        attack_range_2_extension = col_int(parts, 97) if col_int(parts, 95) != 0 else 0
        attack_range_3_start = col_int(parts, 99) if col_int(parts, 98) != 0 else 0
        attack_range_3_extension = col_int(parts, 100) if col_int(parts, 98) != 0 else 0
        money = col_int(parts, 6)

        # Build names map
        names = {}
        for lang in LANGUAGES:
            name_list = all_names.get(lang, [])
            if index < len(name_list) and name_list[index]:
                names[lang] = name_list[index]

        # Build descriptions map
        descs = {}
        for lang in LANGUAGES:
            desc_list = all_descs.get(lang, [])
            if index < len(desc_list) and desc_list[index]:
                descs[lang] = desc_list[index]

        # TBA calculation
        en_name = names.get("en", "").strip()
        if raw_interval > 0:
            attack_freq = foreswing + (raw_interval * 2 - 1)
        else:
            attack_freq = backswings.get(en_name, 0)

        traits = parse_traits(parts)
        abilities = parse_abilities(parts)

        enemy = {
            "id": index,
            "names": names,
            "hp": hp,
            "kbs": kbs,
            "speed": speed,
            "attack": attack,
            "attackFreq": attack_freq,
            "range": rng,
            "attackRangeStart": attack_range_start,
            "attackRangeExtension": attack_range_extension,
            "attackRange2Start": attack_range_2_start,
            "attackRange2Extension": attack_range_2_extension,
            "attackRange3Start": attack_range_3_start,
            "attackRange3Extension": attack_range_3_extension,
            "moneyDrop": money,
            "traits": traits,
            "abilities": abilities,
        }

        # Only include descriptions if non-empty
        if descs:
            enemy["descriptions"] = descs

        enemies.append(enemy)

    output = {
        "lastUpdate": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "totalEnemies": len(enemies),
        "enemies": enemies,
    }

    for out_path in filter(None, [OUTPUT_APP, OUTPUT_REMOTE]):
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, separators=(",", ":"))
        size_mb = os.path.getsize(out_path) / 1024 / 1024
        print(f"Output: {out_path} ({size_mb:.1f} MB)")

    print(f"Total enemies: {len(enemies)}")


if __name__ == "__main__":
    run_generator(main)
