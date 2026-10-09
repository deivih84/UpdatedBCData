"""Read-only installation/workspace diagnosis; no downloads or generated files."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path
from workspace_paths import Workspace
from update_all import STEPS


def inspect(ws, game_data=False):
    report = {'root': str(ws.root), 'bcdata': str(ws.bcdata), 'workData': str(ws.data),
              'catstats': str(ws.catstats) if ws.catstats else None, 'errors': [], 'notes': []}
    for module in ['requests', 'bs4', 'PIL', 'tbcml', 'PyQt5', 'pandas', 'lxml', 'cloudscraper']:
        if importlib.util.find_spec(module) is None:
            report['errors'].append('Missing dependency: ' + module + '; install requirements-lock.txt')
    if sys.version_info[:2] != (3, 12):
        report['notes'].append('Reference runtime: Python 3.12; other versions are not covered by the portable dependency lock')
    for file in list(STEPS.values()) + ['data/inputs/names.txt', 'data/inputs/combos.csv',
                                      'data/inputs/skill_acquisition.csv', 'data/inputs/skill_level.csv']:
        if not (ws.root / file).is_file():
            report['errors'].append('Missing repository file: ' + file)
    for name in ['gacha_sync_config.json', 'gacha_sync_config_jp.json', 'event_sync_config.json']:
        value = json.loads((ws.root / name).read_text(encoding='utf-8')).get('appDrawables')
        if value and (Path(value).is_absolute() or ':/' in value or ':\\' in value):
            report['errors'].append(name + ' contains a machine-specific shared drawable path')
    if ws.catstats and not ws.app_data.is_dir():
        report['errors'].append('Configured CatStats assets directory is absent: ' + str(ws.app_data))
    if game_data:
        for region in ['en', 'jp']:
            try:
                report[region + 'Version'] = ws.require_bcdata(region).name
            except FileNotFoundError as exc:
                report['errors'].append(str(exc))
        if not (ws.bcdata / 'latest.txt').is_file():
            report['errors'].append('Animations require BCData/latest.txt and retained incremental source packages')
        sources = [p for p in ws.bcdata.iterdir() if p.suffix.lower() in ('.apk', '.xapk', '.apks', '.apkm')] if ws.bcdata.is_dir() else []
        if not sources:
            report['errors'].append('No retained APK/XAPK/APKS/APKM animation sources in configured BCData')
    else:
        report['notes'].append('Game sources not required for online catalogs; use --game-data to inspect the full pipeline prerequisites')
    if ws.catstats is None:
        report['notes'].append('App export disabled; configure catstats and use --export-app to enable it')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bcdata', type=Path)
    parser.add_argument('--catstats', type=Path)
    parser.add_argument('--game-data', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        report = inspect(Workspace.load(overrides={'bcdata': args.bcdata, 'catstats': args.catstats}), args.game_data)
    except (ValueError, OSError) as exc:
        report = {'errors': [str(exc)], 'notes': []}
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        for key in ['root', 'bcdata', 'workData', 'catstats', 'enVersion', 'jpVersion']:
            if key in report:
                print(f'{key}: {report[key]}')
        for note in report['notes']:
            print('NOTE: ' + note)
        for error in report['errors']:
            print('ERROR: ' + error)
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    sys.exit(main())
