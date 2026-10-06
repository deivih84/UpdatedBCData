"""Plan compatible capsule catalogue changes and publish them transactionally."""
from __future__ import annotations

import copy
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import unicodedata

import requests

from gacha_sources import POOL_FIELDS, RATE_FIELDS


def serialize(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def label_key(value):
    return re.sub(r"[\W_]", "", unicodedata.normalize("NFKC", value.casefold().replace(" (gacha event)", "")))


def validate_pool(event, pool):
    rates = [event[field] for field in RATE_FIELDS]
    if any(type(rate) is not int or rate < 0 for rate in rates) or sum(rates) != 10000:
        raise ValueError(f"{event['event_id']}: rarity rates must total 10000")
    if pool.get("unsupported_ids"):
        raise ValueError(f"{event['event_id']}: unsupported unit rarities")
    seen = set()
    for field, rate in zip(POOL_FIELDS, rates):
        ids = pool[field]
        if not isinstance(ids, list) or any(type(unit) is not int or unit < 0 for unit in ids):
            raise ValueError(f"{event['event_id']}: invalid {field} IDs")
        if rate and not ids:
            raise ValueError(f"{event['event_id']}: empty pool for nonzero {field} chance")
        if seen.intersection(ids):
            raise ValueError(f"{event['event_id']}: unit appears in different rarities")
        seen.update(ids)
        if field in pool and RATE_FIELDS[POOL_FIELDS.index(field)] in pool:
            if pool[RATE_FIELDS[POOL_FIELDS.index(field)]] != rate:
                raise ValueError(f"{event['event_id']}: Godfat and PONOS probabilities disagree")


def fingerprint(event, pool):
    return hashlib.sha256(serialize({field: pool[field] for field in POOL_FIELDS} |
                                   {field: event[field] for field in RATE_FIELDS})).hexdigest()


def plan_catalog(catalog, cache, state, events, game, series_names, metadata, *, today=None, region="en"):
    today = today or date.today()
    catalog, cache, state = copy.deepcopy((catalog, cache, state))
    banners = catalog["gachas"]
    by_name = {b["nombre"]: b for b in banners}
    if len(by_name) != len(banners):
        raise ValueError("Duplicate canonical banner names")
    aliases = {}
    for b in banners:
        for name in [b["nombre"]] + b.get("aliases", []):
            aliases.setdefault(label_key(name), set()).add(b["nombre"])
    if any(len(names) > 1 for names in aliases.values()):
        raise ValueError("Catalogue has ambiguous aliases")
    state.setdefault("schemaVersion", 1)
    previous = state.setdefault("banners", {})
    def family_of(candidate):
        families = {record.get("family", candidate) for record in previous.values()
                    if record.get("name") == candidate}
        if len(families) == 1:
            return families.pop()
        variant = re.fullmatch(rf"(.+) \({region.upper()} #(\d+)\)", candidate)
        if variant and previous.get(variant.group(2), {}).get("family") == variant.group(1):
            return variant.group(1)
        return candidate
    report = {"sources": {"schedule": "PONOS gatya.tsv", "pools": game.get("source", "Godfat")},
              "changes": [], "pending": [], "images": [], "errors": []}
    groups = {}
    id_rates = {}
    for ev in events:
        id_rates.setdefault(ev["gacha_id"], set()).add(tuple(ev[f] for f in RATE_FIELDS))
    conflicting = {gid for gid, rates in id_rates.items() if len(rates) > 1}
    for gid in sorted(conflicting):
        report["pending"].append({"gacha_id": gid, "reason": "conflicting_id_variants"})
    for ev in events:
        gid = ev["gacha_id"]
        if gid in conflicting:
            continue
        pool = game["pools"].get(gid)
        if pool is None:
            raise ValueError(f"Missing game pool for {ev['event_id']}")
        validate_pool(ev, pool)
        option = game.get("options", {}).get(gid, {})
        candidates = set()
        cached = cache.get(str(gid))
        if cached:
            cached = family_of(cached)
            if cached in by_name:
                candidates.add(cached)
        configured = series_names.get(str(option.get("seriesID")))
        if configured:
            candidates.add(configured)
        for name in (() if region == "jp" else (ev.get("tsv_full", ""), ev.get("tsv_name", ""))):
            for candidate in aliases.get(label_key(name), set()):
                candidates.add(family_of(candidate))
        meta = metadata.get(gid, {})
        if not candidates and meta.get("name") and meta.get("name_source"):
            candidates.update(family_of(candidate) for candidate in
                              (aliases.get(label_key(meta["name"]), set()) or [meta["name"]]))
        if len(candidates) != 1:
            report["pending"].append({"gacha_id": gid, "event_id": ev["event_id"],
                                      "text": ev.get("tsv_full", ""), "reason":
                                      "identity_conflict" if candidates else "unknown_identity",
                                      "candidates": sorted(candidates)})
            continue
        family = candidates.pop()
        groups.setdefault(family, []).append((ev, pool, option, meta))
    for family, rows in groups.items():
        # Prefer the most recently started active pool; otherwise the nearest future one.
        active = [row for row in rows if row[0]["start_date"] <= today.isoformat()]
        primary = max(active, key=lambda row: row[0]["start_date"]) if active else min(rows, key=lambda row: row[0]["start_date"])
        primary_hash = fingerprint(primary[0], primary[1])
        # The active canonical entry owns shared aliases regardless of input order.
        rows = sorted(rows, key=lambda row: (fingerprint(row[0], row[1]) != primary_hash,
                                            row[0]["start_date"], row[0]["gacha_id"]))
        for ev, pool, option, meta in rows:
            gid = ev["gacha_id"]
            content_hash = fingerprint(ev, pool)
            name = family if content_hash == primary_hash else f"{family} ({region.upper()} #{gid})"
            old = copy.deepcopy(by_name.get(name))
            if old is None:
                b = {"nombre": name, "aliases": [name], "imagen_url": ""}
                if family in by_name:
                    b["imagen_url"] = by_name[family].get("imagen_url", "")
                banners.append(b)
                by_name[name] = b
            else:
                b = by_name[name]
            for field in POOL_FIELDS:
                b[field] = list(pool[field])
            for field in RATE_FIELDS:
                b[field] = ev[field]
            for alias in ((meta.get("name"),) if region == "jp" else (ev.get("tsv_full"), ev.get("tsv_name"), meta.get("name"))):
                if not alias:
                    continue
                owners = aliases.get(label_key(alias), set())
                if owners and owners != {name}:
                    continue
                if alias not in b.setdefault("aliases", [name]):
                    b["aliases"].append(alias)
                aliases.setdefault(label_key(alias), set()).add(name)
            cache[str(gid)] = name
            image_record = previous.get(str(gid), {}).get("image")
            previous[str(gid)] = {"family": family, "name": name, "fingerprint": content_hash,
                                  "pool": {field: list(pool[field]) for field in POOL_FIELDS},
                                  "rates": {field: ev[field] for field in RATE_FIELDS},
                                  "option": option, "source": game.get("poolSources", {}).get(gid, game.get("source", "Godfat")),
                                  "gameVersion": game.get("poolVersions", {}).get(gid, game.get("version")),
                                  "start_date": ev["start_date"], "end_date": ev["end_date"]}
            if image_record:
                previous[str(gid)]["image"] = image_record
            if old != b:
                change = {"name": name, "gacha_id": gid, "created": old is None,
                          "units": {}, "rates": {}}
                for field in POOL_FIELDS:
                    before = (old or {}).get(field, [])
                    if before != b[field]:
                        change["units"][field] = {"added": sorted(set(b[field]) - set(before)),
                                                   "removed": sorted(set(before) - set(b[field]))}
                for field in RATE_FIELDS:
                    before = (old or {}).get(field)
                    if before != b[field]:
                        change["rates"][field] = {"old": before, "new": b[field]}
                report["changes"].append(change)
    return catalog, cache, state, report


def plan_images(catalog, state, metadata, fetch_image, repository, public_base,
                report, drawables=None, *, today=None, region="en"):
    today = today or date.today()
    groups = {}
    for id_text, record in state.get("banners", {}).items():
        gid = int(id_text)
        if gid in metadata:
            groups.setdefault(record["name"], []).append((gid, record))
    outputs, downloaded = {}, {}
    by_name = {b["nombre"]: b for b in catalog["gachas"]}
    for name, candidates in groups.items():
        if name not in by_name:
            continue
        active = [row for row in candidates if row[1]["start_date"] <= today.isoformat()]
        gid, record = max(active, key=lambda row: (row[1]["start_date"], row[0])) if active else min(candidates, key=lambda row: (row[1]["start_date"], row[0]))
        meta = metadata[gid]
        image_url = meta.get("image_url")
        if not image_url:
            report["pending"].append({"name": name, "gacha_id": gid, "reason": "image_not_found"})
            continue
        try:
            if image_url not in downloaded:
                downloaded[image_url] = fetch_image(image_url)
            data = downloaded[image_url]
            digest = hashlib.sha256(data).hexdigest()
            filename = f"banner_{region}_{gid}_{digest[:16]}.png"
            destination = Path(repository) / "images" / "gacha" / filename
            outputs[destination] = data
            if drawables is not None and Path(drawables).is_dir():
                outputs[Path(drawables) / filename] = data
            new_url = public_base.rstrip("/") + "/" + filename
            old_url = by_name[name].get("imagen_url", "")
            by_name[name]["imagen_url"] = new_url
            record["image"] = {"sourceUrl": image_url, "sourcePage": meta.get("image_source"),
                               "sha256": digest, "file": filename}
            if old_url != new_url or not destination.exists():
                report["images"].append({"name": name, "gacha_id": gid, "file": filename})
        except (requests.RequestException, ValueError, OSError) as error:
            report["pending"].append({"name": name, "gacha_id": gid,
                                      "reason": "image_unavailable", "detail": str(error)})
    return outputs


def publish(outputs, *, dry_run=False, replace_file=os.replace):
    changed = {Path(path): data for path, data in outputs.items()
               if not Path(path).exists() or Path(path).read_bytes() != data}
    if dry_run or not changed:
        return list(changed)
    originals = {path: path.read_bytes() if path.exists() else None for path in changed}
    temporary = {}
    published = []
    try:
        for path, data in changed.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                stream.write(data)
                temporary[path] = Path(stream.name)
        for path in changed:
            replace_file(temporary[path], path)
            published.append(path)
    except Exception:
        for path in reversed(published):
            if originals[path] is None:
                path.unlink()
            else:
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                    stream.write(originals[path])
                    backup = Path(stream.name)
                os.replace(backup, path)
        raise
    finally:
        for path in temporary.values():
            if path.exists():
                path.unlink()
    return list(changed)
