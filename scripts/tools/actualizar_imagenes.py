"""Crop PNGs into public images and optional app drawables; keep originals."""
import argparse
import sys
from pathlib import Path

if __package__ in (None, ''):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from PIL import Image
from workspace_paths import Workspace


def process_images(source, public, drawables=None, kind='cats', size=(110, 85)):
    source, public = Path(source), Path(public)
    if not source.is_dir():
        raise FileNotFoundError(source)
    files = sorted(p for p in source.iterdir() if p.is_file() and p.suffix.lower() == '.png')
    outputs = [p.name.lower().replace(' ', '_') for p in files]
    if len(set(outputs)) != len(outputs):
        raise ValueError('Image names collide after normalization')
    destinations = [public] + ([Path(drawables)] if drawables is not None else [])
    originals = {path.resolve() for path in files}
    if any((directory / name).resolve() in originals for directory in destinations for name in outputs):
        raise ValueError('A destination would overwrite an original image; select a separate source folder')
    for path, name in zip(files, outputs):
        with Image.open(path) as image:
            if kind == 'cats':
                left, top = (image.width - size[0]) // 2, (image.height - size[1]) // 2
                image = image.crop((left, top, left + size[0], top + size[1]))
            for directory in destinations:
                directory.mkdir(parents=True, exist_ok=True)
                image.save(directory / name)
        print(name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--kind', choices=['cats', 'enemies'], default='cats')
    parser.add_argument('--drawables', type=Path)
    args = parser.parse_args()
    ws = Workspace.load()
    process_images(args.source or ws.image_inbox, ws.root / 'images' / args.kind,
                   args.drawables or ws.app_drawables, kind=args.kind)


if __name__ == '__main__':
    main()
