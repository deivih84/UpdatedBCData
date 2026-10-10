"""Merge the reviewed PC catalog into published cats data without regenerating mobile stats."""
import argparse
import json
from datetime import datetime
from pathlib import Path

from scripts.data.pc_cats import load_pc_source, merge_pc_source
from update_cat_backswings import render_data


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cats-data', type=Path, default=root / 'cats_data.json')
    parser.add_argument('--source', type=Path, default=root / 'data/inputs/cats_pc.json')
    parser.add_argument('--app-data', type=Path, help='Explicit app cats_data.json to export after applying')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    original = args.cats_data.read_text(encoding='utf-8-sig')
    data = json.loads(original)
    merged = merge_pc_source(data, load_pc_source(args.source))
    changed = merged != data
    print(f"PC combat units: {merged['metadata']['pc_units']}; catalog-only entries: {merged['metadata']['pc_catalog_units']}")
    print(f'Changed files: {int(changed)}')
    if args.dry_run:
        return
    if changed:
        merged['metadata']['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        temporary = args.cats_data.with_suffix('.json.tmp')
        temporary.write_text(render_data(merged) + '\n', encoding='utf-8')
        temporary.replace(args.cats_data)
        version_path = args.cats_data.parent / 'data_version.json'
        if version_path.exists():
            version = json.loads(version_path.read_text(encoding='utf-8'))
            version['lastUpdate'] = merged['metadata']['last_update']
            # Animation synchronization compares canonical LF bytes on every platform.
            version_path.write_bytes((json.dumps(version, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8'))
    if args.app_data:
        args.app_data.write_bytes(args.cats_data.read_bytes())


if __name__ == '__main__':
    main()
