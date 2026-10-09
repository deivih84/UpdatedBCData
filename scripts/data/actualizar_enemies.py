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

# 📂 Rutas de tu entorno
BASE_GITHUB = str(paths.bcdata)
# Destino final en los assets de tu App
PATH_DESTINO = str(paths.data / 'enemy_data.csv')

def buscar_ruta_jp_reciente():
    """Busca la versión más reciente que termine en 'jp'."""
    return str(latest_version_dir(_WorkspacePath(BASE_GITHUB), 'jp') / 'DataLocal/t_unit.csv')

def actualizar_estadisticas_enemigos():
    print("🚀 Iniciando actualización de estadísticas de enemigos...")

    # 1. Localizar el archivo t_unit.csv en la versión JP
    ruta_maestra = buscar_ruta_jp_reciente()

    if not ruta_maestra or not os.path.exists(ruta_maestra):
        raise RuntimeError(f"❌ Error: No se encontró 't_unit.csv' en las carpetas JP de {BASE_GITHUB}.")
        return

    nombre_version = os.path.basename(os.path.dirname(os.path.dirname(ruta_maestra)))
    print(f"📂 Archivo de estadísticas detectado en: {nombre_version}")

    # 2. Asegurarnos de que la carpeta de destino existe
    os.makedirs(os.path.dirname(PATH_DESTINO), exist_ok=True)

    # 3. Copiar y renombrar a 'enemy_data.csv'
    try:
        shutil.copy2(ruta_maestra, PATH_DESTINO)
        print(f"✅ ¡Éxito! Estadísticas copiadas y renombradas a: {os.path.basename(PATH_DESTINO)}")
        print(f"📍 Destino: {PATH_DESTINO}")
    except Exception as e:
        raise RuntimeError(f"❌ Ocurrió un error al copiar las estadísticas: {e}")

if __name__ == "__main__":
    run_generator(actualizar_estadisticas_enemigos)
