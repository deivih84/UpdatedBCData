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

WINDOW_PAST_DAYS   = 30
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
        print(f"  Add 'event_id' fields to all_events.json to map these to event names.")

    return rows

# ---------------------------------------------------------------------------
# Event name DB (all_events.json)
# ---------------------------------------------------------------------------

def load_event_db():
    """
    Returns:
      by_id    {int event_id -> event_dict}
      by_name  {name_lower  -> event_dict}
    """
    by_id   = {}
    by_name = {}
    if EVENTS_FILE.exists():
        data = json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
        for ev in data.get("events", []):
            by_name[ev["nombre"].lower()] = ev
            if "event_id" in ev:
                by_id[int(ev["event_id"])] = ev
    return by_id, by_name

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

    # 5. Fetch events from Discord channel history (REST, no active bot)
    print("Fetching event schedule from Discord channel history...")
    discord_events = fetch_discord_events(by_name)

    enriched_discord = []
    for ev in discord_events:
        meta = by_name.get(ev["nombre"].lower())
        desc = meta.get("descripcion", "") if meta else ""
        enriched_discord.append(_build_event_entry(
            ev["nombre"], ev["start_date"], ev["end_date"], desc
        ))

    # 6. Merge: ponos_events (dated) takes priority, discord fills names
    seen_ids = set()
    all_events = []

    for ev in ponos_events:
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

    disc_by_date = {}  # fecha_inicio -> [nombre, ...]
    for ev in enriched_discord:
        disc_by_date.setdefault(ev["fecha_inicio"], []).append(ev["nombre"])

    kept_old = []
    for ev in existing.get("eventos", []):
        if ev["id"] in seen_ids:
            continue
        # Drop if a discord entry covers the same day with an overlapping name
        disc_names_same_day = disc_by_date.get(ev["fecha_inicio"], [])
        if any(_names_overlap(ev["nombre"], dn) for dn in disc_names_same_day):
            continue
        kept_old.append(ev)

    final_eventos = sorted(
        all_events + kept_old,
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
    discord_ids = {e["id"] for e in enriched_discord}
    print("\nEvent schedule:")
    for ev in final_eventos:
        if ev["id"] in ponos_ids:
            src = "(ponos)"
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
