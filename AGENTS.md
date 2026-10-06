# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Running the bots

Automatic EN banner catalogue maintenance (pools, identities and artwork):

```powershell
pip install -r requirements-gacha-sync.txt
python sync_gacha_catalog.py --dry-run
python sync_gacha_catalog.py
python fetch_bc_schedule.py
```

See `docs/gacha-sync.md`. Use `--online` on GitHub; local runs detect sibling
BCData. Preserve distinct scheduled pool variants, do not assign pools by fuzzy
names, and do not stage `.bc_state.json` or `.gacha_sync_run.json`.

```bash
# Fetch gachas directamente de Ponos (sin Discord)
python fetch_bc_schedule.py

# Fetch eventos directamente de Ponos + historial Discord REST (sin bot activo)
python fetch_bc_events.py

# Bot combinado (gachas + eventos juntos) — requiere Discord bot activo
python bot_updater1.py

# Bot solo gachas (version refactorizada con aliases) — requiere Discord bot activo
python bot_updater_gachas.py

# Bot solo eventos — requiere Discord bot activo
python bot_updater_events.py

# Bot legacy (gachas con plantillas hardcodeadas)
python bot_updater.py
```

Dependencies:
```bash
pip install requests discord.py PyGithub
```

`fetch_bc_schedule.py` y `fetch_bc_events.py` solo necesitan `requests`. Los bots Discord necesitan además `discord.py` y `PyGithub`.

Run the repository tests with
`python -m unittest discover -s tests -p "test_*.py" -v`.

## Mandatory cat-animation update

A game-data update is incomplete until `update_cat_animations.py` succeeds.
Run the normal `update_all.py` flow, or use `--only animations` for repair.
PONOS packs are incremental: apply every unrecorded source in semantic-version
order. Never replace an archive from one pack wholesale; merge entries and
replace byte-different files only.

Each `cats/<id>.zip` stores normalized entries as
`<id>/<form>/<id>_<form>...`, where form is `f`, `c`, `s`, or `u`.
`cats/manifest.json` records the SHA-256 and byte size of every ZIP plus all
applied sources. Require `latestSource.gameVersion` to match the selected
game-data version unless a documented region/version exception exists.

Run both checks before reporting completion:

```powershell
python update_cat_animations.py --dry-run
python -m unittest discover -s tests -p "test_*.py" -v
```

The second animation dry-run must report zero pending changes. Do not suppress
declared-form warnings: source packages can intentionally omit forms, while
every form actually stored in a ZIP must still validate as complete.

## Architecture

This repo is a **Battle Cats game data updater**. Actualiza un JSON con el calendario de gachas y eventos del juego, sin necesidad de Discord en los scripts modernos.

### Data flow — scripts modernos (sin Discord activo)

**Gachas** (`fetch_bc_schedule.py`):
1. Crea una cuenta anónima BC en `nyanko-backups.ponosgames.com` (se guarda en `.bc_state.json`)
2. Obtiene JWT token via `nyanko-auth.ponosgames.com`
3. Descarga `gatya.tsv` de `nyanko-events.ponosgames.com/battlecatsen_production/`
4. Parsea el TSV (estructura de secciones + entradas con nombre en posición +14/+16)
5. Escribe la sección `gachas` de `gachas_eventos_actualizados_en1.json`

**Eventos** (`fetch_bc_events.py`):
1. Descarga `sale.tsv` de PONOS con fallback validado al espejo Godfat.
2. Resuelve todos los IDs por catálogo e índice EN de BCData; conserva el snapshot si el remoto está retrasado.
3. Mantiene `all_events.json` y busca carteles EN completos declarados en la wiki.
4. Copia imágenes a `images/events/` y al drawable local configurado; fallos quedan pendientes sin reemplazar fotos previas.
5. Publica catálogo, índice, estado, informe y sección `eventos` del calendario conservando `gachas`.
6. GitHub ejecuta `python fetch_bc_events.py --online` cada seis horas. Ver `docs/event-sync.md`.

El flujo previo de PONOS + historial Discord REST está disponible con `--legacy-discord`.
No stage `.event_sync_run.json`, `.bc_state.json` ni informes privados de ejecución.

### Data flow — bots Discord (legacy, requieren bot activo)

1. A source bot posts schedule messages to Discord channel `1445468966989332563`
2. The updater bot detects the region marker (`EN Event Data Found` / `JP Event Data Found`) to set `region_actual`
3. It then parses subsequent messages containing gacha schedules (triggered by `**Gacha**` / `G : Guaranteed`) or event schedules (triggered by `Stage/Event`)
4. Parsed entries are deduplicated against the live GitHub JSON, then appended and pushed

### Static reference data

- `all_gachas_en.json` — master list of gachas with `nombre`, `aliases`, image URLs, drop rates (`rareChance`, `supaChance`, `uberChance`, `legendChance`), and cat ID lists per rarity (`rares`, `super_rares`, `ubers`, `legends`)
- `all_events.json` — master list of events with `nombre`, `imagen_url`, `descripcion`, optional `url`
- `all_gachas_jp.json` — JP equivalent of gachas

### Image update workflow

Cuando el usuario pida actualizar fotos, copia las imagenes a dos destinos:
- Repo publico para usuarios con versiones antiguas: `C:\Users\forex\Documents\GitHub\UpdatedBCData\images`
  - Unidades: `images\cats\`
  - Enemigos: `images\enemies\`
- App para la proxima actualizacion: `C:\Users\forex\StudioProjects\CatStats\app\src\main\res\drawable\`

### Archivos temporales (gitignored)

- `.bc_state.json` — cuenta BC anónima y JWT token (generado por `fetch_bc_schedule.py` / `fetch_bc_events.py`)
- `.bc_sale_raw.tsv` — dump raw del `sale.tsv` de Ponos (para debugging)

### Output (live schedule) files

- `gachas_eventos_actualizados_en.json` / `gachas_eventos_actualizados_jp.json` — used by `bot_updater.py` (legacy)
- `gachas_eventos_actualizados_en1.json` / `gachas_eventos_actualizados_jp1.json` — used by `fetch_bc_schedule.py`, `fetch_bc_events.py`, `bot_updater1.py`, `bot_updater_gachas.py`, `bot_updater_events.py` (current)

Each output file has a top-level structure:
```json
{
  "gachas": [ { "id", "nombre", "fecha_inicio", "fecha_fin", "caracteristicas" } ],
  "eventos": [ { "id", "nombre", "caracteristicas", "fecha_inicio", "fecha_fin" } ],
  "ultima_actualizacion": "ISO timestamp"
}
```

IDs are generated as `nombre_snake_case_YYYY-MM-DD` (start date).

### Script differences

| Script | Requiere Discord | Fuente gachas | Fuente eventos | Alias support |
|---|---|---|---|---|
| `fetch_bc_schedule.py` | No | Ponos `gatya.tsv` (JWT) | — | Via `all_gachas_en.json` |
| `fetch_bc_events.py` | No (solo REST) | Ponos `sale.tsv` (JWT), fallback Godfat | BCData EN + carteles wiki | Via `all_events.json` |
| `bot_updater.py` | Sí (bot activo) | Hardcoded dict | — | No |
| `bot_updater1.py` | Sí (bot activo) | `all_gachas_en.json` | `all_events.json` | No |
| `bot_updater_gachas.py` | Sí (bot activo) | `all_gachas_en.json` | — | Sí |
| `bot_updater_events.py` | Sí (bot activo) | — | `all_events.json` | No |

`fetch_bc_schedule.py` y `fetch_bc_events.py` son los scripts recomendados — no requieren bot activo en Discord.

### Expandir mapeo de eventos (sale.tsv)

`sale.tsv` contiene pack IDs numéricos sin nombres. Para mapear un ID a un nombre, añade `"event_id": <id>` a la entrada correspondiente en `all_events.json`. El script imprime los IDs detectados al ejecutarse.

### Date parsing logic

`parsear_fecha()` handles three formats:
1. `"2026 January 1st"` — explicit year
2. `"November 28th"` — infers current year (bumps to next year for January in December)
3. Bare day number `"15"` with a `mes_referencia` datetime — infers month relative to the reference date

**Date trimming**: When the same gacha appears multiple times (rotating schedule), consecutive entries are sorted by start date and the end date of each entry is clipped to the start date of the next occurrence to prevent overlaps.

### Adding a new gacha to the master list

Add an entry to `all_gachas_en.json` under `"gachas"` with at minimum:
- `nombre` (canonical name)
- `aliases` (list of names the source bot may use — must include `nombre` itself)
- `imagen_url` pointing to the image in `images/gacha/`
- Drop chance fields and cat ID arrays

To make the legacy `bot_updater.py` recognize it, also add it to `PLANTILLAS_GACHA` in that file.
