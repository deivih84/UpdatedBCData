# Both direct invocation and python -m work from any current directory.
import os as _workspace_os
import sys as _workspace_sys
from pathlib import Path as _WorkspacePath
if __package__ in (None, ''):
    _workspace_sys.path.insert(0, str(_WorkspacePath(__file__).resolve().parents[2]))
from workspace_paths import Workspace, latest_version_dir, run_generator
paths = Workspace.load(_workspace_os.environ.get('UPDATED_BCDATA_ROOT'))

import requests
import pandas as pd
import os
import re
import glob
from io import StringIO

# 📂 Rutas
PATH_ASSETS_DATA = str(paths.data)
PATH_NAMES = os.path.join(PATH_ASSETS_DATA, 'names.txt')
BASE_BCDATA = str(paths.bcdata)
URL = "https://battlecats.miraheze.org/wiki/Cat_Release_Order"

def buscar_ruta_jp_reciente():
    """Devuelve la ruta DataLocal de la versión JP más reciente de BCData."""
    return str(latest_version_dir(_WorkspacePath(BASE_BCDATA), 'jp') / 'DataLocal')


def preserve_published_names(lines, public_json):
    import json
    if not _WorkspacePath(public_json).is_file():
        return lines
    units = json.loads(_WorkspacePath(public_json).read_text(encoding='utf-8'))['units']
    result = []
    for line in lines:
        fields = [field.strip() for field in line.split('\t')]
        unit = units.get(fields[0].zfill(3)) or units.get(fields[0])
        if unit and len(fields) >= 5:
            info = unit['info']
            fields[2] = info.get('name_basic', fields[2])
            fields[3] = info.get('names_evolved', fields[3])
            line = ' \t'.join(fields)
        result.append(line)
    return result

def obtener_max_id_local():
    """Escanea BCData DataLocal para encontrar el unit***.csv más alto."""
    unit_dir = buscar_ruta_jp_reciente()
    if not unit_dir or not os.path.exists(unit_dir):
        return 0

    max_id = 0
    patron = re.compile(r'unit(\d+)\.csv')
    for archivo in os.listdir(unit_dir):
        match = patron.match(archivo)
        if match:
            id_actual = int(match.group(1))
            if id_actual > max_id:
                max_id = id_actual
    return max_id

def contar_lineas_csv(ruta_csv):
    """Cuenta cuántas líneas tiene el archivo CSV de la unidad."""
    if not os.path.exists(ruta_csv):
        return 0
    try:
        with open(ruta_csv, 'r', encoding='utf-8') as f:
            return sum(1 for line in f if line.strip())
    except:
        return 0

def actualizar_names_inteligente():
    print(f"🌐 Paso 1: Obteniendo datos de la Wiki...")

    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}

    try:
        # 1. Obtener datos de la Wiki
        response = requests.get(URL, headers=headers, timeout=60)
        response.raise_for_status()
        df_wiki = pd.read_html(StringIO(response.text))[0]

        # Quitamos a Cat God (fila 0)
        df_wiki = df_wiki.iloc[1:]

        # 2. Mapear Wiki a diccionario {id: fila}
        dict_wiki = {}
        for _, fila in df_wiki.iterrows():
            try:
                c_id = int(pd.to_numeric(fila.iloc[0], errors='coerce'))
                dict_wiki[c_id] = fila
            except:
                continue

        # 3. Determinar el rango de IDs
        max_id_local = obtener_max_id_local()
        max_id_wiki = max(dict_wiki.keys()) if dict_wiki else 0
        limite_final = max(max_id_local, max_id_wiki)

        print(f"📊 Wiki: {max_id_wiki} IDs | Local: {max_id_local} IDs.")
        lineas_finales = []

        # 4. Construir el archivo línea a línea
        for i in range(limite_final):
            cat_id = str(i)

            if i in dict_wiki:
                # --- CASO A: DATOS DE LA WIKI ---
                fila = dict_wiki[i]
                num_cols = len(fila)

                rarity = str(fila.iloc[1]).strip()
                basic_name = str(fila.iloc[2]).strip()

                if num_cols >= 6:
                    evol1 = str(fila.iloc[3]).strip() if pd.notna(fila.iloc[3]) else ""
                    evol2 = str(fila.iloc[4]).strip() if pd.notna(fila.iloc[4]) else ""
                    unlock = str(fila.iloc[5]).strip() if pd.notna(fila.iloc[5]) else ""

                    if evol1 and evol2 and evol2.lower() != "n/a":
                        evol_final = f"{evol1} / {evol2}"
                    else:
                        evol_final = evol1 if evol1 else (evol2 if evol2 else "N/A")
                else:
                    evol_final = str(fila.iloc[3]).strip() if pd.notna(fila.iloc[3]) else "N/A"
                    unlock = str(fila.iloc[4]).strip() if pd.notna(fila.iloc[4]) else ""

            else:
                # --- CASO B: PLACEHOLDER (No está en Wiki) ---
                unit_dir = buscar_ruta_jp_reciente() or PATH_ASSETS_DATA
                ruta_csv = os.path.join(unit_dir, f"unit{i+1:03d}.csv")
                if not os.path.exists(ruta_csv):
                    ruta_csv = os.path.join(unit_dir, f"unit{i+1}.csv")

                num_lineas = contar_lineas_csv(ruta_csv)

                rarity = "UR" # Usamos UR como valor por defecto en placeholders
                basic_name = f"{i}-1"
                unlock = "?"

                if num_lineas <= 1:
                    # Formato para 1 sola forma (o ninguna)
                    evol_final = "N/A"
                else:
                    # Formato para 2 o 3 formas
                    evol_final = f"{i}-2 / {i}-3"

            # Construir línea con el separador de CatStats (Espacio + Tab + Espacio)
            partes = [cat_id, rarity, basic_name, evol_final, unlock]
            lineas_finales.append(" \t".join(partes))

        lineas_finales = preserve_published_names(lineas_finales, paths.root / 'cats_data.json')
        # 5. Guardar el archivo
        print(f"💾 Guardando en {os.path.basename(PATH_NAMES)}...")
        with open(PATH_NAMES, 'w', encoding='utf-8') as f:
            f.write("\n".join(lineas_finales))

        print(f"✨ ¡Hecho, David! Archivo sincronizado y validado con tus CSVs locales. 🐈✅")

    except Exception as e:
        raise RuntimeError(f"❌ Error crítico: {e}")

if __name__ == "__main__":
    run_generator(actualizar_names_inteligente)
