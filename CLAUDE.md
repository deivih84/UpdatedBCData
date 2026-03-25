# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the bots

```bash
# Bot combinado (gachas + eventos juntos)
python bot_updater1.py

# Bot solo gachas (version refactorizada con aliases)
python bot_updater_gachas.py

# Bot solo eventos
python bot_updater_events.py

# Bot legacy (gachas con plantillas hardcodeadas)
python bot_updater.py
```

Dependencies: `discord.py`, `PyGithub`. Install with:
```bash
pip install discord.py PyGithub
```

No test suite exists in this project.

## Architecture

This repo is a **Battle Cats game data updater**. A Discord bot listens to a specific channel where another bot posts game schedule data, parses it, and pushes structured JSON to GitHub.

### Data flow

1. A source bot posts schedule messages to Discord channel `1445468966989332563`
2. The updater bot detects the region marker (`EN Event Data Found` / `JP Event Data Found`) to set `region_actual`
3. It then parses subsequent messages containing gacha schedules (triggered by `**Gacha**` / `G : Guaranteed`) or event schedules (triggered by `Stage/Event`)
4. Parsed entries are deduplicated against the live GitHub JSON, then appended and pushed

### Static reference data

- `all_gachas_en.json` — master list of gachas with `nombre`, `aliases`, image URLs, drop rates (`rareChance`, `supaChance`, `uberChance`, `legendChance`), and cat ID lists per rarity (`rares`, `super_rares`, `ubers`, `legends`)
- `all_events.json` — master list of events with `nombre`, `imagen_url`, `descripcion`, optional `url`
- `all_gachas_jp.json` — JP equivalent of gachas

### Output (live schedule) files

- `gachas_eventos_actualizados_en.json` / `gachas_eventos_actualizados_jp.json` — used by `bot_updater.py` (legacy)
- `gachas_eventos_actualizados_en1.json` / `gachas_eventos_actualizados_jp1.json` — used by `bot_updater1.py`, `bot_updater_gachas.py`, `bot_updater_events.py` (current)

Each output file has a top-level structure:
```json
{
  "gachas": [ { "id", "nombre", "fecha_inicio", "fecha_fin", "caracteristicas" } ],
  "eventos": [ { "id", "nombre", "caracteristicas", "fecha_inicio", "fecha_fin" } ],
  "ultima_actualizacion": "ISO timestamp"
}
```

IDs are generated as `nombre_snake_case_YYYY-MM-DD` (start date).

### Bot script differences

| Script | Gacha source | Alias support | Gacha detail (imagen_url, gatos_ids) |
|---|---|---|---|
| `bot_updater.py` | Hardcoded `PLANTILLAS_GACHA` dict | No | Yes (legacy) |
| `bot_updater1.py` | `all_gachas_en.json` | No | No |
| `bot_updater_gachas.py` | `all_gachas_en.json` via `aliases` field | Yes | No |
| `bot_updater_events.py` | `all_events.json` | No | N/A |

`bot_updater_gachas.py` is the most up-to-date gacha bot — it resolves aliases to canonical names before generating IDs.

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
