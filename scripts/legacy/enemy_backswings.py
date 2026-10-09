# Both direct invocation and python -m work from any current directory.
import os as _workspace_os
import sys as _workspace_sys
from pathlib import Path as _WorkspacePath
if __package__ in (None, ''):
    _workspace_sys.path.insert(0, str(_WorkspacePath(__file__).resolve().parents[2]))
from workspace_paths import Workspace, latest_version_dir, run_generator
paths = Workspace.load(_workspace_os.environ.get('UPDATED_BCDATA_ROOT'))

import requests
from bs4 import BeautifulSoup
import time
import re

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

BASE_URL = "https://battlecats.miraheze.org"

# Prefijos de wiki que NO son páginas de enemigo
SKIP_PREFIXES = (
    "/wiki/Category:", "/wiki/File:", "/wiki/Template:", "/wiki/Help:",
    "/wiki/User:", "/wiki/Talk:", "/wiki/Special:", "/wiki/The_Battle_Cats_Wiki:",
    "/wiki/Wikipedia:", "/wiki/Enemy_Dictionary", "/wiki/Enemy_Release_Order",
    "/wiki/Category:", "/wiki/Main_Page",
)

def get_all_enemy_links():
    """Recorre todas las páginas de Category:Enemy_Units y devuelve los links únicos."""
    print("Escaneando Category:Enemy_Units (con paginación)...")
    links = []
    seen = set()

    next_url = f"{BASE_URL}/wiki/Category:Enemy_Units"

    while next_url:
        try:
            response = requests.get(next_url, headers=HEADERS, timeout=30)
            soup = BeautifulSoup(response.text, 'html.parser')

            # Los links de la categoría están en el div #mw-pages
            mw_pages = soup.find('div', id='mw-pages')
            if mw_pages:
                for a in mw_pages.find_all('a', href=True):
                    href = a['href']
                    if href.startswith('/wiki/') and not any(href.startswith(p) for p in SKIP_PREFIXES):
                        full_url = BASE_URL + href
                        if full_url not in seen:
                            links.append(full_url)
                            seen.add(full_url)

            # Buscar el link "next page"
            next_url = None
            for a in soup.find_all('a', href=True):
                if a.get_text(strip=True) in ('next page', 'next 200'):
                    next_url = BASE_URL + a['href']
                    print(f"  → Siguiente página: {next_url}")
                    break

        except Exception as e:
            print(f"Error obteniendo lista: {e}")
            break

    print(f"Total enemigos encontrados: {len(links)}")
    return links


def analyze_enemy(enemy_url):
    try:
        response = requests.get(enemy_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        title_tag = soup.find('h1', id='firstHeading')
        if not title_tag:
            return None
        # Limpiamos el nombre: "Brollow (Enemy)" → "Brollow"
        enemy_name = re.sub(r'\s*\(.*?\)\s*$', '', title_tag.get_text(strip=True)).strip()

        # TBA completo en data-freq del div .enemy-stats-table
        stats_table = soup.find('div', {'class': 'enemy-stats-table'})
        freq = None

        if stats_table:
            freq = stats_table.get('data-freq')

        if freq is None:
            # Fallback: buscar el div con grid-area val-freq
            freq_div = soup.find('div', style=re.compile(r'grid-area:\s*val-freq'))
            if freq_div:
                match = re.search(r'\d+', freq_div.get_text())
                freq = match.group(0) if match else None

        if freq is None:
            return None

        tba = int(str(freq).strip())
        if tba <= 0:
            return None

        return {"name": enemy_name, "tba": tba}

    except Exception:
        return None


if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description='Historical wiki scraper; prefer the maintained animation-backed updater').parse_args()
    paths.prepare_data()
    links = get_all_enemy_links()
    filename = str(paths.data / 'enemy_backswings.txt')

    open(filename, "w", encoding="utf-8").close()
    print(f"\nProcesando {len(links)} enemigos...\n")

    count = 0
    errors = 0
    for i, link in enumerate(links):
        data = analyze_enemy(link)

        if data:
            count += 1
            with open(filename, "a", encoding="utf-8") as f:
                f.write(f"--- {data['name']} ---\n")
                f.write(f"{data['tba']}\n")
            print(f"[{i+1}/{len(links)}] {data['name']} → {data['tba']}f")
        else:
            errors += 1
            # Solo mostramos errores para no saturar la consola
            if errors <= 20 or (i + 1) % 50 == 0:
                print(f"[{i+1}/{len(links)}] Sin datos: {link}")

        time.sleep(0.05)

    print(f"\nHecho! {count} enemigos guardados, {errors} sin datos de stats.")
    print(f"Archivo: {filename}")
