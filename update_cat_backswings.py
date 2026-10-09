"""Derive per-form backswing frames from the merged public attack animations."""

import argparse
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path


def animation_frames(content):
    """Return animation duration, including frame zero, from MAANIM keyframes."""
    lines = content.decode('utf-8-sig').splitlines()
    try:
        if not lines[0].startswith('[modelanim:'):
            raise ValueError('Missing MAANIM header')
        int(lines[1])  # format version
        tracks = int(lines[2])
        if tracks <= 0:
            raise ValueError('Attack animation has no tracks')
        position = 3
        last_frame = -1
        for _ in range(tracks):
            header = lines[position].split(',')
            if len(header) < 5:
                raise ValueError('Invalid MAANIM track header')
            loops = int(header[2])
            position += 1
            count = int(lines[position])
            position += 1
            if count < 0:
                raise ValueError('Negative MAANIM keyframe count')
            frames = []
            for _ in range(count):
                frame = lines[position].split(',')
                if len(frame) < 4:
                    raise ValueError('Invalid MAANIM keyframe')
                frames.append(int(frame[0]))
                position += 1
            if frames:
                # BCU Part.getMax()/MaAnim.len: finite repeats retain their
                # original first-frame offset; infinite tracks use one cycle.
                end = frames[0] + (frames[-1] - frames[0]) * loops if loops > 1 else frames[-1]
                last_frame = max(last_frame, end)
        if last_frame < 0:
            raise ValueError('Attack animation has no keyframes')
        return last_frame + 1
    except (IndexError, UnicodeError) as exc:
        raise ValueError('Truncated or invalid MAANIM animation') from exc


def backswing_frames(content, stats):
    # CSV offsets do not include the ID prepended by the Android loader.
    foreswing = next((int(stats[i]) for i in (62, 61, 13)
                      if len(stats) > i and int(stats[i]) > 0), 0)
    duration = animation_frames(content)
    # Iron Wall and the unused Cheetah record have static attack placeholders.
    if duration == 1 and foreswing > 0:
        return None
    value = duration - foreswing
    if value < 0:
        raise ValueError('Attack animation ends before its final hit')
    return value


def populate_backswings(data, archives):
    """Add frames in stats order; unavailable forms remain null, never aliased."""
    missing = []
    for unit_id, unit in data['units'].items():
        stats = unit['stats']
        if len(stats) > 4:
            raise ValueError(f'{unit_id}: more than four forms')
        archive_id = str(int(unit_id))
        path = Path(archives) / f'{archive_id}.zip'
        values = [None] * len(stats)
        if path.exists():
            with zipfile.ZipFile(path) as archive:
                for index, form in enumerate('fcsu'[:len(stats)]):
                    name = f'{archive_id}/{form}/{archive_id}_{form}02.maanim'
                    if name in archive.namelist():
                        try:
                            values[index] = backswing_frames(archive.read(name), stats[index])
                            if values[index] is None:
                                missing.append(f'{unit_id}/{form}')
                        except ValueError as exc:
                            raise ValueError(f'{name}: {exc}') from exc
                    else:
                        missing.append(f'{unit_id}/{form}')
        else:
            missing.extend(f'{unit_id}/{form}' for form in 'fcsu'[:len(stats)])
        unit['backswing'] = values
    return missing


def validate_source(data, manifest):
    desired = data['metadata']['version']
    actual = manifest.get('latestSource', {}).get('gameVersion')
    if actual != desired:
        raise ValueError(f'Animation source {actual} does not match cats_data {desired}; sync animations first')


def render_data(data):
    text = json.dumps(data, indent=4, ensure_ascii=False)
    return re.sub(r'\[\s+([\d,\s\-.]+)\s+\]',
                  lambda match: '[' + ''.join(match.group(1).split()) + ']', text)


def prepare_backswings(data, archives):
    """During CSV generation, defer calculation until archives match the version."""
    manifest_path = Path(archives) / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8')) if manifest_path.exists() else {}
    if manifest.get('latestSource', {}).get('gameVersion') == data['metadata']['version']:
        return populate_backswings(data, archives)
    missing = []
    for unit_id, unit in data['units'].items():
        unit['backswing'] = [None] * len(unit['stats'])
        missing.extend(f'{unit_id}/{form}' for form in 'fcsu'[:len(unit['stats'])])
    return missing


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cats-data', type=Path, default=root / 'cats_data.json')
    parser.add_argument('--archives', type=Path, default=root / 'cats')
    parser.add_argument('--app-data', type=Path, help='Bundled cats_data.json to synchronize')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    original = args.cats_data.read_text(encoding='utf-8')
    data = json.loads(original)
    manifest = json.loads((args.archives / 'manifest.json').read_text(encoding='utf-8'))
    validate_source(data, manifest)
    previous = {key: unit.get('backswing') for key, unit in data['units'].items()}
    missing = populate_backswings(data, args.archives)
    changed = sum(previous[key] != unit['backswing'] for key, unit in data['units'].items())
    print(f'Units with changed backswing: {changed}; unavailable forms: {len(missing)}')
    for form in missing:
        print(f'WARNING: {form}: attack animation unavailable; backswing is null')
    if args.dry_run:
        return
    if changed:
        data['metadata']['last_update'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        original = render_data(data)
        temporary = args.cats_data.with_suffix('.json.tmp')
        temporary.write_text(original, encoding='utf-8')
        temporary.replace(args.cats_data)
        version_path = args.cats_data.parent / 'data_version.json'
        if version_path.exists():
            version = json.loads(version_path.read_text(encoding='utf-8'))
            version['lastUpdate'] = data['metadata']['last_update']
            version_path.write_text(json.dumps(version, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    if args.app_data:
        args.app_data.write_bytes(args.cats_data.read_bytes())


if __name__ == '__main__':
    main()
