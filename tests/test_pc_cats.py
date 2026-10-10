import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.data.pc_cats import load_pc_source, merge_pc_source, pc_key


def source_fixture():
    return {'schema_version': 1, 'reviewed_at': '2026-10-09', 'entries': [{
        'source_id': '911', 'status': 'catalog_only',
        'info': {'platform': 'pc', 'source_id': '911', 'source_url': 'https://example.org/odin',
                 'rarity': 'UR', 'name_basic': 'Battle God Odin', 'names_evolved': 'Odin End',
                 'obtain_method': 'PC exclusive'},
        'forms': [{'code': 'f', 'name': 'Battle God Odin', 'measurements': [], 'abilities': []},
                  {'code': 'c', 'name': 'Odin End', 'measurements': [], 'abilities': []}]}]}


class PcCatsTests(unittest.TestCase):
    def load(self, source):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'pc.json'
            path.write_text(json.dumps(source), encoding='utf-8')
            return load_pc_source(path)

    def test_stable_ids_and_invalid_ids(self):
        self.assertEqual(pc_key('911'), '100911')
        for value in ('0911', '-1', '100000', '١', 911):
            with self.subTest(value=value), self.assertRaises(ValueError):
                pc_key(value)

    def test_merge_keeps_mobile_and_no_fake_stats(self):
        data = {'metadata': {'version': '15.7.1'}, 'units': {'911': {'stats': [[123]]}}}
        before = copy.deepcopy(data)
        merged = merge_pc_source(data, self.load(source_fixture()))
        self.assertEqual(data, before)
        self.assertEqual(merged['units'], before['units'])
        self.assertNotIn('stats', merged['pc_catalog']['100911'])
        self.assertEqual(merged['metadata']['total_units'], 1)
        self.assertEqual(merged['metadata']['pc_catalog_units'], 1)
        self.assertEqual(merged, merge_pc_source(merged, self.load(source_fixture())))

    def test_duplicate_source_id_and_wrong_identity_rejected(self):
        source = source_fixture()
        source['entries'].append(copy.deepcopy(source['entries'][0]))
        with self.assertRaises(ValueError):
            self.load(source)
        source = source_fixture()
        source['entries'][0]['info']['source_id'] = '912'
        with self.assertRaises(ValueError):
            self.load(source)

    def test_reserved_mobile_id_is_not_overwritten(self):
        data = {'metadata': {}, 'units': {'100911': {'info': {}, 'stats': [[1]]}}}
        with self.assertRaises(ValueError):
            merge_pc_source(data, self.load(source_fixture()))

    def test_verified_requires_evidence_for_every_column(self):
        source = source_fixture()
        entry = source['entries'][0]
        entry.update(status='verified', stats=[[1, 2], [3, 4]], conversion_evidence=[])
        with self.assertRaises(ValueError):
            self.load(source)

    def test_null_and_zero_measurements_are_preserved(self):
        source = source_fixture()
        measurements = [{'field': 'damage', 'value': value, 'unit': 'damage', 'level': None,
                         'treasures': None, 'source_url': 'https://example.org/odin'}
                        for value in (0, None)]
        source['entries'][0]['forms'][0]['measurements'] = measurements
        loaded = self.load(source)
        self.assertEqual(loaded['entries'][0]['forms'][0]['measurements'], measurements)

    def test_malformed_conversion_form_is_rejected_as_validation_error(self):
        for form in (None, 1, '', 'fc'):
            source = source_fixture()
            source['entries'][0].update(status='verified', stats=[[0] * 52] * 2,
                conversion_evidence=[{'form': form, 'column': 0,
                    'explanation': 'Documented conversion', 'source_url': 'https://example.org/odin'}])
            with self.subTest(form=form), self.assertRaises(ValueError):
                self.load(source)

    def test_complete_evidence_does_not_enable_unsupported_pc_combat(self):
        source = source_fixture()
        source['entries'][0].update(status='verified', stats=[[0] * 52] * 2,
            conversion_evidence=[{'form': form, 'column': column,
                'explanation': 'Documented conversion', 'source_url': 'https://example.org/odin'}
                for form in 'fc' for column in range(52)])
        with self.assertRaisesRegex(ValueError, 'combat.*not supported'):
            self.load(source)

    def test_nonfinite_measurements_and_missing_forms_rejected(self):
        source = source_fixture()
        source['entries'][0]['forms'] = []
        with self.assertRaises(ValueError):
            self.load(source)
        source = source_fixture()
        source['entries'][0]['forms'][0]['measurements'] = [{'field': 'health', 'value': float('nan'),
            'unit': 'HP', 'level': 1, 'treasures': None, 'source_url': 'https://example.org/odin'}]
        with self.assertRaises(ValueError):
            self.load(source)


if __name__ == '__main__':
    unittest.main()
