#!/usr/bin/env python3
"""Synchronize EN capsule identities, pools and artwork without interactive prompts."""
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
    config = read_json(repository / "gacha_sync_config.json")
    catalog = read_json(repository / "all_gachas_en.json")
    cache = read_json(repository / "gacha_id_cache.json", {})
    state = read_json(repository / "gacha_sync_state.json", {})
    source = BannerSource()
    if args.tsv:
        tsv = args.tsv.read_text(encoding="utf-8-sig")
    else:
        # A dry-run must not create or refresh credentials on disk.
        if args.dry_run:
            response = source.session.get("https://bc-seek.godfat.org/seek/en/gatya.tsv", timeout=30)
            response.raise_for_status()
            tsv = response.content.decode("utf-8", errors="replace")
        else:
            tsv = schedule.fetch_gatya_tsv(schedule.get_auth_token())
    events = scheduled_events(tsv, args.today)
    local = args.bcdata
    if local is None and not args.online:
        sibling = repository.parent / "BCData"
        if (sibling / "latest.txt").is_file():
            local = sibling
    if local is not None:
        game = load_local_game(local)
    else:
        # The public BCData mirror can lag game releases. Godfat is the existing
        # online pool source; validate both event selection and PONOS rates.
        game = {"pools": {}, "options": {}, "source": "bc.godfat.org (validated against PONOS)", "version": None}
        for event in events:
            gid = event["gacha_id"]
            if gid not in game["pools"]:
                print(f"Pool {event['event_id']}", flush=True)
                game["pools"][gid] = source.pool(event)
            game["options"][gid] = state.get("banners", {}).get(str(gid), {}).get("option", {})
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
        config.get("seriesNames", {}), metadata, today=args.today)
    # Registered historical IDs are sufficient to repair their artwork, without
    # presenting an expired pool as today's version of that banner.
    for gid in ids:
        if str(gid) not in state["banners"] and str(gid) in cache:
            state["banners"][str(gid)] = {"name": cache[str(gid)], "family": cache[str(gid)],
                                         "start_date": "2000-01-01", "option": game.get("options", {}).get(gid, {})}
    drawables = args.app_drawables
    if drawables is None and config.get("appDrawables") and os.name == "nt":
        drawables = Path(config["appDrawables"])
    outputs = plan_images(catalog, state, metadata, source.image, repository,
                          config["publicImageBase"], report, drawables, today=args.today)
    report["missingImages"] = [b["nombre"] for b in catalog["gachas"]
                               if image_missing(repository, b, outputs)]
    outputs.update({repository / "all_gachas_en.json": serialize(catalog),
                    repository / "gacha_id_cache.json": serialize(cache),
                    repository / "gacha_sync_state.json": serialize(state)})
    changed = publish(outputs, dry_run=True)
    report["pendingWrites"] = [str(path.relative_to(repository)) if path.is_relative_to(repository)
                              else str(path) for path in changed]
    # Preserve the last applied change list in the public report on a no-op run.
    public_report = dict(report)
    public_report.pop("pendingWrites")
    if not report["changes"] and not report["images"]:
        last = read_json(repository / "gacha_sync_report.json", {})
        public_report["changes"] = last.get("changes", [])
        public_report["images"] = last.get("images", [])
    outputs[repository / "gacha_sync_report.json"] = serialize(public_report)
    if not args.dry_run:
        outputs[repository / ".gacha_sync_run.json"] = serialize(report)
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
            stream.write(f"### EN banner sync\n\n{len(report['changes'])} catalogue changes; "
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
    parser.add_argument("--repo", type=Path, default=ROOT)
    parser.add_argument("--bcdata", type=Path, help="Local BCData checkout (latest EN); detected automatically on this PC")
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
            publish({args.repo.resolve() / ".gacha_sync_run.json": serialize({
                "errors": [message], "changes": [], "images": [], "pending": []})})
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
