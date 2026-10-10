import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_pc_cats import source_fixture
from workspace_paths import ROOT


class UpdatePcCatsTests(unittest.TestCase):
    def test_command_preserves_mobile_and_second_run_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cats = root / 'cats_data.json'
            mobile = {'000': {'info': {'name_basic': 'Cat'}, 'stats': [[1, 2, 3]], 'backswing': [17]}}
            cats.write_text(json.dumps({'metadata': {'version': '15.7.1', 'total_units': 1}, 'units': mobile}), encoding='utf-8')
            source = root / 'source.json'
            source.write_text(json.dumps(source_fixture()), encoding='utf-8')
            version = root / 'data_version.json'
            version.write_bytes(b'{"gameVersion":"15.7.1","lastUpdate":"old"}\n')
            command = [sys.executable, str(ROOT / 'update_pc_cats.py'), '--cats-data', str(cats), '--source', str(source)]
            preview = subprocess.run(command + ['--dry-run'], capture_output=True, text=True)
            self.assertEqual(preview.returncode, 0, preview.stderr)
            self.assertNotIn('pc_catalog', json.loads(cats.read_text()))
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(cats.read_text())['units'], mobile)
            self.assertNotIn(b'\r', version.read_bytes())
            first = cats.read_bytes()
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Changed files: 0', result.stdout)
            self.assertEqual(cats.read_bytes(), first)
