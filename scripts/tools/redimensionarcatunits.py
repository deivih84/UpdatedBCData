# Both direct invocation and python -m work from any current directory.
import os as _workspace_os
import sys as _workspace_sys
from pathlib import Path as _WorkspacePath
if __package__ in (None, ''):
    _workspace_sys.path.insert(0, str(_WorkspacePath(__file__).resolve().parents[2]))
from workspace_paths import Workspace, latest_version_dir, run_generator
paths = Workspace.load(_workspace_os.environ.get('UPDATED_BCDATA_ROOT'))

from PIL import Image
import os

def recortar_bordes(ruta_imagen, ancho_deseado, alto_deseado):
    """
    Recorta los bordes de una imagen PNG a un tamaño específico.

    Args:
        ruta_imagen (str): La ruta al archivo de imagen PNG.
        ancho_deseado (int): El ancho deseado en píxeles.
        alto_deseado (int): El alto deseado en píxeles.
    """
    try:
        imagen = Image.open(ruta_imagen)
        ancho_original, alto_original = imagen.size

        # Calcula las coordenadas para el recorte
        izquierda = (ancho_original - ancho_deseado) // 2
        arriba = (alto_original - alto_deseado) // 2
        derecha = izquierda + ancho_deseado
        abajo = arriba + alto_deseado

        imagen_recortada = imagen.crop((izquierda, arriba, derecha, abajo))
        imagen_recortada.save(ruta_imagen)
        print(f"Bordes recortados: {os.path.basename(ruta_imagen)}")
    except Exception as e:
        print(f"Error al procesar {os.path.basename(ruta_imagen)}: {e}")

def procesar_carpeta(ruta_carpeta, ancho_deseado, alto_deseado):
    """
    Procesa todas las imágenes PNG en una carpeta y recorta sus bordes.

    Args:
        ruta_carpeta (str): La ruta a la carpeta que contiene las imágenes PNG.
        ancho_deseado (int): El ancho deseado en píxeles.
        alto_deseado (int): El alto deseado en píxeles.
    """
    for nombre_archivo in os.listdir(ruta_carpeta):
        if nombre_archivo.lower().endswith(".png"):
            ruta_imagen = os.path.join(ruta_carpeta, nombre_archivo)
            recortar_bordes(ruta_imagen, ancho_deseado, alto_deseado)

# Ejemplo de uso:
def main():
    import argparse
    parser = argparse.ArgumentParser(description='Crop PNGs in place in an explicitly selected folder')
    parser.add_argument('folder', type=_WorkspacePath)
    parser.add_argument('--width', type=int, default=110)
    parser.add_argument('--height', type=int, default=85)
    args = parser.parse_args()
    procesar_carpeta(args.folder, args.width, args.height)


if __name__ == '__main__':
    main()
