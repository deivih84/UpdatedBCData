"""Build the curated PC catalog and native animation ZIPs from retained wiki sources."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import requests

from cat_animation_sync import build_deterministic_zip, validate_archive
from update_cat_backswings import animation_frames
from PIL import Image

ROOT = Path(__file__).resolve().parent
USER_AGENT = 'BattleStatsDataSync/1.0 (https://github.com/deivih84/UpdatedBCData)'
ANIMATION_TYPES = {'walk': '00', 'idle': '01', 'attack': '02', 'knockback': '03'}


def text_resource(rows, header=None):
    """The wiki stores the original CSV rows as arrays; retain every column."""
    output = io.StringIO(newline='')
    writer = csv.writer(output, lineterminator='\n')
    for index, row in enumerate(rows):
        writer.writerow([header] if index == 0 and header else row)
    return output.getvalue().encode('utf-8')


def convert_form(unit_id, form, source, spritesheet):
    with Image.open(io.BytesIO(spritesheet)) as image:
        image.verify()
    prefix = f'{unit_id}_{form}'
    entries = {prefix + '.png': spritesheet,
               prefix + '.imgcut': text_resource(source['imgcut']),
               prefix + '.mamodel': text_resource(source['mamodel'])}
    entries[prefix + '.imgcut'] = entries[prefix + '.imgcut'].replace(
        str(source['imgcut'][2][0]).encode(), (prefix + '.png').encode(), 1)
    seen = set()
    for animation in source['maanim']:
        name = animation['name'].lower()
        if name not in ANIMATION_TYPES or name in seen:
            raise ValueError(f'{prefix}: unexpected/duplicate animation {name}')
        seen.add(name)
        content = text_resource(animation['data'], '[modelanim:animation]')
        if int(animation['data'][2][0]) > 0:
            animation_frames(content)  # validate non-static tracks
        entries[prefix + ANIMATION_TYPES[name] + '.maanim'] = content
    if seen != set(ANIMATION_TYPES):
        raise ValueError(f'{prefix}: missing animation states: {set(ANIMATION_TYPES) - seen}')
    result = validate_archive(unit_id, entries)
    if result.errors:
        raise ValueError('; '.join(result.errors))
    return entries


def retained_file(path, url, online):
    if not path.exists():
        if not online:
            raise ValueError(f'Missing retained source {path}; use --online to fetch it')
        response = requests.get(url, headers={'User-Agent': USER_AGENT}, timeout=60)
        response.raise_for_status()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
    return path.read_bytes()


def build(input_path, cache, online):
    catalog = json.loads(input_path.read_text(encoding='utf-8'))['pc_catalog']
    outputs, records, sources, warnings = {}, {}, [], []
    for key, unit in catalog.items():
        unit_id = int(key)
        if unit_id != 100000 + int(unit['info']['source_id']):
            raise ValueError(f'Invalid PC identity: {key}')
        entries = {}
        for form in unit['forms']:
            code = form['code']
            ref = form.pop('animation_source')
            json_url = requests.Request('GET', 'https://battlecats.miraheze.org/w/index.php',
                params={'title': ref['page'], 'action': 'raw'}).prepare().url
            filename = ref['spritesheet']
            digest = hashlib.md5(filename.encode()).hexdigest()
            png_url = f'https://static.wikitide.net/battlecatswiki/{digest[0]}/{digest[:2]}/{filename}'
            stem = cache / key / code
            raw = retained_file(stem / f"{ref['revision']}.json", json_url, online)
            png = retained_file(stem / filename, png_url, online)
            converted = convert_form(unit_id, code, json.loads(raw), png)
            entries.update(converted)
            for animation in json.loads(raw)['maanim']:
                if int(animation['data'][2][0]) == 0:
                    warnings.append(f"{key}/{code}: {animation['name']} has no tracks in the source")
            foreswing = next((m['value'] for m in form['measurements'] if m['field'] == 'foreswing'), None)
            frames = animation_frames(converted[f'{unit_id}_{code}02.maanim'])
            multi_hit = any(a['text'].lower().startswith('multi-hit') for a in form['abilities'])
            backswing = frames - int(foreswing) if foreswing is not None and not multi_hit else None
            if foreswing is None or multi_hit:
                warnings.append(f'{key}/{code}: final hit timing unavailable/ambiguous; backswing unavailable')
            if backswing is not None and backswing < 0:
                warnings.append(f'{key}/{code}: attack ends before published foreswing; backswing unavailable')
                backswing = None
            form['backswing'] = backswing
            sources.append({'unitId': key, 'form': code, 'jsonUrl': json_url,
                'jsonSha256': hashlib.sha256(raw).hexdigest(), 'spritesheetUrl': png_url,
                'spritesheetSha256': hashlib.sha256(png).hexdigest()})
            # Native archives exist only for explicitly imported forms.
            form['animation'] = True
        content = build_deterministic_zip(unit_id, entries)
        outputs[f'cats_pc/{key}.zip'] = content
        records[key] = {'sha256': hashlib.sha256(content).hexdigest(), 'size': len(content)}
    digest_input = '\n'.join(f"{key}:{value['sha256']}:{value['size']}" for key,value in sorted(records.items()))
    manifest = {'schemaVersion': 1, 'revision': 'sha256:' + hashlib.sha256(digest_input.encode()).hexdigest(),
                'archives': records, 'sources': sources, 'warnings': warnings}
    outputs['cats_pc/manifest.json'] = (json.dumps(manifest, indent=2) + '\n').encode()
    outputs['pc_cats.json'] = (json.dumps({'pc_catalog': catalog}, ensure_ascii=False, indent=2) + '\n').encode()
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'data/inputs/pc_cats.json')
    parser.add_argument('--cache', type=Path, default=ROOT / 'workspace/pc-sources')
    parser.add_argument('--output', type=Path, default=ROOT)
    parser.add_argument('--app-data', type=Path, help='Optional app cats_data.json; update its PC catalog only')
    parser.add_argument('--app-details', type=Path, help='Optional bundled pc_cat_details.json')
    parser.add_argument('--online', action='store_true', help='Download missing wiki sources and retain them')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    outputs = build(args.input, args.cache, args.online)
    for warning in json.loads(outputs['cats_pc/manifest.json'])['warnings']:
        print('WARNING: ' + warning)
    # Publish the catalog in the existing client interface without changing mobile data.
    public_path = args.output / 'cats_data.json'
    if public_path.exists():
        from update_cat_backswings import render_data
        data = json.loads(public_path.read_text(encoding='utf-8'))
        data['pc_catalog'] = json.loads(outputs['pc_cats.json'])['pc_catalog']
        outputs['cats_data.json'] = render_data(data).encode('utf-8')
    catalog = json.loads(outputs['pc_cats.json'])['pc_catalog']
    if args.app_data:
        from update_cat_backswings import render_data
        app_data = json.loads(args.app_data.read_text(encoding='utf-8'))
        app_data['pc_catalog'] = catalog
        outputs[str(args.app_data.resolve())] = render_data(app_data).encode('utf-8')
    if args.app_details:
        outputs[str(args.app_details.resolve())] = (json.dumps(
            {key: unit['forms'] for key, unit in catalog.items()}, indent=2,
            ensure_ascii=False) + '\n').encode('utf-8')
    changed = [name for name, content in outputs.items()
               if not (args.output / name).exists() or (args.output / name).read_bytes() != content]
    print(f'PC changed paths: {len(changed)}')
    for name in changed:
        print(name)
    if not args.dry_run:
        for name in changed:
            path = args.output / name
            path.parent.mkdir(parents=True, exist_ok=True)
            temp = path.with_suffix(path.suffix + '.tmp')
            temp.write_bytes(outputs[name])
            temp.replace(path)


if __name__ == '__main__':
    main()
