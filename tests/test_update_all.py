import tempfile
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

import update_all
from workspace_paths import ROOT, Workspace


class PipelineTests(unittest.TestCase):
    def test_animation_only_includes_backswings(self):
        self.assertEqual(update_all.selected_steps(['animations']), ['animations', 'backswings'])

    def test_invalid_step_fails(self):
        with self.assertRaises(ValueError):
            update_all.selected_steps(['does-not-exist'])

    def test_order_is_pipeline_order(self):
        self.assertEqual(update_all.selected_steps(['evolution', 'cats_info']), ['cats_info', 'evolution'])

    def test_animation_repair_preserves_timestamp(self):
        self.assertFalse(update_all.should_update_data_version(['animations', 'backswings']))
        self.assertFalse(update_all.should_update_data_version(['backswings']))
        self.assertTrue(update_all.should_update_data_version(['cats_info']))

    def test_failure_prevents_metadata_export_push_and_later_steps(self):
        ws = Workspace.load(ROOT, environ={})
        with patch.object(update_all, 'preflight'), patch.object(ws.__class__, 'prepare_data'), \
             patch.object(update_all, 'run_step', return_value=(False, 'fixture failure')) as run, \
             patch.object(update_all, 'update_data_version') as metadata, \
             patch.object(update_all, 'export_app') as export, \
             patch.object(update_all, 'push_updated_bcdata') as push:
            result = update_all.execute(ws, ['cats_info', 'evolution'], export=True, push=True)
        self.assertEqual(result, 1)
        self.assertEqual(run.call_count, 1)
        metadata.assert_not_called()
        export.assert_not_called()
        push.assert_not_called()

    def test_child_process_uses_same_interpreter_and_effective_paths(self):
        with tempfile.TemporaryDirectory(prefix='workspace with spaces ') as tmp:
            ws = Workspace.load(ROOT, overrides={'data': tmp, 'bcdata': tmp}, environ={})
            with patch.object(update_all.subprocess, 'run') as run:
                run.return_value.returncode = 0
                run.return_value.stdout = ''
                run.return_value.stderr = ''
                self.assertTrue(update_all.run_step('backswings', ws)[0])
            args, kwargs = run.call_args
            self.assertEqual(args[0][0], update_all.sys.executable)
            self.assertEqual(kwargs['env']['UPDATED_BCDATA_WORK_DATA'], str(ws.data))
            self.assertEqual(Path(kwargs['cwd']), ROOT)

    def test_preflight_app_export_requires_app(self):
        ws = Workspace.load(ROOT, environ={'CATSTATS_DIR': ''})
        with self.assertRaises(ValueError):
            update_all.preflight(ws, ['backswings'], export=True)

    def test_export_uses_public_final_cat_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cats_data.json').write_bytes(b'{"fixture":true}')
            (root / 'app/app/src/main/assets/data').mkdir(parents=True)
            ws = Workspace.load(root, overrides={'catstats': 'app'}, environ={})
            update_all.export_app(ws, ['backswings'])
            self.assertEqual((ws.app_data / 'cats_data.json').read_bytes(), b'{"fixture":true}')

    def test_summary_failure_restores_previous_version_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'cats_data.json').write_text('{"metadata":{"version":"2.0.0"}}', encoding='utf-8')
            original = b'{"gameVersion":"1.0.0","lastUpdate":"original"}\n'
            (root / 'data_version.json').write_bytes(original)
            ws = Workspace.load(root, environ={})
            with patch.object(update_all, 'preflight'), patch.object(update_all, 'run_step', return_value=(True, 'OK')), \
                 patch.object(update_all.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'summary')), \
                 patch.object(update_all, 'export_app') as export, patch.object(update_all, 'push_updated_bcdata') as push:
                try:
                    update_all.execute(ws, ['cats_info'], export=True, push=True, summary_versions={'jp': '2.0.0'})
                except subprocess.CalledProcessError:
                    pass
            self.assertEqual((root / 'data_version.json').read_bytes(), original)
            export.assert_not_called()
            push.assert_not_called()


if __name__ == '__main__':
    unittest.main()
