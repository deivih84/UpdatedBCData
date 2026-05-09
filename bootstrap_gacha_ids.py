#!/usr/bin/env python3
"""
bootstrap_gacha_ids.py
Auto-derives BC internal gacha ID → canonical name mappings by cross-referencing:
  - Git history of gachas_eventos_actualizados_en1.json (has correct names + dates)
  - Current gatya.tsv from Ponos (has BC IDs + dates)

Algorithm:
  For each TSV entry (ID_set, start, end), find Discord entries with same (start, end).
  An ID maps to a name if that name consistently co-occurs with the ID across all windows.
  Uses bipartite set-intersection to disambiguate when multiple IDs share dates.

Writes gacha_id_cache.json with the derived mapping.
Run this once (or after adding new gachas) before using fetch_bc_schedule.py.
"""

import json
import subprocess
import sys
from pathlib import Path
from collections import defaultdict

try:
    import requests
except ImportError:
    sys.exit("Missing dependency: pip install requests")

SCRIPT_DIR  = Path(__file__).parent
CACHE_FILE  = SCRIPT_DIR / "gacha_id_cache.json"
STATE_FILE  = SCRIPT_DIR / ".bc_state.json"
GACHAS_FILE = SCRIPT_DIR / "all_gachas_en.json"

USER_AGENT = "Dalvik/2.1.0 (Linux; U; Android 13; XQ-BC52 Build/61.2.A.0.447)"
GATYA_URL  = "https://nyanko-events.ponosgames.com/battlecatsen_production/gatya.tsv?jwt={token}"

# ---------------------------------------------------------------------------
# Re-use auth from fetch_bc_schedule (DRY via import)
# ---------------------------------------------------------------------------

def _get_jwt() -> str:
    """Get JWT using saved state from fetch_bc_schedule.py."""
    if not STATE_FILE.exists():
        sys.exit("No .bc_state.json found. Run fetch_bc_schedule.py first.")
    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    # If token is fresh enough, reuse it
    import time
    if state.get("jwt_token") and time.time() - state.get("jwt_ts", 0) < 11 * 3600:
        return state["jwt_token"]
    # Otherwise, re-run the main script to refresh
    sys.exit("JWT token expired. Run fetch_bc_schedule.py first to refresh.")

# ---------------------------------------------------------------------------
# TSV parsing (identical to fetch_bc_schedule.py)
# ---------------------------------------------------------------------------

def _bc_date(v: int):
    if v <= 0:
        return None
    y, rest = divmod(v, 10000)
    m, d    = divmod(rest, 100)
    if not (2000 <= y <= 2050 and 1 <= m <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{m:02d}-{d:02d}"


def _extract_gacha_ids(cols):
    ids = []
    try:
        if int(cols[6]) != 0:
            return ids
        section_count = int(cols[7])
        idx = 8
        for _ in range(section_count):
            day_set_count = int(cols[idx]); idx += 1
            idx += day_set_count * 4
            day_count = int(cols[idx]); idx += 1
            idx += day_count
            idx += 1
            time_count = int(cols[idx]); idx += 1
            idx += time_count * 2
        gacha_type     = int(cols[idx]); idx += 1
        category_count = int(cols[idx]); idx += 1
        entry_width    = 17 if gacha_type == 4 else 15
        for _ in range(category_count):
            if idx >= len(cols):
                break
            gacha_id = int(cols[idx])
            if gacha_id not in (-1, 0):
                ids.append(gacha_id)
            idx += entry_width
    except (ValueError, IndexError):
        pass
    return ids


def parse_tsv(content: str):
    """Returns list of (frozenset_of_ids, start_date, end_date)."""
    from datetime import timedelta, datetime
    entries = []
    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        cols = line.split("\t")
        if len(cols) < 8:
            continue
        try:
            start = _bc_date(int(cols[0]))
            end_raw  = int(cols[2])
            end_time = int(cols[3])
            if end_time == 0:
                dt  = datetime.strptime(str(end_raw), "%Y%m%d") - timedelta(days=1)
                end = dt.strftime("%Y-%m-%d")
            else:
                end = _bc_date(end_raw)
            if not start or not end:
                continue
            ids = _extract_gacha_ids(cols)
            entries.append((frozenset(ids), start, end))
        except (ValueError, IndexError):
            continue
    return entries

# ---------------------------------------------------------------------------
# Git history mining
# ---------------------------------------------------------------------------

def get_git_commits(filepath: str, max_commits: int = 50):
    """Return list of commit hashes that touched this file."""
    result = subprocess.run(
        ["git", "log", f"--max-count={max_commits}", "--format=%H", "--", filepath],
        capture_output=True, text=True, cwd=SCRIPT_DIR
    )
    return result.stdout.strip().split("\n")


def get_file_at_commit(filepath: str, commit: str):
    """Return file contents at a specific commit, or None if not available."""
    result = subprocess.run(
        ["git", "show", f"{commit}:{filepath}"],
        capture_output=True, text=True, cwd=SCRIPT_DIR
    )
    if result.returncode != 0:
        return None
    return result.stdout


def mine_git_history():
    """
    Mine git history to build: {(start, end): set_of_names}
    These are date ranges → gacha names that were active in that window.
    """
    date_to_names = defaultdict(set)

    commits = get_git_commits("gachas_eventos_actualizados_en1.json", max_commits=100)
    print(f"Found {len(commits)} commits in git history")

    for commit in commits:
        content = get_file_at_commit("gachas_eventos_actualizados_en1.json", commit)
        if not content:
            continue
        try:
            data = json.loads(content)
            for g in data.get("gachas", []):
                key = (g["fecha_inicio"], g["fecha_fin"])
                date_to_names[key].add(g["nombre"])
        except (json.JSONDecodeError, KeyError):
            continue

    print(f"Found {len(date_to_names)} unique date ranges in history")
    return date_to_names

# ---------------------------------------------------------------------------
# Bipartite matching: IDs ↔ Names
# ---------------------------------------------------------------------------

def derive_mappings(tsv_entries, date_to_names):
    """
    Cross-reference TSV (IDs, date) with Discord history (names, date).
    Uses set intersection across multiple time periods to disambiguate.

    Returns:
      confirmed: {id: name}   — high confidence (consistent across multiple windows)
      candidates: {id: set_of_possible_names}  — ambiguous
    """
    # For each ID: list of name-sets it co-appeared with
    id_to_cosets = defaultdict(list)  # id → [frozenset_of_names_at_same_window, ...]

    for (tsv_ids, start, end) in tsv_entries:
        if not tsv_ids:
            continue
        # Find Discord names for this exact date range
        discord_names = date_to_names.get((start, end), set())
        if not discord_names:
            continue
        for gid in tsv_ids:
            id_to_cosets[gid].append(frozenset(discord_names))

    # For each ID: the name it maps to is in ALL co-sets (intersection)
    confirmed   = {}
    candidates  = {}
    unresolvable = []

    for gid, cosets in id_to_cosets.items():
        if not cosets:
            continue
        # Intersect all name sets → the name that ALWAYS appears with this ID
        intersection = set(cosets[0])
        for s in cosets[1:]:
            intersection &= s

        if len(intersection) == 1:
            confirmed[gid] = list(intersection)[0]
        elif len(intersection) > 1:
            candidates[gid] = intersection
        else:
            unresolvable.append(gid)

    return confirmed, candidates, unresolvable

# ---------------------------------------------------------------------------
# Load canonical names for alias matching
# ---------------------------------------------------------------------------

def load_canonical_names():
    data = json.loads(GACHAS_FILE.read_text(encoding="utf-8"))
    aliases = {}
    for g in data["gachas"]:
        for alias in g.get("aliases", [g["nombre"]]):
            aliases[alias.lower()] = g["nombre"]
    return aliases


def normalize_name(name: str, aliases: dict) -> str:
    return aliases.get(name.lower(), name)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    # 1. Fetch current TSV
    print("Fetching current gatya.tsv...")
    jwt = _get_jwt()
    r = requests.get(GATYA_URL.format(token=jwt),
                     headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    tsv_entries = parse_tsv(r.text)
    print(f"  Parsed {len(tsv_entries)} TSV entries")

    # Unique IDs found in TSV
    all_tsv_ids = set()
    for (ids, _, _) in tsv_entries:
        all_tsv_ids |= ids
    print(f"  Unique gacha IDs in TSV: {sorted(all_tsv_ids)}")

    # 2. Mine git history
    print("\nMining git history...")
    date_to_names = mine_git_history()

    # 3. Derive mappings
    print("\nDeriving ID -> name mappings...")
    canonical = load_canonical_names()

    confirmed, candidates, unresolvable = derive_mappings(tsv_entries, date_to_names)

    # Normalize names
    confirmed = {k: normalize_name(v, canonical) for k, v in confirmed.items()}

    # 4. Load existing cache
    existing_cache = {}
    if CACHE_FILE.exists():
        try:
            existing_cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Merge: existing cache + newly confirmed
    merged = dict(existing_cache)
    for gid, name in confirmed.items():
        merged[str(gid)] = name

    # 5. Save cache
    CACHE_FILE.write_text(
        json.dumps({str(k): v for k, v in sorted(merged.items(), key=lambda x: int(x[0]))},
                   indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\nSaved {len(merged)} mappings to gacha_id_cache.json")

    # 6. Report
    print("\n=== CONFIRMED (auto-derived) ===")
    for gid, name in sorted(confirmed.items()):
        tag = "(already in cache)" if str(gid) in existing_cache else "(new)"
        print(f"  ID {gid:5d} -> {name} {tag}")

    if candidates:
        print("\n=== AMBIGUOUS (multiple possible names) ===")
        for gid, names in sorted(candidates.items()):
            print(f"  ID {gid:5d} -> one of: {sorted(names)}")
            print(f"           Add manually to gacha_id_cache.json: \"{gid}\": \"<name>\"")

    # IDs in TSV with no resolution at all
    unresolved_ids = all_tsv_ids - set(confirmed.keys()) - set(candidates.keys()) - {int(k) for k in merged}
    if unresolved_ids:
        print("\n=== UNKNOWN (no date match in git history) ===")
        for gid in sorted(unresolved_ids):
            # Show what dates this ID appears at in the TSV
            dates = [(s, e) for (ids, s, e) in tsv_entries if gid in ids]
            print(f"  ID {gid:5d} -> appears at dates: {dates}")

    if not candidates and not unresolved_ids:
        print("\nAll IDs resolved! fetch_bc_schedule.py should work fully.")
    else:
        print("\nFor unresolved IDs, manually add to gacha_id_cache.json:")
        print('  { "12345": "Gacha Name Here", ... }')


if __name__ == "__main__":
    main()
