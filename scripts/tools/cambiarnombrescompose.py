# Both direct invocation and python -m work from any current directory.
import os as _workspace_os
import sys as _workspace_sys
from pathlib import Path as _WorkspacePath
if __package__ in (None, ''):
    _workspace_sys.path.insert(0, str(_WorkspacePath(__file__).resolve().parents[2]))
from workspace_paths import Workspace, latest_version_dir, run_generator
paths = Workspace.load(_workspace_os.environ.get('UPDATED_BCDATA_ROOT'))

import os

def renombrar_archivos(ruta_carpeta):
    """
    Renombra todos los archivos en una carpeta, convirtiendo mayúsculas a minúsculas y reemplazando espacios con guiones bajos.

    Args:
        ruta_carpeta (str): La ruta a la carpeta que contiene los archivos.
    """
    for nombre_archivo in os.listdir(ruta_carpeta):
        ruta_archivo_antiguo = os.path.join(ruta_carpeta, nombre_archivo)
        if os.path.isfile(ruta_archivo_antiguo):  # Verifica que sea un archivo
            nombre_archivo_nuevo = nombre_archivo.lower().replace(" ", "_")
            ruta_archivo_nuevo = os.path.join(ruta_carpeta, nombre_archivo_nuevo)
            os.rename(ruta_archivo_antiguo, ruta_archivo_nuevo)
            print(f"Archivo renombrado: {nombre_archivo} -> {nombre_archivo_nuevo}")

# Ejemplo de uso:
def main():
    import argparse
    parser = argparse.ArgumentParser(description='Normalize names in an explicitly selected folder')
    parser.add_argument('folder', type=_WorkspacePath)
    args = parser.parse_args()
    names = [p.name.lower().replace(' ', '_') for p in args.folder.iterdir() if p.is_file()]
    if len(names) != len(set(names)):
        raise ValueError('Names collide after normalization')
    renombrar_archivos(args.folder)


if __name__ == '__main__':
    main()
