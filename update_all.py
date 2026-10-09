"""Portable game-data pipeline. No Git network operations occur without --push."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from workspace_paths import ROOT, Workspace

STEPS = {
    'names': 'scripts/data/actualizar_names.py',
    'combos': 'scripts/data/actualizar_combo_data.py',
    'talents': 'scripts/data/actualizar_talentos.py',
    'enemies_csv': 'scripts/data/actualizar_enemies.py',
    'enemies_json': 'scripts/data/build_enemies_json.py',
    'stages': 'scripts/data/parse_stages.py',
    'cats_info': 'scripts/data/actualizar_cats_info.py',
    'evolution': 'scripts/data/actualizar_evolution_costs.py',
    'animations': 'update_cat_animations.py',
    'backswings': 'update_cat_backswings.py',
}
# Inputs with accumulated/customized state are saved back only after success.
CURATED = {'names': ['names.txt'], 'combos': ['combos.csv', 'combo_names.txt'],
           'talents': ['skill_acquisition.csv'], 'enemies_csv': ['enemy_data.csv']}
PUBLIC = {'cats_info': ['cats_data.json'], 'evolution': ['cats_data.json'],
          'backswings': ['cats_data.json'], 'enemies_json': ['enemies_data.json'],
          'stages': ['stages_data.json'], 'animations': ['cats', 'data_version.json']}


def selected_steps(only=None):
    if not only:
        return list(STEPS)
    unknown = set(only) - set(STEPS)
    if unknown:
        raise ValueError('Unknown pipeline steps: ' + ', '.join(sorted(unknown)))
    wanted = set(only)
    if 'animations' in wanted:
        wanted.add('backswings')
    return [name for name in STEPS if name in wanted]


def should_update_data_version(steps):
    return not steps or any(step not in ('animations', 'backswings') for step in steps)


def preflight(ws, steps, export=False):
    if export and (ws.catstats is None or not ws.app_data.is_dir()):
        raise ValueError('--export-app requires a configured CatStats checkout with app/src/main/assets/data')
    requirements = {
        'names': ('jp', ['DataLocal']),
        'combos': ('en', ['DataLocal/NyancomboData.csv', 'resLocal/Nyancombo_en.csv']),
        'talents': ('jp', ['DataLocal/SkillAcquisition.csv']),
        'enemies_csv': ('jp', ['DataLocal/t_unit.csv']),
        'stages': ('en', ['DataLocal', 'resLocal']),
        'cats_info': ('jp', ['DataLocal']),
        'evolution': ('jp', ['DataLocal/unitbuy.csv']),
        'animations': ('jp', ['DataLocal']),
    }
    for step in steps:
        if not (ws.root / STEPS[step]).is_file():
            raise FileNotFoundError(f'Missing pipeline script: {STEPS[step]}')
        if step in requirements:
            region, files = requirements[step]
            source = ws.require_bcdata(region)
            for name in files:
                if not (source / name).exists():
                    raise FileNotFoundError(f'{step} requires {source / name}')
    if ('evolution' in steps or 'backswings' in steps) and 'cats_info' not in steps:
        if not (ws.root / 'cats_data.json').is_file():
            raise FileNotFoundError('Existing cats_data.json required for evolution/backswings')
    if 'backswings' in steps and 'animations' not in steps:
        if not (ws.root / 'cats/manifest.json').is_file():
            raise FileNotFoundError('Synchronize animations before refreshing backswings')


def step_command(step, ws):
    command = [sys.executable, str(ws.root / STEPS[step])]
    if step == 'animations':
        command.extend(['--bcdata', str(ws.bcdata)])
    return command


def run_step(step, ws):
    print(f'\nRunning {step}', flush=True)
    try:
        result = subprocess.run(step_command(step, ws), cwd=ws.root,
                                env=ws.child_environment(), capture_output=True,
                                text=True, encoding='utf-8', timeout=1800)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    return result.returncode == 0, f'Exit code {result.returncode}'


def copy_changed(source, target):
    source, target = Path(source), Path(target)
    if target.exists() and source.read_bytes() == target.read_bytes():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.tmp')
    shutil.copyfile(source, temporary)
    os.replace(temporary, target)


def save_curated(ws, steps):
    for step in steps:
        for name in CURATED.get(step, []):
            source = ws.data / name
            if source.is_file():
                copy_changed(source, ws.root / 'data/inputs' / name)


def export_app(ws, steps):
    if ws.app_data is None:
        raise ValueError('Configure catstats before exporting to the app')
    names = {name for step in steps for name in PUBLIC.get(step, []) if name.endswith('.json') and name != 'data_version.json'}
    for name in sorted(names):
        copy_changed(ws.root / name, ws.app_data / name)
    for step in steps:
        for name in CURATED.get(step, []):
            copy_changed(ws.data / name, ws.app_data / name)
    if should_update_data_version(steps):
        copy_changed(ws.root / 'data_version.json', ws.app_data / 'data_version.json')


def update_data_version(ws):
    path = ws.root / 'data_version.json'
    existing = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    cats = json.loads((ws.root / 'cats_data.json').read_text(encoding='utf-8'))
    existing['gameVersion'] = cats['metadata']['version']
    existing['lastUpdate'] = datetime.now(timezone.utc).isoformat()
    existing.setdefault('dataFiles', {'cats_data.json': 'cats', 'stages_data.json': 'stages', 'enemies_data.json': 'enemies'})
    path.write_text(json.dumps(existing, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def push_updated_bcdata(ws, steps, summaries=False):
    """Only stage pipeline outputs; preserve unrelated staged/working changes."""
    def git(*args):
        return subprocess.run(['git', *args], cwd=ws.root, check=True, capture_output=True, text=True)
    if git('diff', '--cached', '--name-only').stdout.strip():
        raise ValueError('--push refused: review and commit existing staged changes first')
    names = {name for step in steps for name in PUBLIC.get(step, [])}
    names.update('data/inputs/' + name for step in steps for name in CURATED.get(step, []))
    if should_update_data_version(steps):
        names.add('data_version.json')
    if summaries:
        names.add('update_summaries')
    names = sorted(name for name in names if (ws.root / name).exists())
    if not names:
        return
    git('add', '--', *names)
    if not git('diff', '--cached', '--name-only').stdout.strip():
        return
    git('commit', '-m', 'chore: update game data')
    git('push')


def execute(ws, steps, export=False, push=False, summary_versions=None):
    preflight(ws, steps, export=export)
    ws.prepare_data()
    for step in steps:
        success, message = run_step(step, ws)
        if not success:
            print(f'Pipeline stopped at {step}: {message}', file=sys.stderr)
            return 1
    version_path = ws.root / 'data_version.json'
    previous_version = version_path.read_bytes() if version_path.exists() else None
    try:
        if should_update_data_version(steps):
            update_data_version(ws)
        for region, version in (summary_versions or {}).items():
            command = [sys.executable, str(ws.root / 'scripts/data/build_update_summary.py'),
                       '--updated-bcdata', str(ws.root), '--region', region,
                       '--game-version', version, '--ai-draft', '--publish']
            subprocess.run(command, cwd=ws.root, env=ws.child_environment(), check=True)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        if previous_version is not None:
            version_path.write_bytes(previous_version)
        elif version_path.exists():
            version_path.unlink()
        print(f'Pipeline finalization failed: {exc}', file=sys.stderr)
        return 1
    save_curated(ws, steps)
    if export:
        export_app(ws, steps)
    if push:
        push_updated_bcdata(ws, steps, summaries=bool(summary_versions))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--only', nargs='+', choices=list(STEPS))
    parser.add_argument('--bcdata', type=Path)
    parser.add_argument('--catstats', type=Path)
    parser.add_argument('--work-data', type=Path)
    parser.add_argument('--export-app', action='store_true')
    parser.add_argument('--list', action='store_true', help='List steps without requiring game sources')
    parser.add_argument('--dry-run', action='store_true', help='Validate paths and print commands; does not run generators')
    parser.add_argument('--skip-pull', action='store_true', help='Compatibility flag: this pipeline never pulls BCData automatically')
    parser.add_argument('--push', action='store_true', help='Explicitly commit and push only selected pipeline outputs after success')
    parser.add_argument('--summary', action='store_true')
    parser.add_argument('--summary-en-version')
    parser.add_argument('--summary-jp-version')
    args = parser.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    try:
        steps = selected_steps(args.only)
        if args.list:
            for step in steps:
                print(f'{step:14} {STEPS[step]}')
            return 0
        ws = Workspace.load(overrides={'bcdata': args.bcdata, 'catstats': args.catstats, 'data': args.work_data})
        versions = {r: v for r, v in [('en', args.summary_en_version), ('jp', args.summary_jp_version)] if v}
        if args.summary and not versions:
            raise ValueError('--summary requires an explicit --summary-en-version or --summary-jp-version')
        if versions and not args.summary:
            raise ValueError('Use --summary with summary version arguments')
        if args.dry_run:
            preflight(ws, steps, export=args.export_app)
            for step in steps:
                print(step, step_command(step, ws))
            return 0
        return execute(ws, steps, export=args.export_app, push=args.push, summary_versions=versions)
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
