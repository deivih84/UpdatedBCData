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
import re

# 📂 Rutas
BASE_GITHUB = str(paths.bcdata)
PATH_COMBOS = str(paths.data / 'combos.csv')
PATH_NAMES = str(paths.data / 'combo_names.txt')

def buscar_rutas_maestras():
    candidates = []
    for region, language in [('en', 'en'), ('jp', 'ja')]:
        try:
            source = latest_version_dir(_WorkspacePath(BASE_GITHUB), region)
        except FileNotFoundError:
            continue
        version = tuple(int(part) for part in re.findall(r'\d+', source.name))
        candidates.append((version, region == 'en', source, language))
    if not candidates:
        raise FileNotFoundError('No extracted EN/JP combo source')
    _, _, source, language = max(candidates)
    return (str(source / 'DataLocal/NyancomboData.csv'),
            str(source / f'resLocal/Nyancombo_{language}.csv'))


def sincronizar_todo():
    ruta_m_data, ruta_m_names = buscar_rutas_maestras()
    if not ruta_m_data or not os.path.exists(ruta_m_data):
        raise RuntimeError("❌ No se encontró el repositorio de GitHub.")
        return

    print(f"📦 Analizando versión: {os.path.basename(os.path.dirname(os.path.dirname(ruta_m_data)))}")

    # 1. Cargar tus archivos actuales
    df_actual = pd.read_csv(PATH_COMBOS, header=None)

    # 2. Cargar el maestro de datos
    df_maestro = pd.read_csv(ruta_m_data, header=None)

    # --- LÓGICA DEFENSIVA ---
    num_cols_actual = df_actual.shape[1]
    ultima_fila_actual = df_actual.iloc[-1].tolist()

    print(f"🔍 Buscando huella comparando {num_cols_actual} columnas...")

    df_maestro_recortado = df_maestro.iloc[:, :num_cols_actual]
    coincidencias = df_maestro_recortado[(df_maestro_recortado == ultima_fila_actual).all(axis=1)]

    if coincidencias.empty:
        raise ValueError('Existing combo fingerprint not found in selected source; refusing append')

    indice_ultimo = coincidencias.index[-1]
    nuevas_filas_data = df_maestro.iloc[indice_ultimo + 1:]

    if nuevas_filas_data.empty:
        print("✅ Las últimas líneas coinciden. ¡No hay nada nuevo! 🐈")
        return

    print(f"✨ ¡Se han detectado {len(nuevas_filas_data)} combos nuevos!")

    # Source data has no header: names use the same physical row index.
    # Resolve every name before writing either accumulated file.
    with open(ruta_m_names, 'r', encoding='utf-8') as handle:
        nombres_maestros = handle.read().splitlines()
    nombres_nuevos = []
    for index in nuevas_filas_data.index:
        if index >= len(nombres_maestros) or not nombres_maestros[index].strip():
            raise ValueError(f'Missing source name for combo row {index}')
        nombres_nuevos.append(nombres_maestros[index].strip())
    previous_names = _WorkspacePath(PATH_NAMES).read_text(encoding='utf-8').rstrip('\n')
    nuevas_filas_data.to_csv(PATH_COMBOS, mode='a', index=False, header=False)
    _WorkspacePath(PATH_NAMES).write_text(
        previous_names + '\n' + '\n'.join(nombres_nuevos) + '\n', encoding='utf-8')
    print('📝 Datos y nombres de combos actualizados por el mismo índice fuente.')


if __name__ == "__main__":
    run_generator(sincronizar_todo)
