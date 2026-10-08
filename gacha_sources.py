"""Read PONOS schedules, game capsule pools and ID-addressed banner artwork."""
from __future__ import annotations

import csv
from datetime import date, datetime, timedelta
from decimal import Decimal
import io
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image

import fetch_bc_schedule as schedule


POOL_FIELDS = ("rares", "super_rares", "ubers", "legends")
RATE_FIELDS = ("rareChance", "supaChance", "uberChance", "legendChance")
USER_AGENT = "UpdatedBCData/1.0 (https://github.com/deivih84/UpdatedBCData)"
GAME_FILES = ("GatyaDataSetR1.csv", "unitbuy.csv", "GatyaData_Option_SetR.tsv")
WIKIS = ("https://battlecats.miraheze.org/w/api.php", "https://battle-cats.fandom.com/api.php")
# These unlabelled originals were visually verified as English. Other generic
# wiki filenames can contain Japanese artwork even when the pool ID is EN.
VERIFIED_EN_WIKI_BANNER_IDS = frozenset({174, 582, 640})


def scheduled_events(tsv, today=None, horizon=180):
    """Keep original start dates, all rare slots and future permanent sets."""
    today = today or date.today()
    events = {}
    for line in tsv.splitlines():
        cols = line.rstrip("\r\n").split("\t")
        if len(cols) < 10 or not cols[0].isdigit():
            continue
        try:
            start = datetime.strptime(cols[0], "%Y%m%d").date()
            end = datetime.strptime(cols[2], "%Y%m%d").date()
            if int(cols[3]) == 0:
                end -= timedelta(days=1)
            if end < today or start > today + timedelta(days=horizon):
                continue
            index = 8
            for _ in range(int(cols[7])):
                count = int(cols[index]); index += 1 + count * 4
                count = int(cols[index]); index += 1 + count
                index += 1
                count = int(cols[index]); index += 1 + count * 2
            # Type 4 is EXTRA (E), not Legend. N/E IDs overlap with R IDs.
            if int(cols[index]) in (0, 4):
                continue
            expected = int(cols[index + 1])
            width = 17 if int(cols[index]) == 4 else 15
            if len(cols) < index + 2 + expected * width:
                raise ValueError("Truncated PONOS capsule row")
            for entry in schedule._extract_gacha_entries(cols):
                gid = entry["gacha_id"]
                ev = {"gacha_id": gid, "event_id": f"{start.isoformat()}_{gid}",
                      "start_date": start.isoformat(), "end_date": end.isoformat(),
                      "tsv_full": entry["tsv_full"], "tsv_name": entry["tsv_name"], "gacha_type": int(cols[index])}
                for field, source in zip(RATE_FIELDS, ("rare_chance", "super_chance", "uber_chance", "legend_chance")):
                    ev[field] = entry[source]
                key = (ev["event_id"], tuple(ev[f] for f in RATE_FIELDS))
                previous = events.get(key)
                if previous is None or previous["end_date"] < ev["end_date"]:
                    events[key] = ev
        except (IndexError, TypeError) as error:
            raise ValueError("Malformed PONOS capsule row") from error
    if not events:
        raise ValueError("PONOS schedule has no current or upcoming rare capsules")
    return sorted(events.values(), key=lambda e: (e["start_date"], e["gacha_id"]))


def parse_game_data(files):
    units = list(csv.reader(io.StringIO(files["unitbuy.csv"])))
    pools = {}
    for gid, row in enumerate(csv.reader(io.StringIO(files["GatyaDataSetR1.csv"]))):
        pool = {field: [] for field in POOL_FIELDS}
        terminated = False
        for value in row:
            if not value.strip():
                continue
            unit = int(value)
            if unit == -1:
                terminated = True
                break
            if unit < 0 or unit >= len(units) or len(units[unit]) <= 13:
                raise ValueError(f"Pool {gid}: unknown unit {unit}")
            rarity = int(units[unit][13])
            if rarity in (2, 3, 4, 5):
                pool[POOL_FIELDS[rarity - 2]].append(unit)
            else:
                pool.setdefault("unsupported_ids", []).append(unit)
        if row and not terminated:
            raise ValueError(f"Pool {gid}: missing terminator")
        pools[gid] = pool
    options = {}
    for row in csv.DictReader(io.StringIO(files["GatyaData_Option_SetR.tsv"]), delimiter="\t"):
        gid = int(row["GatyaSetID"])
        if gid in options:
            raise ValueError(f"Duplicate capsule option {gid}")
        options[gid] = {key: int(row[key]) for key in ("seriesID", "imgID")}
    return {"pools": pools, "options": options}


def load_local_game(root, *, region="en"):
    root = Path(root)
    versions = [line.strip()[:-2] for line in (root / "latest.txt").read_text().splitlines()
                if line.strip().endswith(region)]
    if len(versions) != 1 or not re.fullmatch(r"\d+\.\d+\.\d+", versions[0]):
        raise ValueError(f"BCData latest.txt must declare one {region.upper()} version")
    directory = root / (versions[0] + region) / "DataLocal"
    result = parse_game_data({name: (directory / name).read_text(encoding="utf-8-sig") for name in GAME_FILES})
    result.update(version=versions[0], source="BCData " + region.upper() + " " + versions[0])
    return result


def parse_godfat_pool(html, event_id, *, region="en"):
    """Reject fallback pages and incomplete lists instead of emptying a pool."""
    soup = BeautifulSoup(html, "html.parser")
    language = soup.find("select", attrs={"name": "lang"})
    selected_language = language.find("option", selected=True) if language else None
    if (region != "en" or selected_language is not None) and (selected_language is None or selected_language.get("value") != region):
        raise ValueError("Godfat returned a different game region")
    select = soup.find("select", attrs={"name": "event"})
    selected = select.find("option", selected=True) if select else None
    if selected is None or selected.get("value") != event_id:
        raise ValueError(f"Godfat did not return requested event {event_id}")
    info = soup.find("div", class_="information")
    if info is None:
        raise ValueError("Godfat returned no pool information")
    result = {field: [] for field in POOL_FIELDS}
    result.update({field: 0 for field in RATE_FIELDS})
    found = set()
    labels = dict(zip(("Rare", "Super", "Uber", "Legend"), zip(POOL_FIELDS, RATE_FIELDS)))
    for li in info.find_all("li"):
        match = re.match(r"\s*(Rare|Super|Uber|Legend(?:ary)?):\s*([\d.]+)%\s*\((\d+) cats?\)", li.get_text(" ", strip=True))
        if not match:
            continue
        label, chance, count = match.groups()
        if label == "Legendary":
            label = "Legend"
        if label in found:
            raise ValueError(f"Godfat returned duplicate {label} rarity")
        found.add(label)
        ids_key, rate_key = labels[label]
        result[rate_key] = int(Decimal(chance) * 100)
        for link in li.find_all("a", href=True):
            cat = re.search(r"/cats/(\d+)(?:\?|$)", link["href"])
            if cat:
                result[ids_key].append(int(cat.group(1)) - 1)
        if len(result[ids_key]) != int(count):
            raise ValueError(f"Godfat returned incomplete {label} pool")
    if not found or sum(result[f] for f in RATE_FIELDS) != 10000:
        raise ValueError("Godfat pool rates must add up to 100%")
    return result


def validate_banner_dimensions(width, height):
    """Reject capsule-menu buttons and portraits, including enlarged squares."""
    if (not isinstance(width, int) or not isinstance(height, int)
            or not (600 <= width <= 4096 and 150 <= height <= 4096)
            or not 2 <= width / height <= 6):
        raise ValueError(f"Unexpected banner dimensions {width}x{height}")


def png_bytes(data):
    """Fully decode network images and return a deterministic, verified PNG."""
    if len(data) > 12 * 1024 * 1024:
        raise ValueError("Banner image exceeds 12 MB")
    try:
        with Image.open(io.BytesIO(data)) as image:
            width, height = image.size
            validate_banner_dimensions(width, height)
            image.load()
            output = io.BytesIO()
            image.convert("RGBA").save(output, format="PNG")
            return output.getvalue()
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("Source did not return a valid banner image") from error


class BannerSource:
    def __init__(self, session=None, *, region="en"):
        if region not in ("en", "jp"):
            raise ValueError("Unsupported banner region")
        self.region = region
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def pool(self, event):
        response = self.session.get("https://bc.godfat.org/", params={
            "lang": self.region, "event": event["event_id"], "details": "true", "seed": 1, "count": 1}, timeout=30)
        response.raise_for_status()
        return parse_godfat_pool(response.text, event["event_id"], region=self.region)

    def metadata(self, gid, option=None, *, fallback_image_id=None):
        option = option or {}
        result = {"warnings": []}
        prefix = "rareenR" if self.region == "en" else "rareR"
        url = f"https://ponos.s3.dualstack.ap-northeast-1.amazonaws.com/information/appli/battlecats/gacha/{prefix}{gid:03d}.html"
        try:
            response = self.session.get(url, timeout=20)
            if response.ok:
                soup = BeautifulSoup(response.content, "html.parser")
                heading = soup.find("h2")
                if heading:
                    result.update(name=heading.get_text(" ", strip=True), name_source=url)
                # Only exact ID-addressed artwork can be chosen automatically.
                for image in soup.find_all("img", src=True):
                    image_url = urljoin(url, image["src"])
                    if re.search(rf"/gatya_bnr{gid}\.png$", urlparse(image_url).path):
                        result.update(image_url=image_url, image_source=url)
                        return result
        except requests.RequestException:
            pass
        suffix = "en" if self.region == "en" else "jp"
        def image_titles(image_id):
            titles = [f"File:Gatya bnr{image_id} {suffix}.png"]
            if self.region == 'jp' or image_id in VERIFIED_EN_WIKI_BANNER_IDS:
                titles.append(f"File:Gatya bnr{image_id}.png")
            if self.region == 'jp':
                titles.insert(0, f"File:Gatya bnr{image_id} ja.png")
            return titles
        titles = image_titles(gid)
        image_id = option.get("imgID", -1)
        if image_id >= 0 and image_id != gid:
            titles.extend(image_titles(image_id))
        exact_titles = list(titles)
        # Family artwork is an explicit, reviewed mapping, never a menu button.
        if fallback_image_id is not None:
            if not isinstance(fallback_image_id, int) or fallback_image_id < 0:
                raise ValueError("Family banner ID must be a nonnegative integer")
            titles.extend(image_titles(fallback_image_id))
        titles = list(dict.fromkeys(titles))
        wiki_pages = {}
        fallback_titles = [title for title in titles if title not in exact_titles]
        for group in (exact_titles, fallback_titles):
            if not group:
                continue
            for api in WIKIS:
                try:
                    if api not in wiki_pages:
                        wiki_pages[api] = {}
                        response = self.session.get(api, params={"action": "query", "format": "json",
                            "prop": "imageinfo", "iiprop": "url|size", "titles": "|".join(titles)}, timeout=25)
                        response.raise_for_status()
                        body = response.json()
                        if not isinstance(body, dict) or not isinstance(body.get("query"), dict):
                            raise ValueError("Malformed wiki response")
                        pages = body["query"].get("pages", {})
                        if not isinstance(pages, dict) or any(not isinstance(page, dict) for page in pages.values()):
                            raise ValueError("Malformed wiki image pages")
                        wiki_pages[api] = {page.get("title"): page for page in pages.values()}
                    candidates = wiki_pages[api]
                    for title in group:
                        page = candidates.get(title, {})
                        infos = page.get("imageinfo", [])
                        if not isinstance(infos, list) or any(not isinstance(info, dict) for info in infos):
                            raise ValueError("Malformed wiki image metadata")
                        if not infos:
                            continue
                        if not isinstance(infos[0].get("url"), str):
                            raise ValueError("Malformed wiki image URL")
                        try:
                            validate_banner_dimensions(infos[0].get("width"), infos[0].get("height"))
                        except ValueError:
                            result["warnings"].append("image_rejected: " + title)
                            continue
                        result.update(image_url=infos[0]["url"], image_source=infos[0].get("descriptionurl", api))
                        if not result.get("name"):
                            usages = self.session.get(api, params={"action": "query", "format": "json",
                                "list": "imageusage", "iutitle": title, "iunamespace": 0, "iulimit": 50}, timeout=25)
                            usages.raise_for_status()
                            data = usages.json()
                            if not isinstance(data, dict) or not isinstance(data.get("query"), dict):
                                raise ValueError("Malformed wiki image usage")
                            usage_rows = data["query"].get("imageusage", [])
                            if not isinstance(usage_rows, list) or any(
                                not isinstance(row, dict) or not isinstance(row.get("title"), str)
                                for row in usage_rows
                            ):
                                raise ValueError("Malformed wiki usage rows")
                            names = {row["title"].split(" (Gacha Event)")[0]
                                     for row in usage_rows
                                     if " (Gacha Event)" in row["title"]}
                            if len(names) == 1 and "continue" not in data:
                                result.update(name=names.pop(), name_source=api)
                        return result
                except (requests.RequestException, ValueError, KeyError, TypeError):
                    result["warnings"].append("wiki_unavailable: " + api)
        return result

    def image(self, url):
        if urlparse(url).scheme != "https":
            raise ValueError("Artwork source must use HTTPS")
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return png_bytes(response.content)
