# Agent operating contract

Read [README.md](README.md) for installation and [docs/workspace.md](docs/workspace.md)
for paths. This repository is the official home of the updater tools. Do not
use older copies in Downloads/Automatizacion or generators from the app checkout.
Historical plans are context, not current operating instructions.

## Start here

1. Inspect `git status --short`; preserve unrelated and pre-existing changes.
2. Use Python 3.12 in a local venv with `requirements-lock.txt` installed.
3. Run `python check_project.py` and inspect the relevant task docs.
4. For full game data, run `python check_project.py --game-data` and
   `python update_all.py --dry-run` before writing data.

Paths come from `workspace_paths.py`: CLI > environment > ignored
`workspace.local.json` > defaults. BCData defaults to a sibling checkout when
present, otherwise `workspace/BCData`. CatStats is optional; configure
`catstats` for app export and drawables. Never introduce personal absolute
paths into tracked code/config/docs. Resolve repo files from `__file__`.

## Task routing

| Task | Commands / documentation |
|---|---|
| EN gachas | `python sync_gacha_catalog.py --dry-run`, then sync and `python fetch_bc_schedule.py`; [gacha-sync](docs/gacha-sync.md) |
| JP gachas | Same commands with `--region jp`; [gacha-sync-jp](docs/gacha-sync-jp.md) |
| EN events | `python fetch_bc_events.py`; [event-sync](docs/event-sync.md) |
| Full data update | `python update_all.py`; add `--export-app` for a configured app |
| Repair animations | `python update_all.py --only animations` (includes backswings) |
| Recalculate backswings | `python update_cat_backswings.py`; [cat-backswings](docs/cat-backswings.md) |
| New photos | `python scripts/tools/actualizar_imagenes.py --source PATH --kind cats` or `enemies` |
| Summaries | `python scripts/data/build_update_summary.py --help`; explicit region/version and AI draft review |
| Validate cat CSV coverage | `python scripts/tools/validate_cats_data.py --help` |

Use `--online` for catalogs in GitHub or without extracted local data. Online
commands can write public files and contact PONOS/wiki; use fixtures for tests.
The pipeline never pulls, commits or pushes unless `--push` is explicitly
requested. Do not execute Discord legacy bots or publish as an installation test.

## Mandatory game-update verification

A game-data update is incomplete until animation sync succeeds. Apply every
unrecorded PONOS source in semantic-version order. Packs are incremental:
merge entries and replace byte-different resources only; never replace an
archive wholesale from a partial pack.

`cats/<id>.zip` entries are normalized as `<id>/<form>/<id>_<form>...`, with
forms `f`, `c`, `s`, `u`. `cats/manifest.json` records ZIP SHA-256/byte sizes and
all applied sources. `latestSource.gameVersion` must match the selected
cats-data version unless a region/version exception is documented.

After syncing, run `python update_cat_backswings.py`. It maintains per-form
arrays in `cats_data.json`. Use `--app-data PATH` for an explicit app JSON
copy, or use the pipeline's `--export-app`. Missing/static attack animations
remain `null` with visible warnings. Do not fabricate forms or values.

Before reporting completion, run:

```bash
python update_cat_animations.py --dry-run
python update_cat_backswings.py --dry-run
python -m unittest discover -s tests -p 'test_*.py' -v
```

The final animation dry-run must report **zero changed paths** and the second
backswing dry-run **zero changed units**. Do not suppress declared-form
warnings: source packages can intentionally omit forms, while every stored
form must validate complete. Keep source packages available for future repair.

## Data contracts

- Preserve EN/JP catalogs, caches, state and artwork separately. JP advertising
  sentences never identify capsule families. Preserve distinct scheduled pool
  variants; do not assign pools by fuzzy names.
- Keep weighted pool duplicates, verified rates, curated image overrides and
  previous photos when a download fails. See the sync docs for identity rules.
- Gacha/calendar and event updates preserve the other section of the schedule.
  Current outputs are `gachas_eventos_actualizados_en1.json` and `..._jp1.json`.
- Public JSON locations, `images/*`, `cats/*` and summary paths are client
  interfaces: keep them stable. For new entries see the catalog sync docs;
  do not follow references to missing legacy bot templates.
- Stats CSVs with shorter historical schemas are valid. Preserve existing
  medals, localizations, custom talent rows (105, 107, 258, 259, 261), combos
  and warnings about discrepancies. Do not infer undocumented fields.
- `data/inputs` contains curated seeds. `workspace/data` is local working state;
  the successful pipeline persists selected accumulated inputs to Git-ready
  seeds. See [architecture](docs/architecture.md) for the step graph.
- New cat/enemy photos go to `images/cats/` or `images/enemies/` plus configured
  `CatStats/app/src/main/res/drawable/`. Keep originals and old public URLs.

## Git and secrets

Never stage `.bc_state.json`, `.bc_sale_raw.tsv`, `.gacha_sync_run.json`,
`.gacha_sync_run_jp.json`, `.event_sync_run.json`, private execution reports,
`workspace.local.json`, `workspace/`, virtualenvs, downloaded game APKs or tokens.
Legacy Discord/GitHub credentials are environment variables, never literals.
Existing published APKs and public animation ZIPs are intentional artifacts.

Run `git diff --check` and review both public outputs and changed curated inputs.
The pipeline is fail-fast but not globally transactional: inspect partial
outputs after a failure before retrying/exporting. Keep validation read-only
when the task is a code or portability change.
