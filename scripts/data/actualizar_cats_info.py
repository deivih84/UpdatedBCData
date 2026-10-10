# Both direct invocation and python -m work from any current directory.
import os as _workspace_os
import sys as _workspace_sys
from pathlib import Path as _WorkspacePath
if __package__ in (None, ''):
    _workspace_sys.path.insert(0, str(_WorkspacePath(__file__).resolve().parents[2]))
from workspace_paths import Workspace, latest_version_dir, run_generator
paths = Workspace.load(_workspace_os.environ.get('UPDATED_BCDATA_ROOT'))

import os
import csv
import json
import re
import glob
import sys
from pathlib import Path
from datetime import datetime
from scripts.data.pc_cats import load_pc_source, merge_pc_source

BASE_BCDATA = str(paths.bcdata)


def merge_preserved_medals(generated_units, previous_data_sources):
    """Copy existing per-cat medals into freshly generated unit data."""
    medals_by_unit = {}

    for previous_data in previous_data_sources:
        if not isinstance(previous_data, dict):
            continue
        previous_units = previous_data.get("units", {})
        if not isinstance(previous_units, dict):
            continue

        for unit_id, unit_data in previous_units.items():
            if not isinstance(unit_data, dict):
                continue
            info = unit_data.get("info", {})
            medals = info.get("medals", []) if isinstance(info, dict) else []
            if not isinstance(medals, list) or not medals:
                continue

            preserved = medals_by_unit.setdefault(unit_id, [])
            seen = {
                (medal.get("iconIdx"), medal.get("name"))
                for medal in preserved
                if isinstance(medal, dict)
            }
            for medal in medals:
                if not isinstance(medal, dict):
                    continue
                identity = (medal.get("iconIdx"), medal.get("name"))
                if identity not in seen:
                    preserved.append(medal)
                    seen.add(identity)

    for unit_id, medals in medals_by_unit.items():
        generated_unit = generated_units.get(unit_id)
        if not isinstance(generated_unit, dict):
            continue
        info = generated_unit.get("info")
        if isinstance(info, dict) and medals:
            info["medals"] = medals

    return generated_units


def load_previous_cat_data(paths):
    """Load valid cats_data JSON documents from preservation sources."""
    previous_data_sources = []
    for path in paths:
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as source:
                previous_data_sources.append(json.load(source))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            print(f"⚠️ No se pudieron conservar medallas desde {path}: {exc}")
    return previous_data_sources


def list_unit_files(unit_dir):
    """Return every Battle Cats unit CSV, including historic short schemas."""
    pattern = re.compile(r"unit\d+\.csv")
    return sorted(
        filename
        for filename in os.listdir(unit_dir)
        if pattern.fullmatch(filename)
    )


def buscar_ruta_jp_reciente():
    """Devuelve la ruta DataLocal de la versión JP más reciente de BCData."""
    return str(latest_version_dir(_WorkspacePath(BASE_BCDATA), 'jp') / 'DataLocal')


def game_version_from_unit_dir(unit_dir):
    """Return the semantic game version encoded by a JP BCData directory."""
    version_dir = os.path.basename(os.path.dirname(os.path.normpath(unit_dir)))
    match = re.fullmatch(r"(\d+\.\d+\.\d+)jp", version_dir)
    if not match:
        raise ValueError(f"Ruta BCData JP no válida: {unit_dir}")
    return match.group(1)


def build_talents_data(source_dir):
    """
    Reads skill_acquisition.csv and skill_level.csv from source_dir.
    Returns {cat_id_int: flat_array} where flat_array is:
      [typeId, abilityId, maxLevel, npCost, r0min, r0max, r1min, r1max, r2min, r2max, r3min, r3max,  # slot A (11 values)
       ... for every slot present in the source row]
    Historical rows keep at least 8 slots; version 15.7 adds slots I-K.
    Only cats with at least one non-zero abilityId are included.
    """
    def safe_int(value, default=0):
        try:
            return int(str(value).strip())
        except (ValueError, TypeError):
            return default

    # 1. Build {lvId: [costs per level]} from skill_level.csv
    skill_level_map = {}
    skill_level_path = os.path.join(source_dir, "skill_level.csv")
    if os.path.exists(skill_level_path):
        with open(skill_level_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header row
            for row in reader:
                if not row:
                    continue
                lv_id = safe_int(row[0], default=None)
                if lv_id is not None:
                    costs = [safe_int(x) for x in row[1:] if str(x).strip()]
                    skill_level_map[lv_id] = costs
    else:
        print(f"⚠️ skill_level.csv no encontrado en {skill_level_path}, NP costs serán 0")

    # 2. Parse skill_acquisition.csv
    talents_dict = {}
    skill_acq_path = os.path.join(source_dir, "skill_acquisition.csv")
    if not os.path.exists(skill_acq_path):
        print(f"⚠️ skill_acquisition.csv no encontrado en {skill_acq_path}, omitiendo talentos")
        return talents_dict

    with open(skill_acq_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)  # skip header row
        for row in reader:
            if not row:
                continue
            cat_id = safe_int(row[0], default=None)
            if cat_id is None:
                continue
            type_id = safe_int(row[1]) if len(row) > 1 else 0

            flat = [type_id]
            has_any_talent = False

            for i in range(max(8, (len(row) - 2) // 14)):
                offset = 2 + i * 14
                ability_id = safe_int(row[offset]) if len(row) > offset else 0

                if ability_id != 0:
                    max_level_raw = safe_int(row[offset + 1]) if len(row) > offset + 1 else 0
                    max_level = max(1, max_level_raw)
                else:
                    max_level = 0

                # 4 effect range pairs at offset+2..offset+9
                ranges = []
                for j in range(4):
                    r_min = safe_int(row[offset + 2 + j * 2]) if len(row) > offset + 2 + j * 2 else 0
                    r_max = safe_int(row[offset + 3 + j * 2]) if len(row) > offset + 3 + j * 2 else 0
                    ranges.extend([r_min, r_max])

                # lvId at offset+11; compute npCost
                lv_id = safe_int(row[offset + 11], default=-1) if len(row) > offset + 11 else -1
                np_cost = 0
                if lv_id != -1 and max_level > 0:
                    costs = skill_level_map.get(lv_id, [])
                    np_cost = sum(costs[:max_level])

                # Slot: [abilityId, maxLevel, npCost, r0min, r0max, r1min, r1max, r2min, r2max, r3min, r3max]
                flat.extend([ability_id, max_level, np_cost] + ranges)

                if ability_id != 0:
                    has_any_talent = True

            if has_any_talent:
                talents_dict[cat_id] = flat

    print(f"🎯 Talentos cargados: {len(talents_dict)} unidades con talentos")
    return talents_dict


def master_sync():
    print("🚀 Iniciando el proceso de fusión de datos con formato compacto...")
    pc_source = load_pc_source(paths.root / 'data/inputs/cats_pc.json')

    # --- RUTAS ---
    # Asegúrate de que estas carpetas existan
    source_dir = str(paths.data)
    names_file = os.path.join(source_dir, "names.txt")

    # 0. Cargar datos de talentos
    print("🎯 Cargando datos de talentos...")
    talents_data = build_talents_data(source_dir)
    output_file = str(paths.root / 'cats_data.json')
    medal_source_paths = [
        output_file,
        os.path.join(source_dir, "cats_data.json"),
        os.environ.get("CATS_MEDAL_SOURCE"),
    ]
    previous_cat_data = load_previous_cat_data(medal_source_paths)

    # 1. Parsear names.txt
    names_map = {}
    if os.path.exists(names_file):
        print(f"📖 Analizando nombres en: {names_file}")
        with open(names_file, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split('\t')
                if len(parts) >= 5:
                    unit_id = parts[0].strip().zfill(3)
                    evolved_names_str = parts[3].strip()
                    num_evolved = len([n for n in evolved_names_str.split('/') if n.strip()]) if evolved_names_str else 0
                    total_named_forms = 1 + num_evolved

                    names_map[unit_id] = {
                        "rarity": parts[1].strip(),
                        "name_basic": parts[2].strip(),
                        "names_evolved": evolved_names_str,
                        "obtain_method": parts[4].strip(),
                        "total_forms": total_named_forms
                    }
    else:
        raise RuntimeError(f"❌ Error: No se encontró el archivo de nombres en {names_file}")
        return

    # 2. Procesar CSVs desde BCData JP
    unit_dir = buscar_ruta_jp_reciente()
    if not unit_dir or not os.path.exists(unit_dir):
        raise RuntimeError(f"❌ Error: No se encontró BCData JP en {BASE_BCDATA}")
        return
    current_version = game_version_from_unit_dir(unit_dir)

    units_dict = {}
    pattern = re.compile(r"unit(\d+)\.csv")

    files = list_unit_files(unit_dir)

    if not files:
        raise RuntimeError(f"❌ Error: No se encontraron archivos unit*.csv en {unit_dir}")
        return

    print(f"🔄 Procesando {len(files)} archivos CSV desde {os.path.basename(os.path.dirname(unit_dir))}...")

    for filename in files:
        file_id_int = int(pattern.match(filename).group(1))
        target_id_int = file_id_int - 1
        if target_id_int < 0: continue

        unit_id_str = str(target_id_int).zfill(3)
        file_path = os.path.join(unit_dir, filename)
        info = names_map.get(unit_id_str, {"rarity": "?", "name_basic": "Unknown", "names_evolved": "", "obtain_method": "", "total_forms": 99})

        stats = []
        try:
            with open(file_path, 'r', encoding='utf-8') as csvfile:
                reader = csv.reader(csvfile)
                for row in reader:
                    clean_row = []
                    for cell in row:
                        data_part = cell.split('//')[0].strip()
                        if not data_part: continue
                        try:
                            clean_row.append(float(data_part) if '.' in data_part else int(data_part))
                        except ValueError:
                            clean_row.append(data_part)
                    if clean_row: stats.append(clean_row)

            # Truncado según formas reales
            allowed_forms = info["total_forms"]
            if len(stats) > allowed_forms:
                stats = stats[:allowed_forms]

            unit_data = {
                "info": {k: v for k, v in info.items() if k != "total_forms"},
                "stats": stats
            }
            if target_id_int in talents_data:
                unit_data["talents"] = talents_data[target_id_int]
            units_dict[unit_id_str] = unit_data
        except Exception as e:
            print(f"⚠️ Error en {filename}: {e}")

    merge_preserved_medals(units_dict, previous_cat_data)
    preserved_medal_count = sum(
        len(unit["info"].get("medals", []))
        for unit in units_dict.values()
    )
    print(f"🏅 Medallas de gatos conservadas: {preserved_medal_count}")

    # 4. Guardar JSON con formato de FILA COMPACTA 🪄
    final_data = {
        "metadata": {
            "version": current_version,
            "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_units": len(units_dict)
        },
        "units": units_dict
    }
    final_data = merge_pc_source(final_data, pc_source)

    # Provisional values from the merged archives. update_all refreshes them
    # again after the selected version's incremental animation sync finishes.
    public_root = Path(output_file).parent
    sys.path.insert(0, str(public_root))
    from update_cat_backswings import prepare_backswings
    missing_backswings = prepare_backswings(final_data, public_root / 'cats')
    for form in missing_backswings:
        print(f"WARNING: {form}: backswing sin animación de ataque; null")

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # Generamos el JSON como texto
    json_string = json.dumps(final_data, indent=4, ensure_ascii=False)

    # Aplicamos Regex para poner los arrays de stats en una sola línea
    # Busca patrones de [ valor, valor, ... ] y los colapsa
    compact_json = re.sub(
        r'\[\s+([\d,\s\-.]+)\s+\]',
        lambda m: "[" + "".join(m.group(1).split()) + "]",
        json_string
    )

    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(compact_json)

    print("-" * 40)
    print(f"✅ ¡Hecho, David! Archivo generado en: {output_file}")
    print(f"📊 Versión: {current_version} | Unidades procesadas: {len(units_dict)}")

# --- ESTA PARTE ES IMPORTANTE PARA QUE EL SCRIPT CORRA ---
if __name__ == "__main__":
    run_generator(master_sync)
