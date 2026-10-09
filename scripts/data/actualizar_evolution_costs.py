"""
actualizar_evolution_costs.py
Parses unitbuy.csv from the latest BCData JP folder and adds evolution cost
data (True Form / Ultra Form) to each unit's info in cats_data.json.

Must run AFTER actualizar_cats_info.py since that script regenerates the JSON.

Column layout in unitbuy.csv (0-indexed):
  [13]     flag: 3 = has True Form catfruit evo, 4 = has True + Ultra Form
  [25]     level required for True Form
  [26]     level required for Ultra Form (-1 if none)
  [27]     XP cost True Form
  [28-37]  5 x (item_id, qty) pairs for True Form materials
  [38]     XP cost Ultra Form
  [39-48]  5 x (item_id, qty) pairs for Ultra Form materials

Item IDs from GatyaitemName.csv (EN 15.2.0):
  Catfruit Seeds: 30=Purple 31=Red 32=Blue 33=Green 34=Yellow
                  41=Elder  43=Epic 160=Aku  164=Gold
  Catfruits:      35=Purple 36=Red  37=Blue  38=Green 39=Yellow
                  40=Epic   42=Elder 44=Gold 161=Aku
  Behemoth Stones: 167=Purple 168=Red 169=Blue 170=Green 171=Yellow 184=Epic
  Behemoth Gems:   179=Purple 180=Red 181=Blue 182=Green 183=Yellow
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
import sys
import csv
import json
import glob
import re
from typing import Optional, List, Dict


# === PATHS ===
BASE_GITHUB = str(paths.bcdata)
UPDATED_BCDATA = str(paths.root)
CATS_JSON = os.path.join(UPDATED_BCDATA, "cats_data.json")


def find_unitbuy_path() -> Optional[str]:
    """Returns path to unitbuy.csv from the latest BCData JP folder."""
    path = str(latest_version_dir(_WorkspacePath(BASE_GITHUB), 'jp') / 'DataLocal/unitbuy.csv')
    return path if os.path.exists(path) else None


def parse_materials(row: List[str], start_col: int, count: int = 5) -> List[List[int]]:
    """
    Extracts up to `count` (item_id, qty) pairs from row starting at start_col.
    Skips pairs where item_id == 0 or qty == 0.
    """
    materials = []
    for i in range(count):
        id_idx = start_col + i * 2
        qty_idx = id_idx + 1
        if qty_idx >= len(row):
            break
        try:
            item_id = int(row[id_idx])
            qty = int(row[qty_idx])
        except ValueError:
            continue
        if item_id > 0 and qty > 0:
            materials.append([item_id, qty])
    return materials


def parse_unitbuy(unitbuy_path: str) -> Dict[int, dict]:
    """
    Reads unitbuy.csv and returns a dict mapping cat_id (int) to
    evolution data dict with 'true_form' and/or 'ultra_form' keys.
    """
    evolution_map = {}

    with open(unitbuy_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        for cat_id, row in enumerate(reader):
            if len(row) < 49:
                continue

            try:
                level_true = int(row[25])
                xp_true = int(row[27])
                level_ultra = int(row[26])
                xp_ultra = int(row[38])
            except (ValueError, IndexError):
                continue

            evolution: dict = {}

            if level_true >= 0 and xp_true > 0:
                true_materials = parse_materials(row, 28, 5)
                evolution["true_form"] = {
                    "level": level_true,
                    "xp": xp_true,
                    "materials": true_materials,
                }

            if level_ultra >= 0 and xp_ultra > 0:
                ultra_materials = parse_materials(row, 39, 5)
                evolution["ultra_form"] = {
                    "level": level_ultra,
                    "xp": xp_ultra,
                    "materials": ultra_materials,
                }

            if evolution:
                evolution_map[cat_id] = evolution

    return evolution_map


def save_compact(data: dict, path: str) -> None:
    """Saves JSON with the same compact stats-array style as actualizar_cats_info.py."""
    json_string = json.dumps(data, indent=4, ensure_ascii=False)
    compact = re.sub(
        r"\[\s+([\d,\s\-.]+)\s+\]",
        lambda m: "[" + "".join(m.group(1).split()) + "]",
        json_string,
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(compact)


def main() -> None:
    print("🔍 Buscando unitbuy.csv...")
    unitbuy_path = find_unitbuy_path()
    if not unitbuy_path:
        raise RuntimeError(f"❌ No se encontró unitbuy.csv en ninguna carpeta *jp de {BASE_GITHUB}")
        return
    print(f"📂 Usando: {unitbuy_path}")

    print("📊 Parseando costes de evolución...")
    evolution_map = parse_unitbuy(unitbuy_path)
    print(f"   {len(evolution_map)} unidades con datos de evolución por catfruit")

    print(f"📖 Cargando {CATS_JSON}...")
    if not os.path.exists(CATS_JSON):
        raise RuntimeError(f"❌ No se encontró cats_data.json. Ejecuta primero actualizar_cats_info.py")
        return

    with open(CATS_JSON, "r", encoding="utf-8") as f:
        cats_data = json.load(f)

    print("✏️  Añadiendo datos de evolución a cada unidad...")
    updated = 0
    missing = 0
    for cat_id, evolution in evolution_map.items():
        key = str(cat_id).zfill(3)
        if key in cats_data.get("units", {}):
            cats_data["units"][key]["info"]["evolution"] = evolution
            updated += 1
        else:
            missing += 1

    print(f"💾 Guardando cats_data.json...")
    save_compact(cats_data, CATS_JSON)

    print("-" * 50)
    print(f"✅ ¡Hecho! {updated} unidades actualizadas con costes de evolución.")
    if missing:
        print(f"⚠️  {missing} IDs de evolución no encontrados en cats_data.json (gatos fuera de rango).")


if __name__ == "__main__":
    run_generator(main)
