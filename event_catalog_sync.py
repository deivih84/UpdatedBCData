"""Plan event catalogue, posters and calendar updates as one publication."""
import copy
import hashlib
import re
from pathlib import Path

import requests

from event_sources import event_png_bytes


def key(name):
    return re.sub(r'\s+', ' ', name).strip().casefold()


def plan_events(catalog, state, rows, names, metadata, fetch_image, repo, public_base, *, drawables=None, image_overrides=None):
    catalog, state = copy.deepcopy((catalog, state))
    image_overrides = image_overrides or {}
    entries = catalog['events']
    by_name, by_id = {}, {}
    for event in entries:
        for name in [event['nombre']] + event.get('aliases', []):
            if key(name) in by_name and by_name[key(name)] is not event:
                raise ValueError('Ambiguous event alias: ' + name)
            by_name[key(name)] = event
        ids = event.get('event_ids', []) + ([event['event_id']] if 'event_id' in event else [])
        for event_id in ids:
            if int(event_id) in by_id and by_id[int(event_id)] is not event:
                raise ValueError('Event ID belongs to multiple entries')
            by_id[int(event_id)] = event
    state.setdefault('schemaVersion', 1)
    records = state.setdefault('events', {})
    report = {'changes': [], 'images': [], 'pending': [], 'warnings': []}
    outputs, planned, downloaded, rejected, blocked_names = {}, {}, {}, set(), set()
    ids = sorted({event_id for row in rows for event_id in row['pack_ids']})
    for event_id in ids:
        hit = names.get(str(event_id))
        existing = by_id.get(event_id)
        if hit and not hit.get('calendar', True) and existing is None:
            continue
        named = by_name.get(key(hit['name'])) if hit else None
        if named is None and hit:
            root_name = re.sub(r'\s*\([^)]*\)\s*$', '', hit['name']).strip()
            named = by_name.get(key(root_name))
        if existing and named and named is not existing:
            report['pending'].append({'event_id': event_id, 'reason': 'identity_conflict',
                                      'names': [existing['nombre'], named['nombre']]})
            rejected.add(event_id)
            blocked_names.update((existing['nombre'], named['nombre']))
            continue
        event = existing or named
        if event is None and not hit:
            report['pending'].append({'event_id': event_id, 'reason': 'unknown_identity'})
            continue
        name = event['nombre'] if event else hit['name']
        planned.setdefault(name, {'event': event, 'ids': []})['ids'].append(event_id)
    # Also repair registered inactive events whose artwork was requested.
    for name in sorted(set(metadata) | set(image_overrides)):
        event = by_name.get(key(name))
        if event and event['nombre'] not in blocked_names:
            planned.setdefault(event['nombre'], {'event': event, 'ids': []})
    for name, group in planned.items():
        if name in blocked_names:
            continue
        event, group_ids = group['event'], group['ids']
        before = copy.deepcopy(event)
        meta = metadata.get(name, {})
        report['warnings'].extend(name + ': ' + w for w in meta.get('warnings', []))
        selected_file = image_overrides.get(name)
        if event is None:
            if not selected_file and not meta.get('image_url'):
                report['pending'].append({'name': name, 'event_ids': group_ids, 'reason': 'image_not_found'})
                continue
            event = {'nombre': name, 'aliases': [name], 'imagen_url': '', 'descripcion': ''}
        record = records.get(name, {})
        if selected_file or meta.get('image_url'):
            try:
                if selected_file:
                    if Path(selected_file).name != selected_file or not selected_file.endswith('.png'):
                        raise ValueError('Selected poster must be a PNG filename in images/events')
                    filename = selected_file
                    data = (Path(repo) / 'images/events' / filename).read_bytes()
                    event_png_bytes(data)  # Validate without modifying the selected bytes.
                    url = public_base.rstrip('/') + '/' + filename
                else:
                    url = meta['image_url']
                    if url not in downloaded:
                        downloaded[url] = event_png_bytes(fetch_image(url))
                    data = downloaded[url]
                    digest = hashlib.sha256(data).hexdigest()
                    slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
                    filename = f'event_{slug}_{digest[:16]}.png'
                digest = hashlib.sha256(data).hexdigest()
                target = Path(repo) / 'images/events' / filename
                outputs[target] = data
                if drawables is not None and Path(drawables).is_dir():
                    outputs[Path(drawables) / filename] = data
                new_url = public_base.rstrip('/') + '/' + filename
                if new_url != event['imagen_url'] or not target.is_file():
                    report['images'].append({'name': name, 'file': filename})
                event['imagen_url'] = new_url
                record['image'] = {'sourceUrl': url, 'sourcePage': None if selected_file else meta.get('image_source', meta.get('url')),
                                   **({'selection': 'catalog_override'} if selected_file else {}),
                                   'sha256': digest, 'file': filename}
            except (requests.RequestException, ValueError, OSError) as error:
                report['pending'].append({'name': name, 'reason': 'image_unavailable', 'detail': type(error).__name__})
                if before is None:
                    continue
                meta = {}  # Preserve metadata too when this repair failed.
        else:
            report['pending'].append({'name': name, 'reason': 'image_not_found'})
        if before is None:
            entries.append(event)
            by_name[key(name)] = event
        all_ids = set(event.get('event_ids', [])) | set(group_ids)
        if 'event_id' in event:
            all_ids.discard(event['event_id'])
        if all_ids and (all_ids != set(event.get('event_ids', []))):
            event['event_ids'] = sorted(all_ids)
        if meta.get('url') and not event.get('url'):
            event['url'] = meta['url']
        if meta.get('description') and event.get('descripcion', '') in ('', record.get('description')):
            event['descripcion'] = meta['description']
            record['description'] = meta['description']
        if record:
            records[name] = record
        if event != before:
            report['changes'].append({'name': name, 'action': 'created' if before is None else 'updated', 'event_ids': group_ids})
        for event_id in group_ids:
            by_id[event_id] = event
    schedule, seen = [], set()
    for row in rows:
        for event_id in row['pack_ids']:
            event = by_id.get(event_id)
            if event is None or event_id in rejected or event['nombre'] in blocked_names:
                continue
            name = event['nombre']
            slug = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')
            identity = (name, row['start_date'], row['end_date'])
            if identity in seen:
                continue
            seen.add(identity)
            schedule.append({'id': f'{slug}_{row["start_date"]}', 'nombre': name,
                             'caracteristicas': [event['descripcion']] if event.get('descripcion') else [],
                             'fecha_inicio': row['start_date'], 'fecha_fin': row['end_date']})
    from fetch_bc_events import dedupe_contained_event_ranges
    schedule = sorted(dedupe_contained_event_ranges(schedule), key=lambda ev: (ev['fecha_inicio'], ev['nombre']))
    ids_seen = {}
    for item in schedule:
        ids_seen.setdefault(item['id'], []).append(item)
    for items in ids_seen.values():
        if len(items) > 1:
            for item in items:
                identity = item['nombre'] + '|' + item['fecha_fin']
                item['id'] += '_' + hashlib.sha256(identity.encode()).hexdigest()[:10]
    return catalog, state, schedule, outputs, report
