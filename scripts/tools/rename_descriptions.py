"""Normalize Korean/Japanese description suffixes in an explicit folder."""
import argparse
from pathlib import Path


def rename_descriptions(folder):
    for path in sorted(Path(folder).glob('*.csv')):
        name = path.name.replace('_ko.csv', '_kr.csv').replace('_ja.csv', '_jp.csv')
        if name == path.name:
            continue
        target = path.with_name(name)
        if target.exists():
            raise FileExistsError(target)
        path.rename(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    rename_descriptions(parser.parse_args().folder)
