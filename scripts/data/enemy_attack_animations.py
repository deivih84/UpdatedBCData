"""Cache verified enemy attack durations by ID from retained incremental packs."""
from __future__ import annotations

import csv
import hashlib
import json

from cat_animation_sources import decrypt_named_resources, discover_sources
from update_cat_backswings import animation_frames
from workspace_paths import latest_version_dir


def sync_enemy_attack_animations(paths):
    source_dir = latest_version_dir(paths.bcdata, 'jp')
    version = tuple(map(int, source_dir.name[:-2].split('.')))
    with (source_dir / 'DataLocal/t_unit.csv').open(encoding='utf-8-sig', newline='') as handle:
        rows = list(csv.reader(handle))[2:]
    # Positive CSV intervals already determine frequency. Zero intervals need
    # attack-animation duration; caches remain ID keyed when names change.
    wanted = {f'{i:03d}_e02.maanim': str(i) for i, row in enumerate(rows)
              if len(row) > 12 and int(row[4]) == 0}
    target = paths.data / 'enemy_attack_animations.json'
    cache = json.loads(target.read_text(encoding='utf-8')) if target.is_file() else {'enemies': {}}
    records = cache['enemies']
    for source in discover_sources(paths.bcdata, 'jp'):
        if source.version > version:
            continue
        resources = decrypt_named_resources(source, lambda name: name if name in wanted else None)
        for name, content in resources.items():
            duration = animation_frames(content)
            enemy_id = wanted[name]
            if duration <= int(rows[int(enemy_id)][12]):
                print(f'WARNING: enemy {enemy_id}: static or incomplete attack animation; retaining fallback')
                continue
            records[enemy_id] = {
                'frames': duration,
                'animation': name,
                'sha256': hashlib.sha256(content).hexdigest(),
                'sourceVersion': source.version_text,
                'sourceRegion': source.region,
            }
    payload = json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True) + '\n'
    if not target.is_file() or target.read_text(encoding='utf-8') != payload:
        temporary = target.with_suffix('.json.tmp')
        temporary.write_text(payload, encoding='utf-8')
        temporary.replace(target)
    print(f'Verified enemy attack durations: {len(records)}')
    return records
