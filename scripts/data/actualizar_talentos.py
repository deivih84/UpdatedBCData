# Both direct invocation and python -m work from any current directory.
import os as _workspace_os
import sys as _workspace_sys
from pathlib import Path as _WorkspacePath
if __package__ in (None, ''):
    _workspace_sys.path.insert(0, str(_WorkspacePath(__file__).resolve().parents[2]))
from workspace_paths import Workspace, latest_version_dir, run_generator
paths = Workspace.load(_workspace_os.environ.get('UPDATED_BCDATA_ROOT'))

import pandas as pd
import os
import glob

# 📂 Rutas
BASE_GITHUB = str(paths.bcdata)
PATH_APP = str(paths.data / 'skill_acquisition.csv')

# 🚫 IDs de talentos protegidos (Tus excepciones)
EXCEPCIONES = [105, 107, 258, 259, 261]

def buscar_ruta_jp_reciente():
    return str(latest_version_dir(_WorkspacePath(BASE_GITHUB), 'jp') / 'DataLocal/SkillAcquisition.csv')

def actualizar_talentos_con_cabecera():
    print("🚀 Iniciando actualización con protección de cabecera e IDs...")

    ruta_maestra = buscar_ruta_jp_reciente()
    if not ruta_maestra or not os.path.exists(ruta_maestra):
        raise RuntimeError("❌ Error: No se encontró el archivo maestro en GitHub.")
        return

    # 1. Cargar datos usando la primera línea como cabecera (header=0)
    print(f"📖 Cargando datos nuevos y detectando cabecera...")
    df_nuevo = pd.read_csv(ruta_maestra, header=0)

    # 2. Cargar tu archivo actual para rescatar la cabecera exacta y las excepciones
    if os.path.exists(PATH_APP):
        df_actual = pd.read_csv(PATH_APP, header=0)

        # Usamos los nombres de las columnas de TU archivo para que no cambien
        shared_columns = min(len(df_nuevo.columns), len(df_actual.columns))
        df_nuevo.columns = list(df_actual.columns[:shared_columns]) + list(df_nuevo.columns[shared_columns:])

        # El nombre de la primera columna (donde está el ID)
        col_id = df_actual.columns[0]
        print(f"📌 Columna de control detectada: '{col_id}'")

        # 3. Aplicar el escudo a tus excepciones
        for talent_id in EXCEPCIONES:
            # Buscamos la fila en tu archivo
            fila_protegida = df_actual[df_actual[col_id] == talent_id]

            if not fila_protegida.empty:
                # Si el ID existe en el nuevo, le damos el "cambiazo"
                if talent_id in df_nuevo[col_id].values:
                    df_nuevo.loc[df_nuevo[col_id] == talent_id, df_nuevo.columns[:shared_columns]] = fila_protegida.iloc[0, :shared_columns].values
                    print(f"🛡️ ID {talent_id}: Protegido y mantenido con éxito.")

    # 4. Guardar el archivo incluyendo la cabecera (header=True)
    print(f"💾 Guardando en {os.path.basename(PATH_APP)} con cabecera...")

    # index=False para que no añada números de fila al principio
    df_nuevo.to_csv(PATH_APP, index=False, header=True)

    print(f"✨ ¡Todo listo, David! Cabecera preservada y talentos actualizados. 🐈✅")

if __name__ == "__main__":
    run_generator(actualizar_talentos_con_cabecera)
