import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workspace_paths import ROOT, Workspace


class ImportedGeneratorsTests(unittest.TestCase):
    def test_generators_import_without_bcdata_or_app(self):
        names = ['actualizar_cats_info', 'actualizar_combo_data', 'actualizar_talentos',
                 'actualizar_names', 'actualizar_enemies', 'actualizar_evolution_costs',
                 'build_enemies_json', 'parse_stages', 'build_update_summary', 'update_summary_core']
        with tempfile.TemporaryDirectory() as tmp:
            env = dict(os.environ, BCDATA_DIR=str(Path(tmp) / 'missing'),
                       CATSTATS_DIR='', UPDATED_BCDATA_WORK_DATA=str(Path(tmp) / 'working'))
            code = '; '.join('import scripts.data.' + name for name in names)
            result = subprocess.run([sys.executable, '-c', code], cwd=ROOT, env=env,
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse((Path(tmp) / 'working').exists())

    def test_curated_seed_has_all_protected_talent_ids(self):
        import csv
        with (ROOT / 'data/inputs/skill_acquisition.csv').open(encoding='utf-8') as f:
            rows = list(csv.reader(f))
        ids = {int(row[0]) for row in rows[1:] if row and row[0].isdigit()}
        self.assertTrue({105, 107, 258, 259, 261}.issubset(ids))

    def test_cat_generator_reads_latest_semantic_version(self):
        module = importlib.import_module('scripts.data.actualizar_cats_info')
        with tempfile.TemporaryDirectory() as tmp:
            for name in ['15.9.0jp', '15.10.0jp', '16.0.0en', 'junkjp']:
                (Path(tmp) / name / 'DataLocal').mkdir(parents=True)
            with patch.object(module, 'BASE_BCDATA', tmp):
                self.assertEqual(Path(module.buscar_ruta_jp_reciente()).parent.name, '15.10.0jp')

    def test_name_refresh_preserves_existing_localization(self):
        module = importlib.import_module('scripts.data.actualizar_names')
        import json
        with tempfile.TemporaryDirectory() as tmp:
            public = Path(tmp) / 'cats_data.json'
            public.write_text(json.dumps({'units': {'000': {'info': {'name_basic': 'Gato', 'names_evolved': 'Gato Macho / Gato Mohawk'}}}}), encoding='utf-8')
            lines = ['0 \tN \tCat \tMacho Cat / Mohawk Cat \tBeginning', '1 \tN \tNew cat \tN/A \t?']
            result = module.preserve_published_names(lines, public)
            self.assertIn('Gato', result[0])
            self.assertEqual(result[1], lines[1])

    def test_stages_source_selection_is_deferred_until_execution(self):
        module = importlib.import_module('scripts.data.parse_stages')
        with tempfile.TemporaryDirectory() as tmp:
            for name in ['15.9.0en', '15.10.0en', '16.0.0jp']:
                (Path(tmp) / name / 'DataLocal').mkdir(parents=True)
            (Path(tmp) / '15.11.0en').mkdir()
            self.assertEqual(Path(module.find_latest_en_dir(tmp)).name, '15.10.0en')

    def test_working_seed_does_not_need_catstats(self):
        with tempfile.TemporaryDirectory() as tmp:
            ws = Workspace.load(ROOT, overrides={'data': tmp}, environ={})
            ws.prepare_data()
            for name in ['names.txt', 'combos.csv', 'combo_names.txt', 'skill_level.csv', 'skill_acquisition.csv']:
                self.assertTrue((ws.data / name).is_file(), name)


if __name__ == '__main__':
    unittest.main()
