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
BASE_DESTINO = str(paths.data / 'descriptions')

def obtener_ultima_version(prefijo):
    try:
        return str(latest_version_dir(_WorkspacePath(BASE_GITHUB), prefijo))
    except FileNotFoundError:
        return None


def organizar_descripciones_final():
    print("🚀 Normalizando nombres de descripciones (JA->JP / KO->KR)...")

    # Configuración: Idioma : [Prefijo Carpeta, Subruta Interna, Sufijo Original]
    config_idiomas = {
        'en': ['en', 'resLocal', 'en'],
        'tw': ['tw', 'resLocal', 'tw'],
        'kr': ['kr', 'resLocal', 'ko'],  # Origen _ko -> Destino _kr
        'jp': ['jp', 'resLocal', 'ja'],  # Origen _ja -> Destino _jp
        'es': ['en', 'resLocal_es', 'es'],
        'fr': ['en', 'resLocal_fr', 'fr'],
        'it': ['en', 'resLocal_it', 'it'],
        'de': ['en', 'resLocal_de', 'de'],
        'th': ['en', 'resLocal_th', 'th']
    }

    for lang, config in config_idiomas.items():
        prefijo_version, subruta, sufijo_orig = config
        print(f"\n🌐 Procesando idioma: [{lang.upper()}]")

        ruta_version = obtener_ultima_version(prefijo_version)
        if not ruta_version:
            print(f"⚠️ No se encontró carpeta para *{prefijo_version}")
            continue

        ruta_origen = os.path.join(ruta_version, subruta)
        ruta_destino_lang = os.path.join(BASE_DESTINO, lang)
        os.makedirs(ruta_destino_lang, exist_ok=True)

        # Buscamos con el sufijo que viene en el GitHub (_ja, _ko...)
        patron_busqueda = os.path.join(ruta_origen, f"Unit_Explanation*_{sufijo_orig}.csv")
        archivos = glob.glob(patron_busqueda)

        if not archivos:
            print(f"❓ No se encontraron archivos '_{sufijo_orig}' en {subruta}")
            continue

        print(f"📦 Renombrando y copiando {len(archivos)} archivos...")

        # --- LÓGICA DE RENOMBRADO ---
        for r_file in archivos:
            nombre_orig = os.path.basename(r_file).lower()

            # Reemplazamos el sufijo del archivo por el nombre de la carpeta
            # Ejemplo: unit_explanation001_ja.csv -> unit_explanation001_jp.csv
            nombre_nuevo = nombre_orig.replace(f"_{sufijo_orig}.csv", f"_{lang}.csv")

            shutil.copy2(r_file, os.path.join(ruta_destino_lang, nombre_nuevo))

    print("\n✨ ¡Misión cumplida, David! Todos los nombres están normalizados. 🐈🌍")

if __name__ == "__main__":
    run_generator(organizar_descripciones_final)
