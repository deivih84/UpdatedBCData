#!/usr/bin/env python3
"""
fetch_bc_schedule.py
Fetches Battle Cats EN gacha schedule directly from Ponos servers.
No Discord dependency. Updates gachas_eventos_actualizados_en1.json.

Auth flow (reverse-engineered from PackPack bot):
  1. Create anonymous BC account via nyanko-backups
  2. Get password via nyanko-auth
  3. Get JWT token via nyanko-auth
  4. Fetch gatya.tsv via nyanko-events with JWT

Gacha names and characteristics are extracted directly from the TSV — no manual
ID mapping required. The TSV embeds a name string at position +14 (width-15 entry)
or +16 (width-17, Legend Rare entry) within each gacha category block.
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
USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 13; XQ-BC52 Build/61.2.A.0.447)"

ACCOUNT_URL  = "https://nyanko-backups.ponosgames.com/?action=createAccount&referenceId={ref}"
PASSWORD_URL = "https://nyanko-auth.ponosgames.com/v1/users"
JWT_URL      = "https://nyanko-auth.ponosgames.com/v1/tokens"
GATYA_URL    = "https://nyanko-events.ponosgames.com/battlecatsen_production/gatya.tsv?jwt={token}"

SCRIPT_DIR    = Path(__file__).parent
GACHAS_FILE   = SCRIPT_DIR / "all_gachas_en.json"
OUTPUT_FILE   = SCRIPT_DIR / "gachas_eventos_actualizados_en1.json"
STATE_FILE    = SCRIPT_DIR / ".bc_state.json"
ID_CACHE_FILE = SCRIPT_DIR / "gacha_id_cache.json"

# How many days into the past/future to include in output
WINDOW_PAST_DAYS   = 30
WINDOW_FUTURE_DAYS = 180

# Entries with end_date further than this many days are "permanent" capsules — skip them
MAX_END_DAYS = 730  # 2 years

# additionalMask bit flags (from BC source)
# Correspondence: G=Guaranteed | L=Lucky Ticket per roll | S=Step Up
#                 P=Platinum Shard | 5=5 Capsules | GR=Grandon | N=Neneko | R=Reinforcement
MASK_STEP_UP = 4          # S — rolling cost changes per step
MASK_LUCKY   = 4096       # L — each roll costs a Lucky Ticket
MASK_SHARD   = 16384      # P — Platinum Shard pool
MASK_CAPSULE = 32768      # 5 — 5 Capsules per roll

# ---------------------------------------------------------------------------
# Nyanko auth helpers
# ---------------------------------------------------------------------------

def _nyanko_sig(account_code, body):
    """
    Nyanko-Signature header value.
    Format: random64hex + HMAC-SHA256((accountCode+random64hex), body).hexdigest()
    """
    rand = secrets.token_hex(32)          # 64 hex chars
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

# ---------------------------------------------------------------------------
# Account / JWT management
# ---------------------------------------------------------------------------

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
    """Create an anonymous BC account and get password. Returns state dict."""
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
    """Return a valid JWT token, refreshing if needed (tokens last 12h)."""
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
    """Load or create account state and return a valid JWT token."""
    state = _load_state()
    if not state.get("account_code"):
        print("Creating new anonymous BC account...")
        state = _create_account()
        _save_state(state)
    return _get_jwt(state)

# ---------------------------------------------------------------------------
# TSV fetching
# ---------------------------------------------------------------------------

def fetch_gatya_tsv(jwt):
    url = GATYA_URL.format(token=jwt)
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    # Force UTF-8 — Ponos servers serve UTF-8 but requests may autodetect Latin-1
    return r.content.decode("utf-8")

# ---------------------------------------------------------------------------
# TSV parsing  (mirrors GachaSchedule.java + EventDateSet.java logic)
# ---------------------------------------------------------------------------
# gatya.tsv column layout (per line):
#   [0] startDate  YYYYMMDD (int)
#   [1] startTime  HHMM     (int)
#   [2] endDate    YYYYMMDD (int)  — if endTime==0, actual end = endDate - 1 day
#   [3] endTime    HHMM     (int)
#   [4] minVersion
#   [5] maxVersion
#   [6] entryType  0 = normal gacha with sections
#   [7] sectionCount
#   [8+] section data (variable length)
#   ...  gachaType, categoryCount, then categoryCount×(15 or 17) fields
#
# Per-entry layout (width=15, gacha_type != 4):
#   +0  gachaID
#   +1  requiredCatFruit
#   +2  addition
#   +3  additionalMask
#   +4..+8   rarityChances[0..4]    (Normal, Special, Rare, SuperRare, Uber)
#   +9..+13  rarityGuarantees[0..4]
#   +14 name string (may include flavor text after ',' or '★')
#
# Per-entry layout (width=17, gacha_type == 4, Legend banners):
#   +0  gachaID
#   +1  requiredCatFruit
#   +2  addition
#   +3  additionalMask
#   +4..+9   rarityChances[0..5]    (includes Legend rarity)
#   +10..+15 rarityGuarantees[0..5]
#   +16 name string
# ---------------------------------------------------------------------------

def _bc_date(v):
    """Convert YYYYMMDD integer to 'YYYY-MM-DD' string, or None if invalid."""
    if v <= 0:
        return None
    y, rest = divmod(v, 10000)
    m, d    = divmod(rest, 100)
    if not (2000 <= y <= 2050 and 1 <= m <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


def _clean_tsv_name(raw):
    """
    Extract the clean gacha name from a TSV name field.
    TSV names often contain flavor text after ',' or '★', e.g.:
      'The Almighties, supreme beings of Catkind! ★ Tap banner for info!'
    Returns just 'The Almighties'.
    Strips surrounding quotes and whitespace.
    Also returns the full normalized string (before cutting) for alias matching.
    """
    name = raw.strip().strip('"').strip()
    full = name  # Keep full version for alias matching
    # Cut off flavor text at first comma or star
    name = re.split(r'\s*[,★]\s*', name, maxsplit=1)[0].strip()
    return name, full


def _extract_gacha_entries(cols):
    """
    Navigate the variable-length section structure to extract gacha entries.

    Returns list of dicts:
      {
        gacha_id      : int,
        tsv_name      : str,   # clean name from TSV field +14/+16
        is_legend     : bool,  # gacha_type == 4
        guaranteed_uber: bool, # rarityGuarantees[2] > 0
        step_up       : bool,  # additionalMask & MASK_STEP_UP
        lucky_ticket  : bool,  # additionalMask & MASK_LUCKY
      }
    """
    entries = []
    try:
        if int(cols[6]) != 0:           # only handle type-0 entries
            return entries

        section_count = int(cols[7])
        idx = 8

        for _ in range(section_count):
            day_set_count = int(cols[idx]); idx += 1
            idx += day_set_count * 4        # each EventDateSet = 4 ints

            day_count = int(cols[idx]); idx += 1
            idx += day_count                # one int per day

            idx += 1                        # weekday bitmask

            time_count = int(cols[idx]); idx += 1
            idx += time_count * 2           # each EventTimeSection = 2 ints

        gacha_type     = int(cols[idx]); idx += 1
        category_count = int(cols[idx]); idx += 1

        is_legend   = (gacha_type == 4)
        entry_width = 17 if is_legend else 15
        # rarityGuarantees start at +4+n_chances, uber is index 2 within guarantees
        # width=15: 5 chances (+4..+8), guarantees at +9..+13, uber_guarantee at +11
        # width=17: 6 chances (+4..+9), guarantees at +10..+15, uber_guarantee at +12
        uber_guarantee_off = 12 if is_legend else 11
        name_off           = 16 if is_legend else 14

        for _ in range(category_count):
            if idx + entry_width > len(cols):
                break

            gacha_id = int(cols[idx])
            if gacha_id in (-1, 0):
                idx += entry_width
                continue

            additional_mask  = int(cols[idx + 3])
            uber_guarantee   = int(cols[idx + uber_guarantee_off]) if (idx + uber_guarantee_off) < len(cols) else 0
            rare_chance       = int(cols[idx + 6])
            super_chance      = int(cols[idx + 8])
            uber_chance       = int(cols[idx + 10])
            legend_chance     = int(cols[idx + 12])
            raw_name          = cols[idx + name_off] if (idx + name_off) < len(cols) else ""
            tsv_name, tsv_full = _clean_tsv_name(raw_name)

            entries.append({
                "gacha_id":        gacha_id,
                "tsv_name":        tsv_name,
                "tsv_full":        tsv_full,
                "is_legend":       is_legend,
                "guaranteed_uber": uber_guarantee > 0,
                "step_up":         bool(additional_mask & MASK_STEP_UP),
                "lucky_ticket":    bool(additional_mask & MASK_LUCKY),
                "platinum_shard":  bool(additional_mask & MASK_SHARD),
                "capsule_5":       bool(additional_mask & MASK_CAPSULE),
                "rare_chance":     rare_chance,
                "super_chance":    super_chance,
                "uber_chance":     uber_chance,
                "legend_chance":   legend_chance,
            })
            idx += entry_width

    except (ValueError, IndexError):
        pass
    return entries


def parse_gatya_tsv(content):
    """
    Parse gatya.tsv content.
    Returns list of dicts: {start_date, end_date, entries}.
    Only entries within the configured time window are returned.
    Each 'entries' element is a list of gacha entry dicts from _extract_gacha_entries.
    """
    today         = datetime.now(timezone.utc).date()
    cutoff_past   = today - timedelta(days=WINDOW_PAST_DAYS)
    cutoff_future = today + timedelta(days=WINDOW_FUTURE_DAYS)

    rows = []
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

            # Skip entries outside the schedule window (but keep permanent ones)
            is_permanent = (end_d - today).days > MAX_END_DAYS
            if not is_permanent and (end_d < cutoff_past or start_d > cutoff_future):
                continue
            if is_permanent and start_d > today:
                start_date = today.strftime("%Y-%m-%d")

            gacha_entries = _extract_gacha_entries(cols)
            if gacha_entries:
                rows.append({
                    "start_date":   start_date,
                    "end_date":     end_date,
                    "entries":      gacha_entries,
                    "is_permanent": is_permanent,
                })

        except (ValueError, IndexError):
            continue

    return rows

# ---------------------------------------------------------------------------
# Name lookup DBs
# ---------------------------------------------------------------------------

def _load_name_dbs():
    """
    Returns:
      by_id    {int gacha_id -> canonical_name}  — from gacha_id_cache.json + all_gachas_en.json
      alias_db {alias_lower  -> canonical_name}  — from all_gachas_en.json aliases
    """
    alias_db = {}
    by_id    = {}

    if GACHAS_FILE.exists():
        data = json.loads(GACHAS_FILE.read_text(encoding="utf-8"))
        for g in data.get("gachas", []):
            canonical = g["nombre"]
            alias_db[canonical.lower()] = canonical
            for alias in g.get("aliases", []):
                alias_db[alias.lower()] = canonical
            if "gacha_id" in g:
                by_id[int(g["gacha_id"])] = canonical

    # gacha_id_cache.json takes priority over manual entries
    if ID_CACHE_FILE.exists():
        try:
            cache = json.loads(ID_CACHE_FILE.read_text(encoding="utf-8"))
            for id_str, name in cache.items():
                canonical = alias_db.get(name.lower(), name)
                by_id[int(id_str)] = canonical
        except Exception:
            pass

    return by_id, alias_db


FESTIVAL_RATE_SIGNATURES = {
    "Superfest": (2500, 1000, 30),
    "Uberfest": (2600, 900, 30),
    "Epicfest": (2600, 900, 30),
}
SPECIAL_FESTIVAL_TEXT = "special capsules featuring powerful limited units"


def _festival_rate_matches(name, entry):
    """Return whether a festival candidate matches the rates published by Ponos."""
    expected = FESTIVAL_RATE_SIGNATURES.get(name)
    if expected is None:
        return True
    actual = (
        entry.get("super_chance"),
        entry.get("uber_chance"),
        entry.get("legend_chance"),
    )
    return actual == expected


def _resolve_gacha_name(entry, by_id, alias_db):
    """Resolve a canonical name without confusing festivals with different rates."""
    def valid(candidate):
        return candidate if candidate and _festival_rate_matches(candidate, entry) else None

    canonical = valid(by_id.get(entry["gacha_id"]))

    if canonical is None:
        tsv_full = entry.get("tsv_full", "")
        if tsv_full:
            canonical = valid(alias_db.get(tsv_full.lower()))

    if canonical is None:
        tsv_name = entry.get("tsv_name", "")
        if tsv_name:
            canonical = valid(alias_db.get(tsv_name.lower()))

    if canonical is None:
        tsv_full_lower = entry.get("tsv_full", "").lower()
        if tsv_full_lower:
            best_match_len = 0
            for alias_lower, candidate in alias_db.items():
                if len(alias_lower) < 8:
                    continue
                if (tsv_full_lower.startswith(alias_lower)
                        or alias_lower.startswith(tsv_full_lower)
                        or alias_lower in tsv_full_lower
                        or tsv_full_lower in alias_lower):
                    candidate = valid(candidate)
                    if candidate and len(alias_lower) > best_match_len:
                        best_match_len = len(alias_lower)
                        canonical = candidate

    tsv_full_lower = entry.get("tsv_full", "").lower()
    if (canonical is None
            and SPECIAL_FESTIVAL_TEXT in tsv_full_lower
            and _festival_rate_matches("Superfest", entry)):
        canonical = "Superfest"

    if canonical is None:
        canonical = entry.get("tsv_name") or None

    return canonical if canonical and _is_valid_name(canonical) else None


def _is_valid_name(name):
    """Return False if name is empty, too short, garbled, or a sentence fragment."""
    if not name or len(name) < 2:
        return False
    # Reject if more than 30% of chars are non-ASCII (garbled encoding)
    non_ascii = sum(1 for c in name if ord(c) > 127)
    if non_ascii / len(name) >= 0.3:
        return False
    # Reject mid-sentence fragments (start with lowercase = comma-split artifact)
    if name[0].islower():
        return False
    return True

# ---------------------------------------------------------------------------
# Characteristics builder
# ---------------------------------------------------------------------------

def _build_characteristics(entry):
    """
    Return a list of characteristic strings for a gacha entry dict.

    Includes BOTH the legacy single-letter/short codes used by older app versions
    AND human-readable strings used by the current app version.
    Correspondence (old → new):
      G  → Guaranteed          (guaranteed uber on a set roll cycle)
      L  → Lucky Ticket        (each roll costs a Lucky Ticket)
      S  → Step-Up             (rolling cost changes per step)
      P  → Platinum Shard      (Platinum Shard pool)
      5  → 5 Capsules          (5 capsules per roll)
      Legend Rare              (gacha_type == 4, no old letter code)
      GR / N / R               (Grandon/Neneko/Reinforcement — not derivable from TSV bits)
    """
    chars = []
    if entry.get("is_legend"):
        chars.append("Legend Rare")          # no old letter code for this
    if entry.get("guaranteed_uber"):
        chars.extend(["G", "Guaranteed"])
    if entry.get("lucky_ticket"):
        chars.extend(["L", "Lucky Ticket"])
    if entry.get("step_up"):
        chars.extend(["S", "Step-Up"])
    if entry.get("platinum_shard"):
        chars.extend(["P", "Platinum Shard"])
    if entry.get("capsule_5"):
        chars.extend(["5", "5 Capsules"])
    return chars

# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _snake(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _build_entry(name, start, end, characteristics):
    return {
        "id":              f"{_snake(name)}_{start}",
        "nombre":          name,
        "fecha_inicio":    start,
        "fecha_fin":       end,
        "caracteristicas": characteristics,
    }

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # 1. Auth
    print("Getting JWT token...")
    jwt = get_auth_token()

    # 2. Fetch + parse TSV
    print("Fetching gatya.tsv from Ponos servers...")
    tsv  = fetch_gatya_tsv(jwt)
    rows = parse_gatya_tsv(tsv)
    print(f"  Parsed {len(rows)} TSV rows with gacha entries")

    # 3. Load name lookup DBs
    by_id, alias_db = _load_name_dbs()

    # 4. Build gacha list — one output entry per (name, end_date) per TSV row
    #    Each TSV row can have multiple gacha entries (e.g. three Uber Fest banners).
    #    We emit one output record per distinct name per row.
    gachas     = []   # regular (time-limited) banners
    permanents = []   # always-available capsules (Legend/Platinum Caps etc.)

    for row in rows:
        seen_names = set()
        for entry in row["entries"]:
            canonical = _resolve_gacha_name(entry, by_id, alias_db)
            if canonical is None:
                continue

            if canonical in seen_names:
                continue
            seen_names.add(canonical)

            characteristics = _build_characteristics(entry)
            target = permanents if row.get("is_permanent") else gachas
            target.append(_build_entry(canonical, row["start_date"], row["end_date"], characteristics))

    # 5. Sort + deduplicate regular banners
    gachas.sort(key=lambda x: x["fecha_inicio"])

    # Primary dedup: for the same (nombre, fecha_fin), keep only the entry with
    # the earliest fecha_inicio. This collapses TSV sub-period rows (which all share
    # the same end date) into a single canonical entry per banner campaign.
    # Also merge characteristics from all sub-period rows.
    best       = {}   # (nombre, fecha_fin) -> entry
    best_chars = {}   # (nombre, fecha_fin) -> set of characteristic strings

    for g in gachas:
        key = (g["nombre"], g["fecha_fin"])
        chars = set(g["caracteristicas"])
        if key not in best or g["fecha_inicio"] < best[key]["fecha_inicio"]:
            best[key] = g
        best_chars.setdefault(key, set()).update(chars)

    # Apply merged characteristics
    for key, g in best.items():
        g["caracteristicas"] = sorted(best_chars[key])

    # Secondary dedup: drop exact id duplicates
    seen_ids, unique = set(), []
    for g in sorted(best.values(), key=lambda x: x["fecha_inicio"]):
        if g["id"] not in seen_ids:
            seen_ids.add(g["id"])
            unique.append(g)

    # 5b. Deduplicate permanent capsules — one entry per name (pick latest start_date)
    perm_best = {}   # nombre -> entry with latest start_date
    perm_chars = {}  # nombre -> set of chars
    for g in permanents:
        name = g["nombre"]
        chars = set(g["caracteristicas"])
        if name not in perm_best or g["fecha_inicio"] > perm_best[name]["fecha_inicio"]:
            perm_best[name] = g
        perm_chars.setdefault(name, set()).update(chars)

    for name, g in perm_best.items():
        g["caracteristicas"] = sorted(perm_chars[name])

    # Append permanents at end, sorted by name descending (Platinum before Legend)
    for g in sorted(perm_best.values(), key=lambda x: x["nombre"], reverse=True):
        if g["id"] not in seen_ids:
            seen_ids.add(g["id"])
            unique.append(g)

    # 6. Preserve existing eventos section
    existing = {"gachas": [], "eventos": [], "ultima_actualizacion": ""}
    if OUTPUT_FILE.exists():
        try:
            existing = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    output = {
        "gachas":               unique,
        "eventos":              existing.get("eventos", []),
        "ultima_actualizacion": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    OUTPUT_FILE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"Updated {OUTPUT_FILE.name}: {len(unique)} gachas written")

    # 7. Show summary
    print("\nGacha schedule:")
    for g in unique:
        chars = f"  [{', '.join(g['caracteristicas'])}]" if g["caracteristicas"] else ""
        line = f"  {g['fecha_inicio']} -> {g['fecha_fin']}  {g['nombre']}{chars}"
        print(line.encode("ascii", errors="replace").decode("ascii"))


if __name__ == "__main__":
    main()
