#!/usr/bin/env python3
"""
fetch_bc_events.py
Fetches Battle Cats EN event schedule without Discord.

Two sources (in priority order):
  1. Ponos sale.tsv  — same JWT auth as fetch_bc_schedule.py
     sale.tsv has event stage schedule data with numeric pack IDs.
     IDs are mapped to names via all_events.json (field "event_id" when present),
     or via fuzzy name matching against the Miraheze wiki.
  2. Miraheze wiki   — MediaWiki API, human-readable event names + dates.
     Used both as a fallback AND to enrich names not resolvable from sale.tsv.

Updates the "eventos" section in gachas_eventos_actualizados_en1.json.
Saves raw sale.tsv to .bc_sale_raw.tsv for inspection / debugging.
"""

import hashlib
import hmac
import json
import re
import secrets
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: pip install requests")

from bc_event_name_resolver import BCEventNameResolver

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
USER_AGENT  = "Dalvik/2.1.0 (Linux; U; Android 13; XQ-BC52 Build/61.2.A.0.447)"
DISCORD_API = "https://discord.com/api/v10"

# Discord credentials — read from bot_updater_events.py to avoid duplicating secrets.
# Falls back to env vars if the file is not present.
def _read_discord_creds():
    import os, re as _re
    from pathlib import Path as _Path
    token, channel = "", "1445468966989332563"
    src = _Path(__file__).parent / "bot_updater_events.py"
    if src.exists():
        text = src.read_text(encoding="utf-8")
        m = _re.search(r"DISCORD_TOKEN\s*=\s*['\"]([^'\"]+)['\"]", text)
        if m:
            token = m.group(1)
        m = _re.search(r"CHANNEL_ID_COMANDOS\s*=\s*(\d+)", text)
        if m:
            channel = m.group(1)
    token   = token   or os.environ.get("DISCORD_TOKEN", "")
    channel = channel or os.environ.get("CHANNEL_ID",    "1445468966989332563")
    return token, channel

DISCORD_TOKEN, CHANNEL_ID = _read_discord_creds()

ACCOUNT_URL  = "https://nyanko-backups.ponosgames.com/?action=createAccount&referenceId={ref}"
PASSWORD_URL = "https://nyanko-auth.ponosgames.com/v1/users"
JWT_URL      = "https://nyanko-auth.ponosgames.com/v1/tokens"
SALE_URL     = "https://nyanko-events.ponosgames.com/battlecatsen_production/sale.tsv?jwt={token}"

SCRIPT_DIR    = Path(__file__).parent
EVENTS_FILE   = SCRIPT_DIR / "all_events.json"
OUTPUT_FILE   = SCRIPT_DIR / "gachas_eventos_actualizados_en1.json"
STATE_FILE    = SCRIPT_DIR / ".bc_state.json"
SALE_RAW_FILE = SCRIPT_DIR / ".bc_sale_raw.tsv"
UNKNOWN_REPORT_FILE = SCRIPT_DIR / "unknown_event_ids.json"

WINDOW_PAST_DAYS   = 0
WINDOW_FUTURE_DAYS = 180

# ---------------------------------------------------------------------------
# Auth helpers (identical to fetch_bc_schedule.py)
# ---------------------------------------------------------------------------

def _nyanko_sig(account_code, body):
    rand = secrets.token_hex(32)
    key  = (account_code + rand).encode()
    sig  = hmac.new(key, body.encode(), hashlib.sha256).hexdigest()
    return rand + sig


def _auth_headers(account_code, body):
    return {
        "Nyanko-Signature":           _nyanko_sig(account_code, body),
        "Nyanko-Signature-Version":   "1",
        "Nyanko-Signature-Algorithm": "HMACSHA256",
        "Content-Type":               "application/json",
        "Nyanko-Timestamp":           str(int(time.time() * 1000)),
        "User-Agent":                 USER_AGENT,
        "Connection":                 "Keep-Alive",
        "Accept-Encoding":            "gzip",
    }


def _post(url, account_code, payload):
    body = json.dumps(payload, separators=(",", ":"))
    r = requests.post(url, data=body, headers=_auth_headers(account_code, body), timeout=30)
    r.raise_for_status()
    return r.json()


def _load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _create_account():
    ref = uuid.uuid4().hex
    r = requests.get(ACCOUNT_URL.format(ref=ref), headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    data = r.json()
    if not data.get("success"):
        raise RuntimeError(f"Account creation failed: {data}")
    code = data["accountId"]
    print(f"  Created account: {code}")
    result = _post(PASSWORD_URL, code, {
        "accountCode":      code,
        "accountCreatedAt": str(int(time.time())),
        "nonce":            secrets.token_hex(32),
    })
    payload = result["payload"]
    return {
        "account_code":  code,
        "password":      payload["password"],
        "refresh_token": payload["passwordRefreshToken"],
        "jwt_token":     None,
        "jwt_ts":        0,
    }


def _get_jwt(state):
    age = time.time() - state.get("jwt_ts", 0)
    if state.get("jwt_token") and age < 11 * 3600:
        return state["jwt_token"]
    result = _post(JWT_URL, state["account_code"], {
        "accountCode": state["account_code"],
        "clientInfo": {
            "client": {"countryCode": "ja", "version": "999999"},
            "device": {"model": "XQ-BC52"},
            "os":     {"type": "android", "version": "Android 13"},
        },
        "nonce":    secrets.token_hex(32),
        "password": state["password"],
    })
    token = result["payload"]["token"]
    state["jwt_token"] = token
    state["jwt_ts"]    = time.time()
    _save_state(state)
    print("  JWT token refreshed")
    return token


def get_auth_token():
    state = _load_state()
    if not state.get("account_code"):
        print("Creating new anonymous BC account...")
        state = _create_account()
        _save_state(state)
    return _get_jwt(state)

# ---------------------------------------------------------------------------
# sale.tsv fetch
# ---------------------------------------------------------------------------

def fetch_sale_tsv(jwt):
    url = SALE_URL.format(token=jwt)
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    content = r.content.decode("utf-8")
    SALE_RAW_FILE.write_text(content, encoding="utf-8")
    print(f"  Saved raw sale.tsv to {SALE_RAW_FILE.name} ({len(content)} bytes)")
    return content

# ---------------------------------------------------------------------------
# sale.tsv parsing
#
# Structure per line (tab-separated):
#   [0] startDate  YYYYMMDD
#   [1] startTime  HHMM
#   [2] endDate    YYYYMMDD
#   [3] endTime    HHMM
#   [4] minVersion
#   [5] maxVersion
#   [6] entryType  (0 = schedule entry; skip others)
#   [7] sectionCount
#   [8+] sectionCount × section blocks
#         Each section: day_set_count  day_set_count×4  day_count  day_count×1
#                       weekday_bitmask  time_count  time_count×2
#   after sections: count  ID1  ID2 ... IDn  0  (0 = terminator, -N = markers to skip)
#
# Unlike gatya.tsv there is NO gacha_type/category_count header between sections and IDs.
# IDs are plain integer event-pack identifiers; no human-readable names are embedded.
# ---------------------------------------------------------------------------

def _bc_date(v):
    if v <= 0:
        return None
    y, rest = divmod(v, 10000)
    m, d    = divmod(rest, 100)
    if not (2000 <= y <= 2050 and 1 <= m <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


def _skip_sections(cols, idx):
    """Skip the variable-length section blocks, return new idx."""
    try:
        section_count = int(cols[idx]); idx += 1
        for _ in range(section_count):
            day_set_count = int(cols[idx]); idx += 1
            idx += day_set_count * 4
            day_count = int(cols[idx]); idx += 1
            idx += day_count
            idx += 1  # weekday bitmask
            time_count = int(cols[idx]); idx += 1
            idx += time_count * 2
    except (ValueError, IndexError):
        return None
    return idx


def parse_sale_tsv(content):
    """
    Parse sale.tsv. Returns list of dicts: {start_date, end_date, pack_ids}.
    pack_ids is a list of integer event pack IDs from the entry block.
    """
    today         = datetime.now(timezone.utc).date()
    cutoff_past   = today - timedelta(days=WINDOW_PAST_DAYS)
    cutoff_future = today + timedelta(days=WINDOW_FUTURE_DAYS)

    rows = []
    unknown_ids = set()

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        cols = line.split("\t")
        if len(cols) < 8:
            continue
        try:
            start_date = _bc_date(int(cols[0]))
            end_raw    = int(cols[2])
            end_time   = int(cols[3])

            if end_time == 0:
                dt       = datetime.strptime(str(end_raw), "%Y%m%d") - timedelta(days=1)
                end_date = dt.strftime("%Y-%m-%d")
            else:
                end_date = _bc_date(end_raw)

            if not start_date or not end_date:
                continue

            start_d = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_d   = datetime.strptime(end_date,   "%Y-%m-%d").date()

            # Skip always-available rotating stage schedules (permanent entries)
            if (end_d - today).days > 365 * 2:
                continue

            if end_d < cutoff_past or start_d > cutoff_future:
                continue

            # Skip section header blocks (same structure as gatya.tsv)
            if int(cols[6]) != 0:
                continue

            idx = _skip_sections(cols, 7)
            if idx is None or idx >= len(cols):
                continue

            # After sections: count  ID1  ID2 ... IDn  0
            # 0 = terminator; negative values are markers — skip both
            pack_ids = []
            try:
                count = int(cols[idx]); idx += 1
                for i in range(count):
                    if idx + i >= len(cols):
                        break
                    v = int(cols[idx + i])
                    if v > 0:
                        pack_ids.append(v)
            except (ValueError, IndexError):
                pass

            if pack_ids:
                rows.append({
                    "start_date": start_date,
                    "end_date":   end_date,
                    "pack_ids":   pack_ids,
                })
                unknown_ids.update(pack_ids)

        except (ValueError, IndexError):
            continue

    if unknown_ids:
        print(f"  Found pack IDs in sale.tsv: {sorted(unknown_ids)}")
        print("  These IDs will be resolved through all_events.json and the local BCData index.")

    return rows

# ---------------------------------------------------------------------------
# Event name DB (all_events.json)
# ---------------------------------------------------------------------------

def load_event_db():
    """
    Returns:
      by_id    {int event_id/one of event_ids -> event_dict}
      by_name  {name_or_alias_lower -> event_dict}
    """
    by_id   = {}
    by_name = {}
    if EVENTS_FILE.exists():
        data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        for ev in data.get("events", []):
            by_name[ev["nombre"].lower()] = ev
            for alias in ev.get("aliases", []):
                if alias:
                    by_name[str(alias).lower()] = ev
            if "event_id" in ev:
                by_id[int(ev["event_id"])] = ev
            for event_id in ev.get("event_ids", []):
                by_id[int(event_id)] = ev
    return by_id, by_name


def _parse_iso_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date()


def _date_ranges_overlap(a_start, a_end, b_start, b_end):
    return _parse_iso_date(a_start) <= _parse_iso_date(b_end) and \
        _parse_iso_date(b_start) <= _parse_iso_date(a_end)


def _entry_end_date(item):
    return item.get("fecha_fin") or item.get("end_date")


def _entry_start_date(item):
    return item.get("fecha_inicio") or item.get("start_date")


def filter_relevant_event_entries(items, today=None, max_start_age_days=None):
    today = today or datetime.now(timezone.utc).date()
    filtered = []
    start_cutoff = today - timedelta(days=max_start_age_days) if max_start_age_days is not None else None
    for item in items:
        end_value = _entry_end_date(item)
        if not end_value or _parse_iso_date(end_value) < today:
            continue
        if start_cutoff is not None:
            start_value = _entry_start_date(item)
            if not start_value or _parse_iso_date(start_value) < start_cutoff:
                continue
        filtered.append(item)
    return filtered


def _dedupe_dicts(items, key_fields):
    seen = set()
    unique = []
    for item in items:
        key = tuple(item.get(field) for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _candidate_events_for_occurrences(occurrences, discord_events):
    candidates = []
    for occurrence in occurrences:
        for ev in discord_events:
            if occurrence["start_date"] == ev["start_date"] and occurrence["end_date"] == ev["end_date"]:
                confidence = "exact_dates"
            elif _date_ranges_overlap(
                occurrence["start_date"], occurrence["end_date"],
                ev["start_date"], ev["end_date"],
            ):
                confidence = "date_overlap"
            else:
                continue

            candidates.append({
                "nombre": ev["nombre"],
                "fecha_inicio": ev["start_date"],
                "fecha_fin": ev["end_date"],
                "confidence": confidence,
            })

    confidence_rank = {"exact_dates": 0, "date_overlap": 1}
    candidates = _dedupe_dicts(
        candidates,
        ("nombre", "fecha_inicio", "fecha_fin", "confidence"),
    )
    candidates.sort(key=lambda x: (
        confidence_rank.get(x["confidence"], 99),
        x["fecha_inicio"],
        x["nombre"].lower(),
    ))
    return candidates[:8]


def build_unknown_event_report(sale_rows, by_id, discord_events, by_name=None, resolved_ids=None):
    """
    Build a review-friendly report for event IDs and names that need metadata.

    Unknown Ponos IDs are grouped by ID and paired with Discord candidates using
    exact date matches first, then overlapping date ranges.
    """
    resolved_ids = set(resolved_ids or [])
    unknown_by_id = {}
    for row in sale_rows:
        for pack_id in row["pack_ids"]:
            if pack_id in by_id or pack_id in resolved_ids:
                continue
            unknown_by_id.setdefault(pack_id, []).append({
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "row_pack_ids": row["pack_ids"],
            })

    unknown_entries = []
    sorted_unknown_ids = sorted(
        unknown_by_id,
        key=lambda pack_id: (
            min(item["start_date"] for item in unknown_by_id[pack_id]),
            pack_id,
        ),
    )
    for pack_id in sorted_unknown_ids:
        occurrences = _dedupe_dicts(
            sorted(unknown_by_id[pack_id], key=lambda x: (x["start_date"], x["end_date"])),
            ("start_date", "end_date"),
        )
        unknown_entries.append({
            "event_id": pack_id,
            "status": "needs_mapping",
            "occurrences": occurrences,
            "candidates": _candidate_events_for_occurrences(occurrences, discord_events),
        })

    missing_names = []
    if by_name is not None:
        known_names = set(by_name)
        for ev in discord_events:
            if ev["nombre"].lower() in known_names:
                continue
            missing_names.append({
                "nombre": ev["nombre"],
                "fecha_inicio": ev["start_date"],
                "fecha_fin": ev["end_date"],
                "status": "needs_metadata",
            })
        missing_names = _dedupe_dicts(
            sorted(missing_names, key=lambda x: (x["nombre"].lower(), x["fecha_inicio"])),
            ("nombre", "fecha_inicio", "fecha_fin"),
        )

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {
            "unknown_event_ids": len(unknown_entries),
            "discord_names_missing_metadata": len(missing_names),
        },
        "unknown_event_ids": unknown_entries,
        "discord_names_missing_metadata": missing_names,
    }


def write_unknown_event_report(report):
    UNKNOWN_REPORT_FILE.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

# ---------------------------------------------------------------------------
# Discord REST API — read channel history (no active bot needed)
# ---------------------------------------------------------------------------
# Uses GET /channels/{id}/messages to pull up to 200 recent messages.
# Parses them with the same logic as bot_updater_events.py.
# ---------------------------------------------------------------------------

def _discord_headers():
    return {
        "Authorization": f"Bot {DISCORD_TOKEN}",
        "User-Agent":    "DiscordBot (https://github.com/discord/discord-api-docs, 10)",
        "Content-Type":  "application/json",
    }


def _clean_ansi(text):
    text = re.sub(r"\x1b\[[\d;]*m", "", text)
    text = re.sub(r"\033\[[\d;]*m", "", text)
    text = re.sub(r"\d+;\d+m", "", text)
    text = re.sub(r"\d+m", "", text)
    return text


def _parsear_fecha(fecha_str, mes_referencia=None):
    """Parse date strings used in PackPack event messages."""
    limpia = re.sub(r"(st|nd|rd|th)", "", fecha_str).strip()
    try:
        dt = datetime.strptime(limpia, "%Y %B %d")
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    except ValueError:
        pass

    anio = datetime.now().year
    if "January" in limpia and datetime.now().month == 12:
        anio += 1

    dt = None
    try:
        dt = datetime.strptime(f"{limpia} {anio}", "%B %d %Y")
    except ValueError:
        pass

    if not dt and mes_referencia:
        try:
            ref_date = mes_referencia if not isinstance(mes_referencia, str) \
                else datetime.strptime(mes_referencia, "%Y-%m-%d")
            dia = int(limpia)
            siguiente_mes  = ref_date.month + 1 if ref_date.month < 12 else 1
            siguiente_anio = ref_date.year if ref_date.month < 12 else ref_date.year + 1
            if dia < ref_date.day:
                dt = datetime(siguiente_anio, siguiente_mes, dia)
            else:
                dt = datetime(ref_date.year, ref_date.month, dia)
        except ValueError:
            pass

    if not dt:
        dt = datetime.now()
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def fetch_discord_events(by_name):
    """
    Fetch recent messages from the Discord channel via REST API.
    Parses event schedule messages (same format as bot_updater_events.py).
    Returns list of {nombre, start_date, end_date} dicts.
    """
    headers  = _discord_headers()
    url      = f"{DISCORD_API}/channels/{CHANNEL_ID}/messages"
    messages = []

    # Fetch up to 200 messages (two pages of 100)
    params = {"limit": 100}
    for _ in range(2):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=15)
            if r.status_code == 401:
                print("  Discord: invalid token")
                return []
            r.raise_for_status()
            batch = r.json()
        except Exception as e:
            print(f"  Discord REST failed: {e}")
            break
        if not batch:
            break
        messages.extend(batch)
        params["before"] = batch[-1]["id"]

    if not messages:
        print("  Discord: no messages retrieved")
        return []

    print(f"  Discord: fetched {len(messages)} messages")

    # Reverse to chronological order so region markers apply correctly
    messages.reverse()

    patron_ev = re.compile(r"\[(.+?)\s*[~-]\s*(.+?)\]\s*(.+?)(?=\s*\[|\s*<|$)")
    region    = None
    events    = []

    for msg in messages:
        # Build text from content + embeds
        raw = msg.get("content", "")
        for emb in msg.get("embeds", []):
            if emb.get("description"):
                raw += "\n" + emb["description"]
            if emb.get("title"):
                raw += "\n" + emb["title"]

        texto = _clean_ansi(raw.replace("```ansi", "").replace("```", "").strip())

        if "EN Event Data Found" in texto:
            region = "EN"
            continue
        if "JP Event Data Found" in texto:
            region = "JP"
            continue

        if region != "EN":
            continue

        if "Stage/Event" not in texto:
            continue

        for line in texto.split("\n"):
            line = line.strip()
            if not line or "Stage/Event" in line or "Schedule" in line:
                continue
            m = patron_ev.search(line)
            if not m:
                continue
            ini_str, fin_str, nombre_raw = m.groups()
            nombre = nombre_raw.strip()
            if not nombre:
                continue

            # Strip trailing time-schedule parentheticals, e.g.:
            #   "Catfruit Buffet (08:00 ~ 10:00, 12:00 ~ 14:00, 19:00 ~ 21:00)"
            #   "XP Bonanza! (Tuesday / 08:00 ~ 10:00 | Friday / 16:00 ~ 18:00)"
            nombre = re.sub(r'\s*\([^)]*\d{1,2}:\d{2}[^)]*\)\s*$', '', nombre).strip()
            # Strip weekday-only parentheticals
            #   "After School: Love Letters (Monday, Tuesday, Wednesday, Thursday, Friday / 17:00 ~ 24:00)"
            nombre = re.sub(
                r'\s*\([^)]*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)[^)]*\)\s*$',
                '', nombre
            ).strip()

            if not nombre:
                continue

            dt_ini = _parsear_fecha(ini_str)
            dt_fin = _parsear_fecha(fin_str, mes_referencia=dt_ini)

            # Skip entries with invalid dates (end before start)
            if dt_fin < dt_ini:
                continue

            # Enrich name if in all_events.json
            meta   = by_name.get(nombre.lower())
            nombre = meta["nombre"] if meta else nombre

            events.append({
                "nombre":     nombre,
                "start_date": dt_ini.strftime("%Y-%m-%d"),
                "end_date":   dt_fin.strftime("%Y-%m-%d"),
            })

    # Deduplicate by (nombre, start_date)
    seen, unique = set(), []
    for ev in events:
        key = (ev["nombre"], ev["start_date"])
        if key not in seen:
            seen.add(key)
            unique.append(ev)

    print(f"  Discord: parsed {len(unique)} event entries")
    return unique

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _snake(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _build_event_entry(nombre, start, end, descripcion=""):
    return {
        "id":              f"{_snake(nombre)}_{start}",
        "nombre":          nombre,
        "caracteristicas": [descripcion] if descripcion else [],
        "fecha_inicio":    start,
        "fecha_fin":       end,
    }


def _metadata_for_name(nombre, by_name):
    return by_name.get(nombre.lower()) if by_name else None


def build_bcdata_events(sale_rows, resolver, by_name):
    """
    Convert BCData-resolved sale.tsv IDs into calendar entries.

    Mission-only IDs are considered resolved for diagnostics, but are not shown
    as standalone calendar cards because they are usually too granular.
    """
    bcdata_events = []
    resolved_ids = set()
    seen = set()

    for row in sale_rows:
        for pack_id in row["pack_ids"]:
            hit = resolver.best_hit(pack_id)
            if not hit:
                continue
            resolved_ids.add(pack_id)
            if not resolver.is_calendar_hit(hit):
                continue

            meta = _metadata_for_name(hit.name, by_name)
            nombre = meta["nombre"] if meta else hit.name
            desc = meta.get("descripcion", "") if meta else ""
            key = (pack_id, nombre, row["start_date"], row["end_date"])
            if key in seen:
                continue
            seen.add(key)
            bcdata_events.append(_build_event_entry(
                nombre, row["start_date"], row["end_date"], desc
            ))

    return bcdata_events, resolved_ids

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # 1. Auth
    print("Getting JWT token...")
    jwt = get_auth_token()

    # 2. Fetch sale.tsv
    print("Fetching sale.tsv from Ponos servers...")
    try:
        sale_content = fetch_sale_tsv(jwt)
        sale_rows    = parse_sale_tsv(sale_content)
        print(f"  Parsed {len(sale_rows)} rows from sale.tsv")
    except Exception as e:
        print(f"  sale.tsv fetch failed: {e}")
        sale_rows = []

    # 3. Load event name DB
    by_id, by_name = load_event_db()
    bcdata_resolver = BCEventNameResolver()
    if bcdata_resolver.available:
        print(f"  BCData resolver: {bcdata_resolver.version_dir.name} ({len(bcdata_resolver.by_id)} IDs indexed)")
    else:
        print("  BCData resolver: not available (manual overrides only)")

    # 4. Build events from sale.tsv (ID-mapped entries)
    ponos_events = []
    for row in sale_rows:
        for pack_id in row["pack_ids"]:
            ev_meta = by_id.get(pack_id)
            if ev_meta:
                nombre = ev_meta["nombre"]
                desc   = ev_meta.get("descripcion", "")
                ponos_events.append(_build_event_entry(
                    nombre, row["start_date"], row["end_date"], desc
                ))
                break  # one entry per row is enough

    print(f"  sale.tsv -> {len(ponos_events)} named events (via event_id mapping)")

    bcdata_events, bcdata_resolved_ids = build_bcdata_events(
        sale_rows, bcdata_resolver, by_name
    )
    print(f"  sale.tsv -> {len(bcdata_events)} named events (via BCData resolver)")

    # 5. Fetch events from Discord channel history (REST, no active bot)
    print("Fetching event schedule from Discord channel history...")
    discord_events = fetch_discord_events(by_name)
    discord_events = filter_relevant_event_entries(
        discord_events,
        max_start_age_days=30,
    )

    known_ponos_ids = set(by_id)
    unknown_report = build_unknown_event_report(
        sale_rows,
        by_id,
        discord_events,
        by_name,
        resolved_ids=bcdata_resolved_ids | known_ponos_ids,
    )
    write_unknown_event_report(unknown_report)
    print(
        f"  Review report: {UNKNOWN_REPORT_FILE.name} "
        f"({unknown_report['summary']['unknown_event_ids']} unmapped IDs, "
        f"{unknown_report['summary']['discord_names_missing_metadata']} names missing metadata)"
    )

    enriched_discord = []
    for ev in discord_events:
        meta = by_name.get(ev["nombre"].lower())
        desc = meta.get("descripcion", "") if meta else ""
        enriched_discord.append(_build_event_entry(
            ev["nombre"], ev["start_date"], ev["end_date"], desc
        ))

    # 6. Merge: ponos_events (dated) takes priority, BCData/Discord fill names
    seen_ids = set()
    all_events = []

    for ev in ponos_events:
        if ev["id"] not in seen_ids:
            seen_ids.add(ev["id"])
            all_events.append(ev)

    for ev in bcdata_events:
        if ev["id"] not in seen_ids:
            seen_ids.add(ev["id"])
            all_events.append(ev)

    for ev in enriched_discord:
        if ev["id"] not in seen_ids:
            seen_ids.add(ev["id"])
            all_events.append(ev)

    all_events.sort(key=lambda x: x["fecha_inicio"])

    # 7. Load existing output, preserve gachas, replace eventos
    existing = {"gachas": [], "eventos": [], "ultima_actualizacion": ""}
    if OUTPUT_FILE.exists():
        try:
            existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Deduplicate old entries against new ones.
    # Check both by ID and by (fecha_inicio, name_overlap) to catch cases where
    # the Discord name is a superset of the old name (e.g. "Heavenly Tower, Infernal Tower"
    # vs old "Heavenly Tower") or where old IDs used a different slug format.
    def _names_overlap(a, b):
        al, bl = a.lower(), b.lower()
        return al == bl or al in bl or bl in al or al[:15] == bl[:15]

    new_names_by_date = {}  # fecha_inicio -> [nombre, ...]
    for ev in bcdata_events + enriched_discord:
        new_names_by_date.setdefault(ev["fecha_inicio"], []).append(ev["nombre"])

    kept_old = []
    for ev in existing.get("eventos", []):
        if ev["id"] in seen_ids:
            continue
        # Drop if a discord entry covers the same day with an overlapping name
        names_same_day = new_names_by_date.get(ev["fecha_inicio"], [])
        if any(_names_overlap(ev["nombre"], dn) for dn in names_same_day):
            continue
        kept_old.append(ev)

    kept_old = filter_relevant_event_entries(
        kept_old,
        max_start_age_days=30,
    )

    final_eventos = sorted(
        filter_relevant_event_entries(all_events + kept_old),
        key=lambda x: x["fecha_inicio"]
    )

    output = {
        "gachas":               existing.get("gachas", []),
        "eventos":              final_eventos,
        "ultima_actualizacion": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\nUpdated {OUTPUT_FILE.name}: {len(final_eventos)} eventos total")

    # 8. Summary
    ponos_ids   = {e["id"] for e in ponos_events}
    bcdata_ids  = {e["id"] for e in bcdata_events}
    discord_ids = {e["id"] for e in enriched_discord}
    print("\nEvent schedule:")
    for ev in final_eventos:
        if ev["id"] in ponos_ids:
            src = "(ponos)"
        elif ev["id"] in bcdata_ids:
            src = "(bcdata)"
        elif ev["id"] in discord_ids:
            src = "(disc) "
        else:
            src = "(old)  "
        line = f"  {ev['fecha_inicio']} -> {ev['fecha_fin']}  {src}  {ev['nombre']}"
        print(line.encode("ascii", errors="replace").decode("ascii"))

    # 9. Diagnostic: show raw sale.tsv header lines for format inspection
    if sale_content:
        lines = [l for l in sale_content.splitlines() if l.strip()]
        print(f"\n--- sale.tsv first 5 lines (raw) ---")
        for line in lines[:5]:
            cols = line.split("\t")
            print(f"  cols={len(cols)}  [{cols[0]}]  {cols[:8]}")
        print(f"--- (full dump in {SALE_RAW_FILE.name}) ---")


if __name__ == "__main__":
    main()
