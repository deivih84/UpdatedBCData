import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from workspace_paths import ROOT


class ProjectDiagnosticTests(unittest.TestCase):
    def test_diagnostic_runs_outside_repository_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(ROOT / 'check_project.py'), '--json'],
                                    cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report['root'], str(ROOT))
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_missing_game_data_returns_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(ROOT / 'check_project.py'), '--game-data', '--bcdata', tmp, '--json'],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertTrue(json.loads(result.stdout)['errors'])
