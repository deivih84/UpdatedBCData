import json
import tempfile
import unittest
from pathlib import Path

from workspace_paths import Workspace, drawable_path, latest_version_dir


class WorkspacePathsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='portable workspace ')
        self.addCleanup(self.tmp.cleanup)
        # Windows TEMP can use an 8.3 alias (RUNNER~1); compare canonical paths
        # just as Workspace.load does, including when a parent is a symlink.
        self.root = Path(self.tmp.name).resolve()

    def config(self, value):
        (self.root / 'workspace.local.json').write_text(json.dumps(value), encoding='utf-8')

    def test_relative_paths_are_anchored_to_repo(self):
        self.config({'bcdata': 'sources/game', 'catstats': 'app checkout'})
        ws = Workspace.load(self.root, environ={})
        self.assertEqual(ws.bcdata, self.root / 'sources/game')
        self.assertEqual(ws.app_drawables, self.root / 'app checkout/app/src/main/res/drawable')

    def test_cli_beats_environment_beats_local(self):
        self.config({'bcdata': 'local'})
        ws = Workspace.load(self.root, overrides={'bcdata': 'cli'}, environ={'BCDATA_DIR': 'env'})
        self.assertEqual(ws.bcdata, self.root / 'cli')
        self.assertEqual(Workspace.load(self.root, environ={'BCDATA_DIR': 'env'}).bcdata, self.root / 'env')

    def test_app_is_optional(self):
        ws = Workspace.load(self.root, environ={})
        self.assertIsNone(ws.catstats)
        self.assertIsNone(ws.app_drawables)

    def test_invalid_config_does_not_fall_back(self):
        (self.root / 'workspace.local.json').write_text('{invalid', encoding='utf-8')
        with self.assertRaises(ValueError):
            Workspace.load(self.root, environ={})

    def test_unknown_key_is_rejected(self):
        self.config({'catstat': 'typo'})
        with self.assertRaises(ValueError):
            Workspace.load(self.root, environ={})

    def test_explicit_missing_bcdata_is_not_replaced(self):
        self.config({'bcdata': 'missing'})
        ws = Workspace.load(self.root, environ={})
        self.assertEqual(ws.bcdata, self.root / 'missing')
        with self.assertRaises(FileNotFoundError):
            ws.require_bcdata('jp')

    def test_explicit_source_directory_is_validated_before_online_fallback(self):
        self.config({'bcdata': 'missing'})
        ws = Workspace.load(self.root, environ={})
        with self.assertRaises(FileNotFoundError):
            ws.catalog_bcdata()

    def test_online_mode_can_ignore_configured_offline_source(self):
        self.config({'bcdata': 'missing'})
        ws = Workspace.load(self.root, environ={})
        self.assertIsNone(ws.catalog_bcdata(online=True))

    def test_unconfigured_missing_source_allows_online_fallback(self):
        self.assertIsNone(Workspace.load(self.root, environ={}).catalog_bcdata())

    def test_explicit_gacha_source_requires_latest_file(self):
        (self.root / 'game').mkdir()
        self.config({'bcdata': 'game'})
        with self.assertRaises(FileNotFoundError):
            Workspace.load(self.root, environ={}).catalog_bcdata(require_latest=True)

    def test_latest_version_is_semantic_and_region_specific(self):
        for name in ['15.9.0en', '15.10.0en', '16.0.0jp', 'not-a-version']:
            (self.root / name / 'DataLocal').mkdir(parents=True)
        self.assertEqual(latest_version_dir(self.root, 'en').name, '15.10.0en')
        self.assertEqual(latest_version_dir(self.root, 'jp').name, '16.0.0jp')

    def test_prepare_data_preserves_existing_working_edits(self):
        seed = self.root / 'data/inputs'
        seed.mkdir(parents=True)
        (seed / 'combos.csv').write_text('seed', encoding='utf-8')
        ws = Workspace.load(self.root, environ={})
        self.assertFalse(ws.data.exists())
        ws.prepare_data()
        (ws.data / 'combos.csv').write_text('edited', encoding='utf-8')
        ws.prepare_data()
        self.assertEqual((ws.data / 'combos.csv').read_text(), 'edited')

    def test_drawable_config_works_without_windows_gate(self):
        self.assertEqual(drawable_path(self.root, configured='app/drawable', environ={}), self.root / 'app/drawable')
        self.assertEqual(drawable_path(self.root, explicit=Path('chosen'), configured='other', environ={}), self.root / 'chosen')

    def test_child_environment_carries_effective_paths(self):
        ws = Workspace.load(self.root, overrides={'bcdata': 'game', 'data': 'working'}, environ={})
        env = ws.child_environment()
        self.assertEqual(env['BCDATA_DIR'], str(ws.bcdata))
        self.assertEqual(env['UPDATED_BCDATA_WORK_DATA'], str(ws.data))


if __name__ == '__main__':
    unittest.main()
