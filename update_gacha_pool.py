#!/usr/bin/env python3
"""
update_gacha_pool.py
Actualiza all_gachas_en.json con pools y rates actuales desde bc.godfat.org.
Elimina la necesidad de copiar texto manualmente y mantener names.txt.

Dependencias: pip install requests beautifulsoup4

Uso:
  # Actualizar un gacha con un event ID (copia la URL de bc.godfat.org):
  python update_gacha_pool.py 2026-04-24_1047

  # Forzar un gacha específico si el autodetect falla:
  python update_gacha_pool.py 2026-04-24_1047 --gacha "The Dynamites"

  # Ver eventos activos del TSV y sus matches en el JSON:
  python update_gacha_pool.py --list

  # Actualizar todos los gachas activos desde el TSV (modo automático):
  python update_gacha_pool.py --auto

  # Ver qué cambiaría sin escribir nada:
  python update_gacha_pool.py 2026-04-24_1047 --dry-run
"""

import json
import re
import sys
import argparse
import requests
from datetime import datetime

# Fix Unicode en consola Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Falta beautifulsoup4. Instala con: pip install requests beautifulsoup4")
    sys.exit(1)

GODFAT_BASE = "https://bc.godfat.org"
TSV_URL = "https://bc-seek.godfat.org/seek/en/gatya.tsv"
ALL_GACHAS_FILE = "all_gachas_en.json"

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; gacha-updater/1.0)"}


# ---------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------

def fetch_pool_details(event_id: str):
    """
    Descarga la página de detalles de un event ID y extrae:
      - rareChance, supaChance, uberChance, legendChance (int, porcentaje * 100)
      - rares, super_rares, ubers, legends (listas de cat IDs)

    Los IDs de los gatos se sacan del href="/cats/ID" directamente,
    no necesita names.txt.
    """
    url = f"{GODFAT_BASE}/?event={event_id}&details=true&seed=1&count=10"
    print(f"  Fetching: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  ERROR al descargar: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    info_div = soup.find("div", class_="information")

    if not info_div:
        print("  ERROR: No se encontró <div class='information'> — ¿event ID correcto?")
        return None

    rarity_map = [
        ("Rare",   "rares",       "rareChance"),
        ("Super",  "super_rares", "supaChance"),
        ("Uber",   "ubers",       "uberChance"),
        ("Legend", "legends",     "legendChance"),
    ]

    result = {}
    for _, ids_key, chance_key in rarity_map:
        result[ids_key] = []
        result[chance_key] = 0

    for li in info_div.find_all("li"):
        text = li.get_text()
        for prefix, ids_key, chance_key in rarity_map:
            if text.strip().startswith(prefix):
                m = re.search(r"([\d.]+)%", text)
                if m:
                    result[chance_key] = int(round(float(m.group(1)) * 100))
                for a in li.find_all("a", href=True):
                    id_m = re.search(r"/cats/(\d+)", a["href"])
                    if id_m:
                        # godfat usa IDs 1-indexed, el juego usa 0-indexed
                        result[ids_key].append(int(id_m.group(1)) - 1)
                break

    return result


def get_page_gacha_name(event_id: str):
    """
    Obtiene el nombre/descripcion del gacha desde el <select name="event">
    de la página de godfat.
    Formato del option: "2026-05-20 ~ 2026-05-22: Conjurer Dynasaurus Cat joins..."
    Retorna la parte tras el ": " sin el "★..." final.
    """
    url = f"{GODFAT_BASE}/?event={event_id}&details=true&seed=1&count=10"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        soup = BeautifulSoup(resp.text, "html.parser")

        event_select = soup.find("select", {"name": "event"})
        if event_select:
            selected_opt = event_select.find("option", selected=True)
            if not selected_opt:
                # Fallback: buscar option con value == event_id
                selected_opt = event_select.find("option", value=event_id)
            if selected_opt:
                text = selected_opt.get_text(strip=True)
                # Formato: "FECHA ~ FECHA: DESCRIPCION ★info..."
                # Extraer parte tras ":"
                if ": " in text:
                    desc = text.split(": ", 1)[1]
                else:
                    desc = text
                # Quitar parte "★..." al final
                desc = re.split(r"\s*[★\*]", desc)[0].strip()
                return desc if desc else None

    except requests.RequestException:
        pass
    return None


# ---------------------------------------------------------------------------
# TSV
# ---------------------------------------------------------------------------

def parse_tsv_events(only_active: bool = True, include_permanent: bool = False) -> list[dict]:
    """
    Descarga y parsea gatya.tsv.
    Retorna lista de dicts con: event_id, start_date, end_date, name
    Filtra type==1 (rare gacha). Si only_active, solo eventos hoy en rango.
    Si include_permanent, incluye eventos con end_date >= 2028 (platinum, legend capsules...).
    """
    try:
        resp = requests.get(TSV_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"ERROR al descargar TSV: {e}")
        return []

    today = datetime.now().strftime("%Y%m%d")
    events = []
    seen_ids = set()

    for line in resp.text.strip().split("\n"):
        if not line or line.startswith("["):
            continue

        cols = line.split("\t")
        if len(cols) < 25:
            continue

        try:
            start_raw = cols[0].strip()
            end_raw = cols[2].strip()

            if not (start_raw.isdigit() and end_raw.isdigit()):
                continue

            if only_active and not (start_raw <= today <= end_raw):
                continue

            # Ignorar eventos "permanentes" (end_date >= 2028): platinum, legend capsules, etc.
            if not include_permanent and int(end_raw) >= 20280101:
                continue

            # col 8 = type (1 = rare gacha normal)
            col8 = cols[8].strip()
            if not col8.lstrip("-").isdigit() or int(col8) != 1:
                continue

            # col 9 = offset (slot activo, 1-indexed)
            col9 = cols[9].strip()
            if not col9.isdigit():
                continue
            offset = int(col9)

            # Cada slot ocupa 15 columnas desde col 10
            slot_base = 10 + (offset - 1) * 15
            if slot_base + 14 >= len(cols):
                continue

            pool_id_raw = cols[slot_base].strip()
            if not pool_id_raw.lstrip("-").isdigit():
                continue
            pool_id = int(pool_id_raw)

            name = cols[slot_base + 14].strip()

            start_fmt = f"{start_raw[:4]}-{start_raw[4:6]}-{start_raw[6:8]}"
            event_id = f"{start_fmt}_{pool_id}"

            if event_id in seen_ids:
                continue
            seen_ids.add(event_id)

            events.append({
                "event_id": event_id,
                "start_date": start_fmt,
                "end_date": f"{end_raw[:4]}-{end_raw[4:6]}-{end_raw[6:8]}",
                "name": name,
            })

        except (ValueError, IndexError):
            continue

    return events


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def find_gacha_exact(gachas: list, name: str):
    """Búsqueda exacta por nombre o alias (case-insensitive)."""
    nl = name.lower()
    for g in gachas:
        if g["nombre"].lower() == nl:
            return g
        if any(a.lower() == nl for a in g.get("aliases", [])):
            return g
    return None


def find_gacha_fuzzy(gachas: list, name: str):
    """Búsqueda fuzzy por palabras en común."""
    nl = name.lower()
    words = set(re.findall(r"\w+", nl))
    best, best_score = None, 0.0

    for g in gachas:
        candidates = [g["nombre"]] + g.get("aliases", [])
        for candidate in candidates:
            cwords = set(re.findall(r"\w+", candidate.lower()))
            if not words or not cwords:
                continue
            score = len(words & cwords) / len(words | cwords)
            if score > best_score:
                best_score = score
                best = g

    return (best, best_score) if best_score >= 0.3 else (None, 0.0)


# ---------------------------------------------------------------------------
# Aplicar cambios
# ---------------------------------------------------------------------------

def apply_pool(gacha: dict, pool: dict, event_id: str, dry_run: bool) -> bool:
    label = gacha["nombre"]
    r, s, u, l = pool["rareChance"], pool["supaChance"], pool["uberChance"], pool["legendChance"]
    print(f"  {'[DRY RUN] ' if dry_run else ''}→ {label}")
    print(f"    Rates: Rare={r/100}%  Supa={s/100}%  Uber={u/100}%  Legend={l/100}%")
    print(f"    Cats:  {len(pool['rares'])} rares | {len(pool['super_rares'])} super_rares | {len(pool['ubers'])} ubers | {len(pool['legends'])} legends")

    if not dry_run:
        gacha["rareChance"]  = r
        gacha["supaChance"]  = s
        gacha["uberChance"]  = u
        gacha["legendChance"] = l
        gacha["rares"]       = pool["rares"]
        gacha["super_rares"] = pool["super_rares"]
        gacha["ubers"]       = pool["ubers"]
        gacha["legends"]     = pool["legends"]
        return True
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Actualiza all_gachas_en.json desde bc.godfat.org",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("event_id", nargs="?",
                        help="Event ID, p.ej. 2026-04-24_1047")
    parser.add_argument("--gacha", "-g",
                        help="Nombre exacto del gacha a actualizar")
    parser.add_argument("--auto", action="store_true",
                        help="Procesar todos los eventos activos del TSV")
    parser.add_argument("--list", action="store_true",
                        help="Listar eventos activos del TSV sin actualizar")
    parser.add_argument("--all", action="store_true",
                        help="Con --list: incluir también platinum/legend capsules permanentes")
    parser.add_argument("--dry-run", action="store_true",
                        help="Mostrar cambios sin escribir el archivo")
    args = parser.parse_args()

    # Sin flags ni event_id → comportamiento igual a --auto
    if not args.event_id and not args.auto and not args.list:
        args.auto = True

    with open(ALL_GACHAS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    gachas = data["gachas"]

    # ------------------------------------------------------------------ LIST
    if args.list:
        print("Obteniendo eventos activos del TSV...\n")
        events = parse_tsv_events(only_active=True, include_permanent=args.all)
        if not events:
            print("No se encontraron eventos activos (o el TSV no pudo descargarse).")
            return

        print(f"{'EVENT ID':<28} {'DESCRIPCION TSV':<38} {'MATCH EN JSON'}")
        print("-" * 95)
        for ev in events:
            desc = ev["name"].encode("ascii", errors="replace").decode("ascii")
            desc_short = desc[:35] + "..." if len(desc) > 35 else desc

            match = find_gacha_exact(gachas, ev["name"])
            if match:
                match_str = match["nombre"]
            else:
                match, score = find_gacha_fuzzy(gachas, ev["name"])
                match_str = f"{match['nombre']} (~{score:.0%})" if match else "--- sin match"
            print(f"  {ev['event_id']:<26} {desc_short:<38} {match_str}")
        print()
        print("Los gachas con match se pueden actualizar con --auto o: python update_gacha_pool.py EVENT_ID")
        return

    # ------------------------------------------------------------------ AUTO
    if args.auto:
        print("Modo automático: obteniendo eventos activos del TSV...\n")
        events = parse_tsv_events(only_active=True)
        if not events:
            print("Sin eventos (verifica conexión o el TSV).")
            return

        modified = False
        for ev in events:
            print(f"\nEvento: {ev['event_id']}  [{ev['start_date']} → {ev['end_date']}]")
            name = ev["name"] or ""
            if name:
                name_safe = name.encode("ascii", errors="replace").decode("ascii")
                print(f"  Desc TSV: {name_safe[:70]}")

            gacha = find_gacha_exact(gachas, name) if name else None

            if not gacha and name:
                gacha, score = find_gacha_fuzzy(gachas, name)
                if gacha and score >= 0.55:
                    print(f"  Fuzzy match ({score:.0%}): {gacha['nombre']}")
                    if not args.dry_run:
                        resp = input("  ¿Usar este match? [s/N]: ").strip().lower()
                        if resp != "s":
                            print("  Saltando.")
                            gacha = None
                else:
                    gacha = None

            if not gacha:
                # Intentar extraer nombre de la página web (solo si TSV no dio match)
                page_name = get_page_gacha_name(ev["event_id"])
                if page_name:
                    gacha = find_gacha_exact(gachas, page_name)
                    if not gacha:
                        gacha, score = find_gacha_fuzzy(gachas, page_name)
                        if gacha and score >= 0.55:
                            print(f"  Match por página ({score:.0%}): {gacha['nombre']}")
                            if not args.dry_run:
                                resp = input("  ¿Usar este match? [s/N]: ").strip().lower()
                                if resp != "s":
                                    gacha = None
                        else:
                            gacha = None

            if not gacha:
                print(f"  Sin match. Saltando.")
                print(f"  → Para actualizar manualmente: python update_gacha_pool.py {ev['event_id']} --gacha 'Nombre'")
                continue

            pool = fetch_pool_details(ev["event_id"])
            if not pool:
                continue

            if apply_pool(gacha, pool, ev["event_id"], args.dry_run):
                modified = True

        if modified:
            with open(ALL_GACHAS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"\n✓ Guardado: {ALL_GACHAS_FILE}")
        elif not args.dry_run:
            print("\nNada que guardar.")
        return

    # ------------------------------------------------------------------ SINGLE

    event_id = args.event_id
    print(f"\nEvent ID: {event_id}")

    pool = fetch_pool_details(event_id)
    if not pool:
        sys.exit(1)

    # Determinar qué gacha actualizar
    gacha = None

    if args.gacha:
        gacha = find_gacha_exact(gachas, args.gacha)
        if not gacha:
            print(f"ERROR: No se encontró '{args.gacha}' en {ALL_GACHAS_FILE}")
            print("Nombres disponibles:")
            for g in gachas:
                print(f"  - {g['nombre']}")
            sys.exit(1)
    else:
        # Intentar autodetectar desde la página
        page_name = get_page_gacha_name(event_id)
        if page_name:
            print(f"  Nombre detectado en la página: {page_name}")
            gacha = find_gacha_exact(gachas, page_name)
            if not gacha:
                gacha, score = find_gacha_fuzzy(gachas, page_name)
                if gacha:
                    print(f"  Fuzzy match ({score:.0%}): {gacha['nombre']}")
                    resp = input("  ¿Actualizar este? [s/N]: ").strip().lower()
                    if resp != "s":
                        gacha = None

        if not gacha:
            print("\nNo se pudo detectar el gacha automáticamente.")
            print("Gachas disponibles:")
            for i, g in enumerate(gachas, 1):
                print(f"  {i:>2}. {g['nombre']}")
            try:
                choice = int(input("Número (0 = cancelar): "))
                if choice == 0:
                    sys.exit(0)
                gacha = gachas[choice - 1]
            except (ValueError, IndexError):
                print("Selección inválida.")
                sys.exit(1)

    changed = apply_pool(gacha, pool, event_id, args.dry_run)

    if changed:
        with open(ALL_GACHAS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"\n✓ Guardado: {ALL_GACHAS_FILE}")


if __name__ == "__main__":
    main()
