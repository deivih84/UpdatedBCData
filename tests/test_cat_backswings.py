import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

import update_cat_backswings as sync


class CatBackswingTests(unittest.TestCase):
    def animation(self, last_frame):
        return f'[modelanim:animation2]\n2\n1\n0,4,1,0,0,name\n2\n0,0,0,0\n{last_frame},0,0,0\n'.encode()

    def stats(self, foreswing=17, second=0, third=0):
        row = [0] * 63
        row[13], row[61], row[62] = foreswing, second, third
        return row

    def test_counts_frame_zero_and_subtracts_final_hit(self):
        self.assertEqual(sync.animation_frames(self.animation(71)), 72)
        self.assertEqual(sync.backswing_frames(self.animation(140), self.stats(60, 65, 70)), 71)

    def test_static_attack_placeholder_is_unavailable(self):
        self.assertIsNone(sync.backswing_frames(self.animation(0), self.stats(100)))

    def test_finite_loops_include_first_frame_offset(self):
        animation = self.animation(11).replace(b'0,4,1,0,0', b'0,4,4,0,0')
        self.assertEqual(sync.backswing_frames(animation, self.stats(6, 17, 28)), 17)
        delayed = animation.replace(b'0,0,0,0', b'3,0,0,0')
        self.assertEqual(sync.animation_frames(delayed), 36)

    def test_archive_ids_are_numeric_even_when_json_keys_are_padded(self):
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(Path(tmp) / '0.zip', 'w') as archive:
                archive.writestr('0/f/0_f02.maanim', self.animation(71))
            data = {'units': {'000': {'stats': [self.stats()]}}}
            self.assertEqual(sync.populate_backswings(data, Path(tmp)), [])
            self.assertEqual(data['units']['000']['backswing'], [55])

    def test_missing_form_is_null_and_never_aliased(self):
        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(Path(tmp) / '877.zip', 'w') as archive:
                archive.writestr('877/f/877_f02.maanim', self.animation(71))
                archive.writestr('877/c/877_c02.maanim', self.animation(170))
            data = {'metadata': {'version': '15.7.1'}, 'units': {'877': {
                'info': {'medals': [{'iconIdx': 66}]},
                'stats': [self.stats(), self.stats(21), self.stats(21)],
                'talents': [1, 2], 'backswing': [999, 999, 999]}}}
            old = copy.deepcopy(data)
            sync.populate_backswings(data, Path(tmp))
            self.assertEqual(data['units']['877']['backswing'], [55, 150, None])
            del data['units']['877']['backswing']
            del old['units']['877']['backswing']
            self.assertEqual(data, old)

    def test_rejects_truncated_animation_and_negative_backswing(self):
        with self.assertRaises(ValueError):
            sync.animation_frames(self.animation(71).rsplit(b'\n', 2)[0])
        with self.assertRaises(ValueError):
            sync.backswing_frames(self.animation(10), self.stats(20))

    def test_rejects_stale_manifest(self):
        with self.assertRaises(ValueError):
            sync.validate_source({'metadata': {'version': '15.7.1'}},
                                 {'latestSource': {'gameVersion': '15.6.0'}})

    def test_new_csv_version_defers_backswing_until_animation_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'manifest.json').write_text(json.dumps({'latestSource': {'gameVersion': '15.6.0'}}))
            with zipfile.ZipFile(root / '877.zip', 'w') as archive:
                archive.writestr('877/f/877_f02.maanim', self.animation(10))
            data = {'metadata': {'version': '15.7.1'}, 'units': {'877': {'stats': [self.stats(100)]}}}
            self.assertEqual(sync.prepare_backswings(data, root), ['877/f'])
            self.assertEqual(data['units']['877']['backswing'], [None])


if __name__ == '__main__':
    unittest.main()
