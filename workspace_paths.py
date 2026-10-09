"""Repository-relative workspace configuration. Importing this module never writes files."""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

ROOT = Path(__file__).resolve().parent
ENV_KEYS = {'bcdata': 'BCDATA_DIR', 'catstats': 'CATSTATS_DIR',
            'data': 'UPDATED_BCDATA_WORK_DATA', 'image_inbox': 'UPDATED_BCDATA_IMAGE_INBOX',
            'app_drawables': 'UPDATED_BCDATA_APP_DRAWABLES'}


def resolve_path(root: Path, value) -> Optional[Path]:
    if value is None or value == '':
        return None
    if not isinstance(value, (str, Path)):
        raise ValueError('Workspace paths must be strings or null')
    path = Path(value).expanduser()
    return (path if path.is_absolute() else root / path).resolve()


def latest_version_dir(root: Path, region: str) -> Path:
    if region not in ('en', 'jp', 'kr', 'tw'):
        raise ValueError('Unsupported game-data region: ' + region)
    candidates = []
    for path in Path(root).iterdir() if Path(root).is_dir() else []:
        match = re.fullmatch(r'(\d+)\.(\d+)\.(\d+)' + region, path.name)
        if match and path.is_dir() and (path / 'DataLocal').is_dir():
            candidates.append((tuple(map(int, match.groups())), path))
    if not candidates:
        raise FileNotFoundError(f'No extracted {region.upper()} DataLocal found in {root}; configure BCDATA_DIR or workspace.local.json')
    return max(candidates)[1]


@dataclass(frozen=True)
class Workspace:
    root: Path
    bcdata: Path
    catstats: Optional[Path]
    data: Path
    image_inbox: Path
    app_drawables: Optional[Path]
    bcdata_explicit: bool = False

    @classmethod
    def load(cls, root=None, overrides=None, environ: Optional[Mapping] = None):
        root = Path(root or ROOT).resolve()
        environ = os.environ if environ is None else environ
        config_file = root / 'workspace.local.json'
        config = {}
        if config_file.exists():
            try:
                config = json.loads(config_file.read_text(encoding='utf-8-sig'))
            except (ValueError, OSError) as exc:
                raise ValueError(f'Invalid workspace configuration: {config_file}: {exc}') from exc
            if not isinstance(config, dict) or set(config) - set(ENV_KEYS):
                raise ValueError(f'Unknown workspace configuration keys in {config_file}; allowed: {", ".join(ENV_KEYS)}')
        overrides = overrides or {}
        if set(overrides) - set(ENV_KEYS):
            raise ValueError('Unknown workspace override')
        defaults = {'bcdata': (root.parent / 'BCData' if (root.parent / 'BCData').is_dir() else root / 'workspace/BCData'),
                    'catstats': None, 'data': 'workspace/data', 'image_inbox': 'workspace/images', 'app_drawables': None}
        values = {}
        for key, env_key in ENV_KEYS.items():
            value = overrides.get(key)
            if value is None:
                value = environ.get(env_key, config.get(key, defaults[key]))
            values[key] = resolve_path(root, value)
        for key in ('bcdata', 'data', 'image_inbox'):
            if values[key] is None:
                raise ValueError(f'{key} cannot be empty')
        if values['app_drawables'] is None and values['catstats'] is not None:
            values['app_drawables'] = values['catstats'] / 'app/src/main/res/drawable'
        explicit = overrides.get('bcdata') is not None or 'BCDATA_DIR' in environ or 'bcdata' in config
        return cls(root=root, bcdata_explicit=explicit, **values)

    @property
    def app_data(self):
        return self.catstats / 'app/src/main/assets/data' if self.catstats else None

    def require_bcdata(self, region):
        return latest_version_dir(self.bcdata, region)

    def catalog_bcdata(self, online=False, require_latest=False):
        """Allow automatic online fallback only for absent default sources."""
        if online:
            return None
        if self.bcdata_explicit and not self.bcdata.is_dir():
            raise FileNotFoundError(f'Configured BCData does not exist: {self.bcdata}')
        if self.bcdata_explicit and require_latest and not (self.bcdata / 'latest.txt').is_file():
            raise FileNotFoundError(f'Configured gacha BCData requires {self.bcdata / "latest.txt"}')
        return self.bcdata if self.bcdata.is_dir() else None

    def prepare_data(self):
        """Seed working files once; never overwrite local accumulated edits."""
        seed = self.root / 'data/inputs'
        self.data.mkdir(parents=True, exist_ok=True)
        for source in sorted(seed.rglob('*')) if seed.exists() else []:
            if not source.is_file() or source.name == 'README.md':
                continue
            target = self.data / source.relative_to(seed)
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)

    def child_environment(self):
        env = dict(os.environ)
        env.update({'UPDATED_BCDATA_ROOT': str(self.root), 'PYTHONIOENCODING': 'utf-8',
                    'PYTHONPATH': str(self.root) + os.pathsep + env.get('PYTHONPATH', '')})
        for key, env_key in ENV_KEYS.items():
            value = getattr(self, key)
            env[env_key] = str(value) if value is not None else ''
        return env


def drawable_path(repo=ROOT, explicit=None, configured=None, environ=None):
    if explicit is not None:
        return resolve_path(Path(repo).resolve(), explicit)
    # Retain shared sync-config compatibility; null defers to workspace configuration.
    if configured:
        return resolve_path(Path(repo).resolve(), configured)
    return Workspace.load(repo, environ=environ).app_drawables


def run_generator(function):
    """Common standalone entrypoint; help and imports never seed or generate data."""
    import argparse
    import sys
    parser = argparse.ArgumentParser(description=function.__doc__ or function.__name__)
    parser.parse_args()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    Workspace.load(os.environ.get('UPDATED_BCDATA_ROOT')).prepare_data()
    function()
