import json
import tempfile
import unittest
from pathlib import Path

from scripts.data.pc_cats import load_pc_source, merge_pc_source
from scripts.tools.validate_cats_data import validate
from test_pc_cats import source_fixture


class PcValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'pc.json'
        self.source.write_text(json.dumps(source_fixture()), encoding='utf-8')
        self.data_local = self.root / 'DataLocal'
        self.data_local.mkdir()
        (self.data_local / 'unit1.csv').write_text('100,3,10,8\n', encoding='utf-8')
        self.names = self.root / 'names.txt'
        self.names.write_text('0\tN\tCat\t\tBeginning\n', encoding='utf-8')
        self.data = merge_pc_source({'metadata': {'version': '15.7.1'}, 'units': {'000': {
            'info': {'rarity': 'N', 'name_basic': 'Cat', 'names_evolved': '', 'obtain_method': 'Beginning'},
            'stats': [[100, 3, 10, 8]]}}}, load_pc_source(self.source))

    def errors(self):
        path = self.root / 'cats.json'
        path.write_text(json.dumps(self.data), encoding='utf-8')
        return validate(path, self.data_local, self.names, '15.7.1', pc_source=self.source)

    def test_curated_pc_catalog_and_mobile_coverage_pass(self):
        self.assertEqual(self.errors(), [])

    def test_forged_platform_cannot_bypass_mobile_validation(self):
        self.data['units']['000']['info'].update(platform='pc', source_id='911')
        self.assertTrue(self.errors())

    def test_edited_pc_catalog_and_wrong_counter_fail(self):
        self.data['pc_catalog']['100911']['info']['name_basic'] = 'Fake'
        self.assertTrue(self.errors())
        self.data['pc_catalog']['100911']['info']['name_basic'] = 'Battle God Odin'
        self.data['metadata']['total_units'] = 100912
        self.assertTrue(self.errors())

    def test_missing_source_fails_read_only(self):
        self.source.unlink()
        self.assertTrue(self.errors())

    def test_real_seed_validates(self):
        seed = Path(__file__).resolve().parents[1] / 'data/inputs/cats_pc.json'
        entries = load_pc_source(seed)['entries']
        self.assertEqual(len(entries), 17)
        devil = next(entry for entry in entries if entry['source_id'] == '901')['forms'][2]
        self.assertEqual(devil['code'], 's')
        self.assertEqual(next(m['value'] for m in devil['measurements'] if m['field'] == 'health'), 25500)
