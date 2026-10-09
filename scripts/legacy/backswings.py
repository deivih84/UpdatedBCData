# Both direct invocation and python -m work from any current directory.
import os as _workspace_os
import sys as _workspace_sys
from pathlib import Path as _WorkspacePath
if __package__ in (None, ''):
    _workspace_sys.path.insert(0, str(_WorkspacePath(__file__).resolve().parents[2]))
from workspace_paths import Workspace, latest_version_dir, run_generator
paths = Workspace.load(_workspace_os.environ.get('UPDATED_BCDATA_ROOT'))

import cloudscraper
from bs4 import BeautifulSoup
import time
import re

scraper = cloudscraper.create_scraper()

def get_all_cat_links():
    print("🤖 Escaneando el diccionario de Battle Cats...")
    url = "https://battlecats.miraheze.org/wiki/Cat_Dictionary"
    links = []
    try:
        response = scraper.get(url, timeout=30)
        soup = BeautifulSoup(response.text, 'html.parser')
        content = soup.find('div', {'class': 'mw-parser-output'})
        seen = set()
        for a in content.find_all('a', href=True):
            href = a['href']
            if "/wiki/" in href and "(" in href and ":" not in href:
                full_url = "https://battlecats.miraheze.org" + href
                if full_url not in seen:
                    links.append(full_url)
                    seen.add(full_url)
        print(f"✅ Analizando {len(links)} unidades.")
        return links
    except Exception as e:
        raise RuntimeError(f"❌ Error: {e}")
        return []

def analyze_unit(unit_url):
    try:
        response = scraper.get(unit_url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')

        title_tag = soup.find('h1', id='firstHeading')
        unit_name = title_tag.text.split('(')[0].strip() if title_tag else "Desconocido"

        forms_data = []
        has_zero_cd = False

        # Localizamos los divs de Attack CD y Backswing mediante grid-area
        acd_divs = soup.find_all('div', style=re.compile(r'grid-area:\s*valacd'))
        back_divs = soup.find_all('div', style=re.compile(r'grid-area:\s*valback'))

        for acd_div, back_div in zip(acd_divs, back_divs):
            # Extraemos solo el número (sin la 'f') de data-frames
            acd_val = acd_div.get('data-frames') or acd_div.get_text(strip=True).replace('f', '')
            back_val = back_div.get('data-frames') or back_div.get_text(strip=True).replace('f', '')

            if acd_val == "0":
                has_zero_cd = True

            forms_data.append(f"{acd_val},{back_val}")

        return {
            "unit_name": unit_name,
            "forms": forms_data,
            "match_condition": has_zero_cd
        }
    except:
        return None

if __name__ == "__main__":
    import argparse
    argparse.ArgumentParser(description='Historical wiki scraper; prefer the maintained animation-backed updater').parse_args()
    paths.prepare_data()
    links = get_all_cat_links()
    filename = str(paths.data / 'backswings.txt')

    # Limpiamos/creamos el archivo al inicio
    open(filename, "w", encoding="utf-8").close()

    print(f"🚀 Procesando... Resultados en {filename}")

    count = 0
    for i, link in enumerate(links):
        data = analyze_unit(link)

        if data and data['match_condition']:
            count += 1
            # Escribimos el bloque de texto con el formato solicitado
            with open(filename, "a", encoding="utf-8") as f:
                f.write(f"--- {data['unit_name']} ---\n")
                for line in data['forms']:
                    f.write(f"{line}\n")
                # f.write("\n") # Opcional: añade un espacio entre gatos si quieres

            print(f"[{i+1}/{len(links)}] 🔥 {data['unit_name']}")

        # He reducido el sleep a 0.01 para que vuele ⚡
        # Si ves que te da error 429, súbelo un poquito.
        time.sleep(0.01)

    print(f"\n🥳 ¡Hecho! {count} unidades guardadas en 'backswings.txt'.")
