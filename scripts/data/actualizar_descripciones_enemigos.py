# Both direct invocation and python -m work from any current directory.
import os as _workspace_os
import sys as _workspace_sys
from pathlib import Path as _WorkspacePath
if __package__ in (None, ''):
    _workspace_sys.path.insert(0, str(_WorkspacePath(__file__).resolve().parents[2]))
from workspace_paths import Workspace, latest_version_dir, run_generator
paths = Workspace.load(_workspace_os.environ.get('UPDATED_BCDATA_ROOT'))

import os
import glob
import shutil

# 📂 Rutas Base
BASE_GITHUB = str(paths.bcdata)
BASE_DESTINO = str(paths.data)

def obtener_ultima_version(prefijo):
    try:
        return str(latest_version_dir(_WorkspacePath(BASE_GITHUB), prefijo))
    except FileNotFoundError:
        return None


def organizar_descripciones_enemigos():
    print("🚀 Iniciando sincronización de descripciones de enemigos...")

    # Configuración: Idioma : [Prefijo Carpeta, Subruta Interna, Sufijo Archivo]
    # Nota: Usamos ja para jp y ko para kr en el nombre del archivo csv
    config_idiomas = {
        # GRUPO A: Versiones independientes
        'en': ['en', 'resLocal', 'en'],
        'tw': ['tw', 'resLocal', 'tw'],
        'kr': ['kr', 'resLocal', 'ko'],
        'jp': ['jp', 'resLocal', 'ja'],

        # GRUPO B: Idiomas dentro de la versión global (en)
        'es': ['en', 'resLocal_es', 'es'],
        'fr': ['en', 'resLocal_fr', 'fr'],
        'it': ['en', 'resLocal_it', 'it'],
        'de': ['en', 'resLocal_de', 'de'],
        'th': ['en', 'resLocal_th', 'th']
    }

    for lang, config in config_idiomas.items():
        prefijo_version, subruta, sufijo_file = config
        print(f"\n🌐 Procesando idioma: [{lang.upper()}]")

        # 1. Localizar la versión más reciente
        ruta_version = obtener_ultima_version(prefijo_version)
        if not ruta_version:
            print(f"⚠️ No se encontró carpeta para *{prefijo_version}")
            continue

        # 2. Definir origen y destino
        # Origen: EnemyPictureBook_xx.csv
        nombre_origen = f"EnemyPictureBook_{sufijo_file}.csv"
        ruta_origen = os.path.join(ruta_version, subruta, nombre_origen)

        # Destino: enemy_descriptions_xx.tsv (Cambiamos extensión a .tsv)
        nombre_destino = f"enemy_descriptions_{lang}.tsv"
        ruta_final = os.path.join(BASE_DESTINO, nombre_destino)

        # 3. Copiar y renombrar
        if os.path.exists(ruta_origen):
            try:
                shutil.copy2(ruta_origen, ruta_final)
                print(f"✅ Convertido: {nombre_origen} -> {nombre_destino}")
            except Exception as e:
                raise RuntimeError(f"❌ Error al procesar {lang}: {e}")
        else:
            print(f"❓ No se encontró {nombre_origen} en {subruta}")

    print("\n✨ ¡Logrado, David! El bestiario de CatStats ya tiene todas sus descripciones listas. 🐈📖")

if __name__ == "__main__":
    run_generator(organizar_descripciones_enemigos)
