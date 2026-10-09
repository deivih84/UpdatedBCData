#!/usr/bin/env python3
"""
update_medals.py – Actualiza todas las medallas en stages_data.json.
Corrige medallas mal asignadas y añade las que faltan.
"""

# Both direct invocation and python -m work from any current directory.
import os as _workspace_os
import sys as _workspace_sys
from pathlib import Path as _WorkspacePath
if __package__ in (None, ''):
    _workspace_sys.path.insert(0, str(_WorkspacePath(__file__).resolve().parents[2]))
from workspace_paths import Workspace, latest_version_dir, run_generator
paths = Workspace.load(_workspace_os.environ.get('UPDATED_BCDATA_ROOT'))

import json
import sys

INPUT = str(paths.root / 'stages_data.json')

# ──────────────────────────────────────────────
# TABLA DE MEDALLAS: subchapter_id → lista de medals
# grade: 0=bronze, 1=silver, 2=gold, 3=special
# iconIdx = línea 0-indexada en medalname.tsv = índice imagen medal_XXX.png
# ──────────────────────────────────────────────
MEDALS_BY_SUBCHAPTER = {

    # ── Empire of Cats ── (ya están bien, se mantienen)
    "eoc_ch1": [
        {"name": "★ Builder of Empires ★",   "description": "Collect all Gold Treasures from Empire of Cats Ch. 1", "grade": 0, "iconIdx": 0},
        {"name": "★ Undead Slayer ★",         "description": "Clear all Empire of Cats Ch. 1 Zombie Outbreak Stages","grade": 0, "iconIdx": 3, "condition": {"limit": 1}},
    ],
    "eoc_ch2": [
        {"name": "★ Builder of Empires 2 ★",  "description": "Collect all Gold Treasures from Empire of Cats Ch. 2", "grade": 1, "iconIdx": 1, "condition": {"limit": 1}},
        {"name": "★ Undead Slayer 2 ★",        "description": "Clear all Empire of Cats Ch. 2 Zombie Outbreak Stages","grade": 1, "iconIdx": 4, "condition": {"limit": 2}},
    ],
    "eoc_ch3": [
        {"name": "★ Builder of Empires 3 ★",  "description": "Collect all Gold Treasures from Empire of Cats Ch. 3", "grade": 2, "iconIdx": 2, "condition": {"limit": 2}},
        {"name": "★ Undead Slayer 3 ★",        "description": "Clear all Empire of Cats Ch. 3 Zombie Outbreak Stages","grade": 2, "iconIdx": 5, "condition": {"limit": 3}},
    ],

    # ── Into the Future ── (CORREGIDO)
    "itf_ch1": [
        {"name": "★ The Future Is Ours ★",   "description": "Collect all Gold Treasures from Into the Future Ch. 1", "grade": 0, "iconIdx": 6, "condition": {"limit": 1}},
        {"name": "★ ...And Stay Dead ★",      "description": "Clear all Into the Future Ch. 1 Zombie Outbreak Stages", "grade": 0, "iconIdx": 9, "condition": {"limit": 4}},
    ],
    "itf_ch2": [
        {"name": "★ The Future Is Ours 2 ★", "description": "Collect all Gold Treasures from Into the Future Ch. 2", "grade": 1, "iconIdx": 7, "condition": {"limit": 4}},
        {"name": "★ ...And Stay Dead 2 ★",    "description": "Clear all Into the Future Ch. 2 Zombie Outbreak Stages", "grade": 1, "iconIdx": 10, "condition": {"limit": 5}},
    ],
    "itf_ch3": [
        {"name": "★ The Future Is Ours 3 ★", "description": "Collect all Gold Treasures from Into the Future Ch. 3", "grade": 2, "iconIdx": 8, "condition": {"limit": 5}},
        {"name": "★ ...And Stay Dead 3 ★",    "description": "Clear all Into the Future Ch. 3 Zombie Outbreak Stages", "grade": 2, "iconIdx": 76, "condition": {"limit": 6}},
    ],

    # ── Cats of the Cosmos ── (CORREGIDO)
    "cotc_ch1": [
        {"name": "★ Cosmos Conquistador ★",  "description": "Collect all Gold Treasures from Cats of the Cosmos Ch. 1", "grade": 0, "iconIdx": 11, "condition": {"limit": 4}},
        {"name": "★ Dead Stars ★",            "description": "Clear all Cats of the Cosmos Ch. 1 Zombie Outbreak Stages", "grade": 0, "iconIdx": 94, "condition": {"limit": 7}},
    ],
    "cotc_ch2": [
        {"name": "★ Cosmos Conquistador 2 ★","description": "Collect all Gold Treasures from Cats of the Cosmos Ch. 2", "grade": 1, "iconIdx": 12, "condition": {"limit": 7}},
        {"name": "★ Dead Stars II ★",          "description": "Clear all Cats of the Cosmos Ch. 2 Zombie Outbreak Stages", "grade": 1, "iconIdx": 109, "condition": {"limit": 8}},
    ],
    "cotc_ch3": [
        {"name": "★ Cosmos Conquistador 3 ★","description": "Collect all Gold Treasures from Cats of the Cosmos Ch. 3", "grade": 2, "iconIdx": 13, "condition": {"limit": 8}},
        {"name": "★ Dead Stars III ★",         "description": "Clear all Cats of the Cosmos Ch. 3 Zombie Outbreak Stages", "grade": 2, "iconIdx": 123, "condition": {"limit": 9}},
        {"name": "★ No More Worlds to Conquer? ★",  "description": "Defeat Filibuster Obstructa.",        "grade": 2, "iconIdx": 14, "condition": {"limit": 9}},
        {"name": "★ No More Worlds to Conquer? Z ★","description": "Clear Filibuster Zombie Stage",       "grade": 3, "iconIdx": 124},
    ],

    # ── The Aku Realms ──
    "aku_main": [
        {"name": "★ World of Darkness ★", "description": "Clear all stages in \"The Aku Realms\"", "grade": 2, "iconIdx": 90},
    ],

    # ── Stories of Legend ──
    # sol_47 = The Legend Ends (último SoL regular)
    "sol_47": [
        {"name": "★ I Am Legend ★",   "description": "Clear All Level 1 Stories of Legend stages", "grade": 2, "iconIdx": 15},
        {"name": "★ I Am Legend 2 ★", "description": "Clear All Level 2 Stories of Legend stages", "grade": 2, "iconIdx": 16},
        {"name": "★ I Am Legend 3 ★", "description": "Clear All Level 3 Stories of Legend stages", "grade": 2, "iconIdx": 17},
        {"name": "★ I Am Legend 4 ★", "description": "Clear All Level 4 Stories of Legend stages", "grade": 3, "iconIdx": 85},
    ],
    # Medals tied to specific SoL unlock stages
    "sol_17": [
        {"name": "★ Tiny Nemesis ★",       "description": "Unlock Li'l Nyandam",         "grade": 2, "iconIdx": 64},
    ],
    "sol_22": [
        {"name": "★ Under the Hood ★",     "description": "Unlock Red Riding Mina",       "grade": 2, "iconIdx": 65},
    ],
    "sol_26": [
        {"name": "★ Forest Child ★",       "description": "Unlock Ururun Wolf",           "grade": 2, "iconIdx": 63},
    ],
    "sol_27": [
        {"name": "★ Ronin's Redemption ★", "description": "Unlock Miyamoku Musashi",      "grade": 2, "iconIdx": 66},
    ],
    "sol_36": [
        {"name": "★ Buns of Steel ★",      "description": "Unlock Mecha-Bun",             "grade": 2, "iconIdx": 67},
    ],
    "sol_48": [
        {"name": "★ Exiel Exterminated ★", "description": "Clear \"Divine Archangel Strikes\"", "grade": 2, "iconIdx": 101, "condition": {"limit": 1}},
        {"name": "★ Go With Doron ★",      "description": "Unlock Elder Mask Doron",      "grade": 2, "iconIdx": 88},
    ],

    # ── Uncanny Legends ──
    # ul_48 = Sacred Forest (último UL)
    "ul_48": [
        {"name": "★ I Am Uncanny Legend 1 ★", "description": "Clear All Level 1 Uncanny Legend stages", "grade": 2, "iconIdx": 103},
        {"name": "★ I Am Uncanny Legend 2 ★", "description": "Clear All Level 2 Uncanny Legend stages", "grade": 2, "iconIdx": 106},
        {"name": "★ I Am Uncanny Legend 3 ★", "description": "Clear All Level 3 Uncanny Legend stages", "grade": 2, "iconIdx": 110},
        {"name": "★ I Am Uncanny Legend 4 ★", "description": "Clear All Level 4 Uncanny Legend stages",  "grade": 3, "iconIdx": 117},
        {"name": "★ Heart of Clay ★",          "description": "Unlock Dogumaru",                          "grade": 2, "iconIdx": 68},
        {"name": "★ Newton ★",                  "description": "Unlock Master of Logic Newton",            "grade": 2, "iconIdx": 121},
    ],
    # Unlock medals en etapas específicas de UL
    "ul_11": [
        {"name": "★ Naala Problem ★",  "description": "Unlock Elder Beast Naala",       "grade": 2, "iconIdx": 95},
    ],
    "ul_20": [
        {"name": "★ Lord Luza ★",      "description": "Unlock Ancient Egg: N000",       "grade": 2, "iconIdx": 104},
    ],
    "ul_35": [
        {"name": "★ Soractes ★",       "description": "Unlock Master of Mind Soractes", "grade": 2, "iconIdx": 114},
    ],

    # ── Zero Legends ──
    "zl_28": [
        {"name": "★ Elder Annihilator ★", "description": "Defeat Idi:Re and clear her stage.", "grade": 3, "iconIdx": 86},
    ],

    # ── Event Stages – Cyclones ──
    "events_14": [
        {"name": "★ Red Horizon ★",    "description": "Clear \"Crimson Catastrophe\"",   "grade": 1, "iconIdx": 18},
    ],
    "events_15": [
        {"name": "★ Dark Skies ★",     "description": "Clear \"Heaven of Darkness\"",    "grade": 1, "iconIdx": 19},
    ],
    "events_16": [
        {"name": "★ White Winds ★",    "description": "Clear \"Peerless\"",               "grade": 1, "iconIdx": 20},
    ],
    "events_39": [
        {"name": "★ Holy Squall ★",    "description": "Clear \"Wrath of Heaven\"",        "grade": 1, "iconIdx": 21},
    ],
    "events_43": [
        {"name": "★ Storm of Steel ★", "description": "Clear \"Sweet Irony\"",            "grade": 1, "iconIdx": 22},
    ],
    "events_66": [
        {"name": "★ Alien Weather ★",  "description": "Clear \"Dimension of Despair\"",   "grade": 1, "iconIdx": 23},
    ],
    "events_95": [
        {"name": "★ Angel's Cruelty ★","description": "Clear \"Clionel Ascendant\"",      "grade": 1, "iconIdx": 28},
    ],
    "events_96": [
        {"name": "★ Perfect Threat ★", "description": "Clear \"Red Sky at Morning\"",     "grade": 1, "iconIdx": 24},
    ],
    "events_117": [
        {"name": "★ Charon's Crossing ★","description": "Clear \"River Styx\"",           "grade": 1, "iconIdx": 29},
    ],
    "events_119": [
        {"name": "★ Uncrowned ★",      "description": "Clear \"Queen's Coronation\"",     "grade": 1, "iconIdx": 30},
    ],
    "events_122": [
        {"name": "★ Typhoon Z ★",      "description": "Clear \"The Rolling Dead\"",       "grade": 1, "iconIdx": 25},
    ],
    "events_128": [
        {"name": "★ The Big Z ★",      "description": "Clear \"Dead on Debut\"",          "grade": 1, "iconIdx": 31},
    ],
    "events_157": [
        {"name": "★ Dimensional Rift ★","description": "Clear \"The 2nd Dimension\"",     "grade": 1, "iconIdx": 26},
    ],
    "events_158": [
        {"name": "★ Usurper ★",        "description": "Clear \"King Wahwah's Revenge\"",  "grade": 2, "iconIdx": 32},
    ],
    "events_177": [
        {"name": "★ Time to Wake Up ★","description": "Clear \"Deeply Dreaming\"",        "grade": 1, "iconIdx": 33},
    ],
    "events_189": [
        {"name": "★ Ancient Tempest ★","description": "Clear \"Typhoon Nemo\"",           "grade": 1, "iconIdx": 27},
    ],
    "events_215": [
        {"name": "★ Comet Celeb ★",    "description": "Clear \"Blue Impact\"",            "grade": 1, "iconIdx": 34},
    ],
    "events_217": [
        {"name": "★ Tormented ★",      "description": "Clear \"Courts of Torment\"",      "grade": 2, "iconIdx": 69},
    ],
    "events_219": [
        {"name": "★ Vox Deus ★",       "description": "Clear \"Papuu's Paradise\"",       "grade": 2, "iconIdx": 71},
    ],
    "events_220": [
        {"name": "★ Ancient Dynasty ★","description": "Clear \"The Old Queen\"",          "grade": 2, "iconIdx": 70},
    ],
    "events_226": [
        {"name": "★ Murky Details ★",  "description": "Clear \"Bottom of the Swamp\"",   "grade": 1, "iconIdx": 72},
    ],
    "events_229": [
        {"name": "★ Cosmic Wanwan ★",  "description": "Clear \"Wanwan's Glory\"",         "grade": 2, "iconIdx": 75},
    ],
    "events_231": [
        {"name": "★ Angel of Undeath ★","description": "Clear \"Z-Onel Rises!\"",         "grade": 2, "iconIdx": 77},
    ],
    "events_232": [
        {"name": "★ Helping Out ★",    "description": "Clear \"First Errand\"",           "grade": 1, "iconIdx": 78},
    ],
    "events_246": [
        {"name": "★ Road to Ruin ★",   "description": "Clear \"Prelude to Ruin\"",        "grade": 1, "iconIdx": 87},
    ],
    "events_259": [
        {"name": "★ Storm of Evil ★",  "description": "Clear \"The Great Diablo\"",       "grade": 2, "iconIdx": 89},
    ],
    "events_272": [
        {"name": "★ Alluring Composition ★","description": "Clear \"Temptation's Symphony\"","grade": 2, "iconIdx": 91},
    ],
    "events_273": [
        {"name": "★ Lock the Gates ★", "description": "Clear \"Rashomon\"",               "grade": 2, "iconIdx": 92},
    ],
    "events_340": [
        {"name": "★ Infernal Tyrant Nyandam ★","description": "Clear \"Reign of the Tyrant\"","grade": 2, "iconIdx": 105},
    ],
    "events_348": [
        {"name": "★ Sanzu Swamp Guardian ★","description": "Clear \"Invasion of the Swamplord\"","grade": 2, "iconIdx": 108},
    ],
    "events_391": [
        {"name": "★ Xenobeast Bunaglios ★","description": "Clear \"Hunt for the Xenobeast\"","grade": 2, "iconIdx": 119},
    ],
    "events_406": [
        {"name": "★ Jumbo Jones ★",    "description": "Clear \"Jumbo Invasion\"",         "grade": 2, "iconIdx": 122},
    ],
    "events_421": [
        {"name": "★ Poultrio ★",       "description": "Clear \"Invasion of Poultrio\"",   "grade": 2, "iconIdx": -1},
    ],

    # ── Event Stages – Seasonal / Holiday ──
    "events_8": [
        {"name": "★ Work Up a Sweat ★","description": "Clear \"Autumn = Sports Day\"",   "grade": 1, "iconIdx": 47},
    ],
    "events_9": [
        {"name": "★ On Strike ★",      "description": "Clear \"Loving Labour\"",          "grade": 1, "iconIdx": 48},
    ],
    "events_10": [
        {"name": "★ A Catsmas Miracle ★","description": "Clear \"Jingle Cat Bell\"",      "grade": 1, "iconIdx": 49},
    ],
    "events_11": [
        {"name": "★ Another Year ★",   "description": "Clear \"Happy New Year...?\"",     "grade": 1, "iconIdx": 38},
    ],
    "events_12": [
        {"name": "★ Ritually Speaking ★","description": "Clear \"Ritual Happiness\"",     "grade": 1, "iconIdx": 39},
    ],
    "events_13": [
        {"name": "★ Unbearable ★",     "description": "Clear \"Bears Be Bare\"",          "grade": 1, "iconIdx": 40},
    ],
    "events_26": [
        {"name": "★ Young Love ★",     "description": "Clear \"Teacher! It's Spring!\"",  "grade": 1, "iconIdx": 41},
    ],
    "events_29": [
        {"name": "★ Ambition's End ★", "description": "Clear \"Love is Sickness\"",       "grade": 1, "iconIdx": 42},
    ],
    "events_30": [
        {"name": "★ Man and Wife? ★",  "description": "Clear \"The Forbidden Bride\"",    "grade": 1, "iconIdx": 43},
    ],
    "events_31": [
        {"name": "★ Holidays in the Sun ★","description": "Clear \"Never Summer!\"",      "grade": 1, "iconIdx": 44},
    ],
    "events_32": [
        {"name": "★ Who You Gonna Call? ★","description": "Clear \"Ghostly Houseguests\"","grade": 1, "iconIdx": 45},
    ],
    "events_36": [
        {"name": "★ Respect Your Elders ★","description": "Clear \"Old Guys About Town\"","grade": 1, "iconIdx": 46},
    ],

    # ── Event Stages – Total War ──
    "events_234": [
        {"name": "★ Rites of Spring ★","description": "Clear \"Total War: Spring Special\"","grade": 1, "iconIdx": 80},
    ],
    "events_235": [
        {"name": "★ Song of Summer ★", "description": "Clear \"Total War: Summer Special\"","grade": 1, "iconIdx": 81},
    ],
    "events_236": [
        {"name": "★ Feast of Fall ★",  "description": "Clear \"Total War: Fall Special\"", "grade": 1, "iconIdx": 82},
    ],
    "events_237": [
        {"name": "★ Dance of Winter ★","description": "Clear \"Total War: Winter Special\"","grade": 1, "iconIdx": 83},
        {"name": "★ Year-Round ★",     "description": "Clear all Total War season maps",    "grade": 2, "iconIdx": 84},
    ],

    # ── Event Stages – All-clear medals (last stage of each set) ──
    "events_25": [
        {"name": "★ Crazy Enough to Work ★","description": "Clear all Crazed Stages.", "grade": 1, "iconIdx": 35},
    ],
    "events_110": [
        {"name": "★ Manic Episodes ★", "description": "Clear all Maniac Stages.",        "grade": 1, "iconIdx": 36},
    ],
    "events_138": [
        {"name": "★ Your Own Size ★",  "description": "Clear all Li'l Stages.",          "grade": 1, "iconIdx": 37},
    ],
    "events_208": [
        {"name": "★ Frenzied Family ★","description": "Clear \"Clan of the Maniacs\"",   "grade": 1, "iconIdx": 74},
    ],
    "events_358": [
        {"name": "★ Malevolence ★",    "description": "Clear all Malevolent stages.",     "grade": 2, "iconIdx": 112},
    ],
    "events_376": [
        {"name": "★ Heinous Family ★", "description": "Clear \"Super Smash Families\"",   "grade": 2, "iconIdx": 116},
    ],

    # ── Gauntlets & Strikes ──
    "gauntlets_20": [
        {"name": "★ Baron Wasted ★",       "description": "Clear \"Baron Seal Strikes\"",         "grade": 2, "iconIdx": 96},
    ],
    "gauntlets_27": [
        {"name": "★ Le'Grim Reaped ★",     "description": "Clear \"Le'Grim Strikes\"",            "grade": 2, "iconIdx": 97},
    ],
    "gauntlets_34": [
        {"name": "★ Mega Massacre ★",      "description": "Clear \"Mega Menace\"",                "grade": 2, "iconIdx": 98},
    ],
    "gauntlets_35": [
        {"name": "★ Hyppoh Hysteria ★",    "description": "Clear \"Horrorpotamus\"",              "grade": 2, "iconIdx": 99},
    ],
    "gauntlets_38": [
        {"name": "★ Big Peng in the Neck ★","description": "Clear \"Big Peng Z Strikes\"",        "grade": 2, "iconIdx": 100},
    ],
    "gauntlets_37": [
        {"name": "★ Exiel Exterminated ★", "description": "Clear \"Divine Archangel Strikes\"",   "grade": 2, "iconIdx": 101},
    ],

    # ── Towers ──
    "towers_0": [
        {"name": "Floor 30", "description": "Clear the 30th floor of Heavenly Tower", "grade": 2, "iconIdx": 50, "condition": {"stage": 28}},
        {"name": "Floor 40", "description": "Clear the 40th floor of Heavenly Tower", "grade": 3, "iconIdx": 51, "condition": {"stage": 38}},
        {"name": "Floor 50", "description": "Clear the 50th floor of Heavenly Tower", "grade": 3, "iconIdx": 79, "condition": {"stage": 48}},
    ],
    "towers_6": [
        {"name": "Inferno 30", "description": "Clear Floor 30 of the Infernal Tower", "grade": 3, "iconIdx": 93, "condition": {"stage": 29}},
        {"name": "Inferno 40", "description": "Clear Floor 40 of the Infernal Tower", "grade": 3, "iconIdx": 102, "condition": {"stage": 39}},
        {"name": "Inferno 50", "description": "Clear Floor 50 of the Infernal Tower", "grade": 3, "iconIdx": 113, "condition": {"stage": 49}},
    ],

    # ── Legend Quest ──
    "legend_quest_0": [
        {"name": "A True Master", "description": "Complete the FINAL LEVEL of Legend Quest.", "grade": 3, "iconIdx": 52, "condition": {"stage": 46}},
    ],

    # ── Underground Labyrinth ──
    "labyrinth_0": [
        {"name": "Underground B100F", "description": "Clear the 100th floor of the Underground Labyrinth", "grade": 3, "iconIdx": 120, "condition": {"limit": 6}},
    ],
}


def build_medal(m: dict) -> dict:
    """Construye dict de medalla sin campos vacíos opcionales."""
    medal = {
        "name": m["name"],
        "description": m["description"],
        "grade": m["grade"],
        "iconIdx": m["iconIdx"],
    }
    if "condition" in m and m["condition"]:
        medal["condition"] = m["condition"]
    return medal


def main(input_path=None):
    input_path = input_path or INPUT
    sys.stdout.reconfigure(encoding="utf-8")

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    updated = 0
    skipped = []

    # Build lookup: subchapter_id → (chapter_index, sub_index)
    lookup = {}
    for ci, chapter in enumerate(data["chapters"]):
        for si, sub in enumerate(chapter["subChapters"]):
            lookup[sub["id"]] = (ci, si)

    for sub_id, medals in MEDALS_BY_SUBCHAPTER.items():
        if sub_id not in lookup:
            skipped.append(sub_id)
            continue
        ci, si = lookup[sub_id]
        data["chapters"][ci]["subChapters"][si]["medals"] = [
            build_medal(m) for m in medals
        ]
        updated += 1

    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))

    print(f"Updated: {updated} subchapters")
    if skipped:
        print(f"Skipped (not found): {skipped}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stages-data', type=_WorkspacePath, default=INPUT)
    main(parser.parse_args().stages_data)
