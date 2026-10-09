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
PATH_COMBOS = str(paths.data / 'combos.csv')
PATH_NAMES = str(paths.data / 'combo_names.txt')

def buscar_rutas_maestras():
    ultima = str(latest_version_dir(_WorkspacePath(BASE_GITHUB), 'en'))
    return (os.path.join(ultima, "DataLocal", "NyancomboData.csv"),
            os.path.join(ultima, "resLocal", "Nyancombo_en.csv"))

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

    # --- Actualizar combos.csv ---
    nuevas_filas_data.to_csv(PATH_COMBOS, mode='a', index=False, header=False)
    print(f"📝 {os.path.basename(PATH_COMBOS)} actualizado.")

    # --- Actualizar combo_names.txt ---
    try:
        with open(ruta_m_names, 'r', encoding='utf-8', errors='ignore') as f:
            nombres_maestros = [l.strip() for l in f.readlines()]

        # 🛠️ AJUSTE DE ÍNDICE (Header offset)
        # Fila i en Data (con cabecera) -> Línea i-1 en Nombres (sin cabecera)
        nombres_nuevos = []
        for i in nuevas_filas_data.index:
            idx_nombre = i - 1
            if 0 <= idx_nombre < len(nombres_maestros):
                nombres_nuevos.append(nombres_maestros[idx_nombre])
            else:
                print(f"⚠️ Aviso: No se encontró nombre para la fila {i} del maestro.")

        if nombres_nuevos:
            with open(PATH_NAMES, 'a', encoding='utf-8') as f:
                for nombre in nombres_nuevos:
                    f.write(f"\n{nombre}")
            print(f"📝 {os.path.basename(PATH_NAMES)} actualizado.")

    except Exception as e:
        raise RuntimeError(f"❌ Error al actualizar nombres: {e}")

if __name__ == "__main__":
    run_generator(sincronizar_todo)
