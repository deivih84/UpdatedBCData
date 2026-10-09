# Both direct invocation and python -m work from any current directory.
import os as _workspace_os
import sys as _workspace_sys
from pathlib import Path as _WorkspacePath
if __package__ in (None, ''):
    _workspace_sys.path.insert(0, str(_WorkspacePath(__file__).resolve().parents[2]))
from workspace_paths import Workspace, latest_version_dir, run_generator
paths = Workspace.load(_workspace_os.environ.get('UPDATED_BCDATA_ROOT'))

import re
import os

def generar_mapeo_exacto():
    # 📂 Rutas
    path_names = str(_WorkspacePath(__file__).parent / 'names.txt')
    path_gatchas = str(_WorkspacePath(__file__).parent / 'gatchas.txt')

    if not os.path.exists(path_names) or not os.path.exists(path_gatchas):
        raise RuntimeError("❌ Error: Asegúrate de que names.txt y gatchas.txt estén aquí.")
        return

    # --- 1. CARGAR DICCIONARIO DE NOMBRES ---
    nombre_a_id = {}
    with open(path_names, 'r', encoding='utf-8') as f:
        for linea in f:
            linea_limpia = re.sub(r'\\', '', linea)
            partes = linea_limpia.strip().split('\t')
            if len(partes) >= 3:
                cat_id = partes[0].strip()
                nombre_basico = partes[2].strip().lower()
                nombre_a_id[nombre_basico] = int(cat_id)

    # --- 2. LEER Y LIMPIAR GATCHAS.TXT ---
    with open(path_gatchas, 'r', encoding='utf-8') as f:
        contenido = f.read()

    contenido_limpio = re.sub(r'\\', '', contenido)
    contenido_limpio = " ".join(contenido_limpio.split())

    # --- 3. EXTRAER PORCENTAJES (FORMATO PERSONALIZADO) ---
    config_porcentajes = {
        "Rare": "rareChance",
        "Super": "supaChance",
        "Uber": "uberChance",
        "Legendary": "legendChance"
    }

    for label, var_name in config_porcentajes.items():
        # Busca "Rare: 69.3%" y captura el número
        match = re.search(rf"{label}:\s*([\d.]+)%", contenido_limpio)

        if match:
            valor_float = float(match.group(1))
            valor_int = int(round(valor_float * 100))

            # ✅ CAMBIO AQUÍ: Formato "clave":valor,
            print(f'\t"{var_name}":{valor_int},')
        else:
            # Si no hay probabilidad (ej: Legendary a veces es 0 o no sale), ponemos 0
            print(f'"{var_name}":0,')

    # --- 4. EXTRAER LISTAS DE IDs ---
    patrones_listas = {
        "rares": r"Rare:.*?\(.*?cats\)(.*?)(?=Super:|$)",
        "super_rares": r"Super:.*?\(.*?cats\)(.*?)(?=Uber:|$)",
        "ubers": r"Uber:.*?\(.*?cats\)(.*?)(?=Legendary:|$)",
        "legends": r"Legendary:.*?\(.*?cats\)(.*?)$"
    }

    for clave, regex in patrones_listas.items():
        bloque = re.search(regex, contenido_limpio)
        ids = []
        if bloque:
            texto_gatos = bloque.group(1)
            nombres_encontrados = re.findall(r'\d+\s+(.*?)(?:,|$)', texto_gatos)

            for nombre in nombres_encontrados:
                nombre_limpio = nombre.strip().lower()
                if nombre_limpio in nombre_a_id:
                    ids.append(nombre_a_id[nombre_limpio])

        print(f'\t"{clave}": {ids},')

if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description="Historical exact-name mapper").parse_args()
    generar_mapeo_exacto()
