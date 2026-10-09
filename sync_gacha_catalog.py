#!/usr/bin/env python3
"""Synchronize EN/JP capsule identities, pools and artwork without interactive prompts."""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import re
import sys

import requests

import fetch_bc_schedule as schedule
from gacha_catalog_sync import plan_catalog, plan_images, publish, serialize
from gacha_sources import BannerSource, load_local_game, scheduled_events


ROOT = Path(__file__).resolve().parent


def read_json(path, default=None):
    if not path.exists() and default is not None:
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def run(args):
    repository = args.repo.resolve()
    region = getattr(args, 'region', 'en')
    suffix = '' if region == 'en' else '_jp'
    paths = {name: repository / (name + suffix + '.json') for name in
             ('gacha_sync_config', 'gacha_id_cache', 'gacha_sync_state', 'gacha_sync_report')}
    catalog_path = repository / f'all_gachas_{region}.json'
    private_report = repository / ('.gacha_sync_run' + suffix + '.json')
    config = read_json(paths["gacha_sync_config"])
    catalog = read_json(catalog_path, {"gachas": []})
    cache = read_json(paths["gacha_id_cache"], {})
    state = read_json(paths["gacha_sync_state"], {})
    if state.get('region', region) != region:
        raise ValueError('Catalogue state belongs to another region')
    state['region'] = region
    source = BannerSource(region=region)
    if args.tsv:
        tsv = args.tsv.read_text(encoding="utf-8-sig")
    else:
        from bc_schedule_sources import download_schedule
        direct = None if args.dry_run else lambda: schedule.fetch_gatya_tsv(schedule.get_auth_token(), region=region)
        tsv, provenance = download_schedule('gatya.tsv', direct, session=source.session, region=region)
        print('Schedule source: ' + provenance['url'], flush=True)
    events = scheduled_events(tsv, args.today)
    from workspace_paths import Workspace, drawable_path
    local = args.bcdata
    if local is None and not args.online:
        sibling = Workspace.load(repository).catalog_bcdata(require_latest=True)
        if sibling is not None and (sibling / "latest.txt").is_file():
            local = sibling
    pool_pending = []
    if local is not None:
        game = load_local_game(local, region=region)
    else:
        # The public BCData mirror can lag game releases. Godfat is the existing
        # online pool source; validate both event selection and PONOS rates.
        game = {"pools": {}, "options": {}, "source": "bc.godfat.org (validated against PONOS)", "version": None, "poolSources": {}, "poolVersions": {}}
        available = []
        normal_ids = {event['gacha_id'] for event in events if event.get('gacha_type') not in (2, 3)}
        for event in events:
            gid = event['gacha_id']
            # Godfat does not expose JP's old first-purchase offers (types 2/3).
            # Keep their saved catalogue entries; do not substitute another pool.
            if region == 'jp' and event.get('gacha_type') in (2, 3):
                pool_pending.append({'gacha_id': gid, 'reason': 'starter_pool_not_available_online'})
                if gid in normal_ids:
                    # A normal offer sharing this ID must fetch and validate it.
                    available.append(event)
                    continue
                saved = state.get('banners', {}).get(str(gid), {})
                if not saved.get('pool') or not saved.get('rates'):
                    continue
                # Preserve the last verified starter snapshot, validating its rates
                # against this schedule. The report explicitly marks it as unrefreshed.
                game['pools'][gid] = {**saved['pool'], **saved['rates']}
                game['options'][gid] = saved.get('option', {})
                game['poolSources'][gid] = saved.get('source', 'saved JP starter snapshot')
                game['poolVersions'][gid] = saved.get('gameVersion')
                available.append(event)
                continue
            available.append(event)
            if gid not in game["pools"]:
                print(f"Pool {event['event_id']}", flush=True)
                game["pools"][gid] = source.pool(event)
            game["options"][gid] = state.get("banners", {}).get(str(gid), {}).get("option", {})
        events = available
    metadata = {}
    ids = {event["gacha_id"] for event in events}
    # Repair missing artwork of registered inactive banners too.
    for id_text, name in cache.items():
        banner = next((b for b in catalog["gachas"] if b["nombre"] == name), None)
        if banner and image_missing(repository, banner):
            ids.add(int(id_text))
    if not args.skip_images:
        for gid in sorted(ids):
            print(f"Artwork/name #{gid}", flush=True)
            option = game.get("options", {}).get(gid, state.get("banners", {}).get(str(gid), {}).get("option", {}))
            fallback_id = config.get("seriesBannerIds", {}).get(str(option.get("seriesID", -1)))
            metadata[gid] = source.metadata(gid, option, fallback_image_id=fallback_id)
            meta = metadata[gid]
            if meta.get("name") in config.get("wikiNames", {}):
                meta["name"] = config["wikiNames"][meta["name"]]
    catalog, cache, state, report = plan_catalog(catalog, cache, state, events, game,
        config.get("seriesNames", {}), metadata, today=args.today, region=region)
    report['pending'].extend({p['gacha_id']: p for p in pool_pending}.values())
    report['sources']['schedule'] = 'saved gatya.tsv' if args.tsv else provenance['url']
    report['region'] = region
    # Registered historical IDs are sufficient to repair their artwork, without
    # presenting an expired pool as today's version of that banner.
    for gid in ids:
        if str(gid) not in state["banners"] and str(gid) in cache:
            state["banners"][str(gid)] = {"name": cache[str(gid)], "family": cache[str(gid)],
                                         "start_date": "2000-01-01", "option": game.get("options", {}).get(gid, {})}
    drawables = drawable_path(repository, args.app_drawables, config.get("appDrawables"))
    outputs = plan_images(catalog, state, metadata, source.image, repository,
                          config["publicImageBase"], report, drawables, today=args.today, region=region)
    report["missingImages"] = [b["nombre"] for b in catalog["gachas"]
                               if image_missing(repository, b, outputs)]
    outputs.update({catalog_path: serialize(catalog),
                    paths["gacha_id_cache"]: serialize(cache),
                    paths["gacha_sync_state"]: serialize(state)})
    changed = publish(outputs, dry_run=True)
    report["pendingWrites"] = [str(path.relative_to(repository)) if path.is_relative_to(repository)
                              else str(path) for path in changed]
    # Preserve the last applied change list in the public report on a no-op run.
    public_report = dict(report)
    public_report.pop("pendingWrites")
    if not report["changes"] and not report["images"]:
        last = read_json(paths["gacha_sync_report"], {})
        public_report["changes"] = last.get("changes", [])
        public_report["images"] = last.get("images", [])
    outputs[paths["gacha_sync_report"]] = serialize(public_report)
    if not args.dry_run:
        outputs[private_report] = serialize(report)
    publish(outputs, dry_run=args.dry_run)
    print(f"{'DRY RUN' if args.dry_run else 'APPLIED'}: "
          f"{len(report['changes'])} catalogue changes, {len(report['images'])} images, "
          f"{len(report['pending'])} pending, {len(changed)} pending file changes")
    for pending in report["pending"]:
        print(f"  Pending #{pending.get('gacha_id', '?')}: {pending['reason']}")
    if report["missingImages"]:
        print("  Missing local images: " + ", ".join(report["missingImages"]))
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and not args.dry_run:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(f"### {region.upper()} banner sync\n\n{len(report['changes'])} catalogue changes; "
                         f"{len(report['images'])} images; {len(report['pending'])} pending.\n\n")
            for pending in report["pending"]:
                stream.write(f"- #{pending.get('gacha_id', '?')}: {pending['reason']}\n")
    return report


def image_missing(repository, banner, outputs=None):
    url = banner.get("imagen_url", "")
    if not url:
        return True
    if "/images/gacha/" not in url:
        return False
    path = repository / "images" / "gacha" / url.rsplit("/", 1)[1]
    return not path.is_file() and path not in (outputs or {})


def main(argv=None):
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--region", choices=("en", "jp"), default="en")
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--bcdata", type=Path, help="Local BCData checkout (latest selected region); detected automatically on this PC")
    parser.add_argument("--online", action="store_true", help="Use validated Godfat pools instead of sibling BCData")
    parser.add_argument("--tsv", type=Path, help="Saved PONOS TSV for reproducible offline runs")
    parser.add_argument("--today", type=date.fromisoformat, default=date.today())
    parser.add_argument("--app-drawables", type=Path)
    parser.add_argument("--skip-images", action="store_true", help="Update known pools without artwork/name lookups")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing any files")
    args = parser.parse_args(argv)
    try:
        run(args)
    except (requests.RequestException, OSError, ValueError, KeyError, TypeError) as error:
        message = re.sub(r"jwt=[^&\s]+", "jwt=[redacted]", str(error))
        print(f"ERROR: {message}")
        if not args.dry_run:
            publish({args.repo.resolve() / (".gacha_sync_run" + ("_jp" if args.region == "jp" else "") + ".json"): serialize({
                "errors": [message], "changes": [], "images": [], "pending": []})})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
