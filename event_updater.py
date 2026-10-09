"""Orchestrate the existing EN event flow with catalogue and poster maintenance."""
import argparse
import copy
from datetime import date, datetime, timezone
import json
import os
import re
from pathlib import Path

import requests

from bc_schedule_sources import download_schedule
from event_catalog_sync import plan_events, key
from event_sources import EventWikiSource, load_event_index, event_dimensions
from gacha_catalog_sync import publish, serialize
from PIL import Image


ROOT = Path(__file__).resolve().parent


def read_json(path, default=None):
    if not path.is_file() and default is not None:
        return default
    return json.loads(path.read_text(encoding='utf-8'))


def image_needs_repair(repo, event):
    url = event.get('imagen_url', '')
    if not url or 'event_empty.' in url:
        return True
    if '/images/events/' not in url:
        return False
    filename = url.split('/images/events/', 1)[1]
    path = repo / 'images/events' / filename
    try:
        with Image.open(path) as image:
            event_dimensions(*image.size)
        return False
    except (OSError, ValueError):
        return True


def campaign_family(name):
    for pattern, family in [(r'\d+M Download Celebration!', 'downloads'),
                            (r'\d+(?:st|nd|rd|th) Anniversary', 'anniversary')]:
        if re.fullmatch(pattern, name):
            return family
    return None


def merge_calendar(current, previous, catalog, pending, today):
    import fetch_bc_events as events
    seen = {(item['nombre'], item['fecha_inicio']) for item in current}
    mapped = {e['nombre'] for e in catalog['events'] if e.get('event_ids') or 'event_id' in e}
    known = {e['nombre'] for e in catalog['events']}
    conflicted = {name for item in pending if item['reason'] == 'identity_conflict'
                  for name in item.get('names', [])}
    kept = []
    for item in previous:
        name = item['nombre']
        if name not in known or (name in mapped and name not in conflicted) or (name, item['fecha_inicio']) in seen:
            continue
        family = campaign_family(name)
        superseded = family and any(campaign_family(new['nombre']) == family
            and new['nombre'] != name and new['fecha_inicio'] <= item['fecha_fin']
            and item['fecha_inicio'] <= new['fecha_fin'] for new in current)
        if not superseded:
            kept.append(item)
    kept = events.filter_relevant_event_entries(kept, today=today, max_start_age_days=30)
    result = sorted(events.dedupe_contained_event_ranges(current + kept),
                    key=lambda item: (item['fecha_inicio'], item['nombre']))
    # Preserve familiar IDs unless a Unicode/name collision requires a suffix.
    counts = {}
    for item in result:
        counts[item['id']] = counts.get(item['id'], 0) + 1
    import hashlib
    for item in result:
        if counts[item['id']] > 1:
            identity = item['nombre'] + '|' + item['fecha_fin']
            item['id'] += '_' + hashlib.sha256(identity.encode()).hexdigest()[:10]
    return result


def run(args):
    import fetch_bc_events as events
    repo = args.repo.resolve()
    config = read_json(repo / 'event_sync_config.json')
    catalog = read_json(repo / 'all_events.json')
    image_overrides = config.get('imageOverrides', {})
    state = read_json(repo / 'event_sync_state.json', {})
    previous_index = read_json(repo / 'event_name_index.json', {})
    source = EventWikiSource()
    if args.tsv:
        content = args.tsv.read_text(encoding='utf-8-sig')
        provenance = {'url': 'saved sale.tsv'}
    else:
        direct = None if args.dry_run else lambda: events.fetch_sale_tsv(events.get_auth_token())
        content, provenance = download_schedule('sale.tsv', direct, session=source.session)
    rows = events.parse_sale_tsv(content, today=args.today)
    if not rows:
        raise ValueError('No current/upcoming event rows; previous data retained')
    from workspace_paths import Workspace, drawable_path
    workspace = Workspace.load(repo)
    resolved = workspace.catalog_bcdata(online=args.online)
    bcdata = args.bcdata if args.bcdata is not None else (resolved or workspace.bcdata)
    if args.bcdata is not None and not args.bcdata.is_dir():
        raise FileNotFoundError(f'Explicit BCData does not exist: {args.bcdata}')
    index, warnings = load_event_index(previous_index, source.session, bcdata=bcdata, online=args.online)
    aliases, ids = {}, {}
    for event in catalog['events']:
        for name in [event['nombre']] + event.get('aliases', []):
            aliases[key(name)] = event
        for event_id in event.get('event_ids', []) + ([event['event_id']] if 'event_id' in event else []):
            ids[int(event_id)] = event
    wanted = {}
    for event_id in sorted({i for row in rows for i in row['pack_ids']}):
        hit = index['names'].get(str(event_id))
        known = ids.get(event_id)
        if hit and not hit.get('calendar', True) and known is None:
            continue
        if hit and known is None:
            known = events._metadata_for_name(hit['name'], aliases)
        if known:
            wanted[known['nombre']] = known
        elif hit:
            wanted[hit['name']] = {'nombre': hit['name']}
    for event in catalog['events']:
        if image_needs_repair(repo, event) or event['nombre'] in image_overrides:
            wanted[event['nombre']] = event
    metadata = {}
    if not args.skip_images:
        for name, event in sorted(wanted.items()):
            if name in image_overrides:
                continue
            print('Event poster: ' + name, flush=True)
            metadata[name] = source.metadata(name, event, config)
    drawables = drawable_path(repo, args.app_drawables, config.get('appDrawables'))
    catalog, state, schedule, outputs, report = plan_events(catalog, state, rows, index['names'],
        metadata, source.image, repo, config['publicImageBase'], drawables=drawables, image_overrides=image_overrides)
    report['sources'] = {'schedule': provenance, 'names': {'version': index['version'], 'source': index['source']}}
    report['warnings'].extend(warnings)
    existing = read_json(repo / 'gachas_eventos_actualizados_en1.json')
    schedule = merge_calendar(schedule, existing.get('eventos', []), catalog, report['pending'], args.today)
    output = dict(existing)
    output['eventos'] = schedule
    if schedule != existing.get('eventos', []):
        output['ultima_actualizacion'] = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    report['calendarEvents'] = len(schedule)
    report['missingImages'] = [e['nombre'] for e in catalog['events'] if image_needs_repair(repo, e)
                              and not any(path.name == e.get('imagen_url', '').rsplit('/', 1)[-1] for path in outputs)]
    outputs.update({repo / 'all_events.json': serialize(catalog),
                    repo / 'event_sync_state.json': serialize(state),
                    repo / 'event_name_index.json': serialize(index),
                    repo / 'gachas_eventos_actualizados_en1.json': serialize(output)})
    changed = publish(outputs, dry_run=True)
    report['pendingWrites'] = [str(path.relative_to(repo)) if path.is_relative_to(repo) else str(path) for path in changed]
    public = copy.deepcopy({k: v for k, v in report.items() if k != 'pendingWrites'})
    if not report['changes'] and not report['images']:
        last = read_json(repo / 'event_sync_report.json', {})
        public['changes'] = last.get('changes', [])
        public['images'] = last.get('images', [])
    public['sources']['schedule'] = {k: v for k, v in provenance.items() if k != 'fallbackReason'}
    outputs[repo / 'event_sync_report.json'] = serialize(public)
    changed = publish(outputs, dry_run=True)
    report['pendingWrites'] = [str(path.relative_to(repo)) if path.is_relative_to(repo) else str(path) for path in changed]
    if not args.dry_run:
        outputs[repo / '.event_sync_run.json'] = serialize(report)
    publish(outputs, dry_run=args.dry_run)
    print(f"{'DRY RUN' if args.dry_run else 'APPLIED'}: {len(report['changes'])} event changes, "
          f"{len(report['images'])} posters, {len(schedule)} calendar events, "
          f"{len(report['pending'])} pending, {len(changed)} pending file changes")
    for item in report['pending']:
        print('  Pending ' + str(item.get('name', item.get('event_id'))) + ': ' + item['reason'])
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary and not args.dry_run:
        with open(summary, 'a', encoding='utf-8') as stream:
            stream.write(f"### EN event sync\n\n{len(report['changes'])} catalogue changes; "
                         f"{len(report['images'])} posters; {len(report['pending'])} pending.\n\n")
            for item in report['pending']:
                stream.write(f"- {item.get('name', item.get('event_id'))}: {item['reason']}\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, default=ROOT)
    parser.add_argument('--bcdata', type=Path)
    parser.add_argument('--online', action='store_true')
    parser.add_argument('--tsv', type=Path)
    parser.add_argument('--today', type=date.fromisoformat, default=date.today())
    parser.add_argument('--app-drawables', type=Path)
    parser.add_argument('--skip-images', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        run(args)
    except (requests.RequestException, ValueError, KeyError, TypeError, OSError) as error:
        # Do not leak token-bearing URLs from authentication errors.
        message = str(error) if not isinstance(error, requests.RequestException) else type(error).__name__
        print('ERROR: ' + message)
        if not args.dry_run:
            publish({args.repo.resolve() / '.event_sync_run.json': serialize({'errors': [message]})})
        return 1
    return 0
