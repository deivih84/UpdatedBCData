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


def organizar_nombres_enemigos():
    print("🚀 Iniciando sincronización de nombres de enemigos...")

    # Configuración: Idioma : [Prefijo Carpeta, Subruta Interna]
    config_idiomas = {
        # GRUPO A: Versiones independientes (Carpeta propia)
        'en': ['en', 'resLocal'],
        'tw': ['tw', 'resLocal'],
        'kr': ['kr', 'resLocal'],
        'jp': ['jp', 'resLocal'],

        # GRUPO B: Idiomas dentro de la versión global (Carpeta resLocal_xx)
        'es': ['en', 'resLocal_es'],
        'fr': ['en', 'resLocal_fr'],
        'it': ['en', 'resLocal_it'],
        'de': ['en', 'resLocal_de'],
        'th': ['en', 'resLocal_th']
    }

    for lang, config in config_idiomas.items():
        prefijo_version, subruta = config
        print(f"\n🌐 Procesando idioma: [{lang.upper()}]")

        # 1. Localizar la carpeta de la versión más reciente
        ruta_version = obtener_ultima_version(prefijo_version)
        if not ruta_version:
            print(f"⚠️ No se encontró carpeta para *{prefijo_version}")
            continue

        # 2. Definir origen y destino
        # El archivo de origen siempre se llama 'Enemyname.tsv'
        ruta_origen = os.path.join(ruta_version, subruta, "Enemyname.tsv")
        # El archivo de destino será 'enemy_names_xx.tsv'
        nombre_destino = f"enemy_names_{lang}.tsv"
        ruta_final = os.path.join(BASE_DESTINO, nombre_destino)

        # 3. Copiar y Renombrar
        if os.path.exists(ruta_origen):
            try:
                shutil.copy2(ruta_origen, ruta_final)
                print(f"✅ Copiado: {os.path.basename(ruta_version)} -> {nombre_destino}")
            except Exception as e:
                raise RuntimeError(f"❌ Error al copiar {lang}: {e}")
        else:
            print(f"❓ No se encontró 'Enemyname.tsv' en {subruta}")

    print("\n✨ ¡Misión cumplida, David! Todos los enemigos están traducidos y organizados. 🐈👹")

if __name__ == "__main__":
    run_generator(organizar_nombres_enemigos)
