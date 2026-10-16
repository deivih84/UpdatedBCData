import hashlib
import io
import json
from pathlib import Path
import unittest
import zipfile

from cat_animation_sync import build_deterministic_zip, validate_archive
from sync_pc_cats import convert_form
from update_cat_backswings import animation_frames

ROOT = Path(__file__).resolve().parents[1]


class PcCatsTests(unittest.TestCase):
    def source(self):
        animation = [['[maanim]'], [1], [1], [0, 4, -1, 0, 0], [2],
                     [0, 0, 0, 0], [29, 1, 0, 0]]
        return {'imgcut': [['[imgcut]'], [0], ['911_f.png'], [1], [0, 0, 1, 1]],
                'mamodel': [['[mamodel]'], [3], [1], [-1, -1, 0, 0, 0, 0, 0, 0, 1000, 1000, 0, 1000, 0]],
                'maanim': [{'name': name, 'data': animation} for name in ['Walk', 'Idle', 'Attack', 'Knockback']]}

    def test_native_conversion_preserves_tracks_and_normalizes_identity(self):
        from PIL import Image
        image = io.BytesIO()
        Image.new('RGBA', (1, 1)).save(image, format='PNG')
        png = image.getvalue()
        entries = convert_form(100911, 'f', self.source(), png)
        self.assertEqual(7, len(entries))
        self.assertIn(b'100911_f.png', entries['100911_f.imgcut'])
        self.assertEqual(30, animation_frames(entries['100911_f02.maanim']))
        content = build_deterministic_zip(100911, entries)
        self.assertEqual(content, build_deterministic_zip(100911, dict(reversed(list(entries.items())))))
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertTrue(all(name.startswith('100911/f/100911_f') for name in archive.namelist()))

    def test_missing_or_unknown_states_are_rejected(self):
        from PIL import Image
        image = io.BytesIO()
        Image.new('RGBA', (1, 1)).save(image, format='PNG')
        png = image.getvalue()
        source = self.source()
        source['maanim'].pop()
        with self.assertRaisesRegex(ValueError, 'missing animation states'):
            convert_form(100911, 'f', source, png)
        source['maanim'][0]['name'] = 'Unknown'
        with self.assertRaisesRegex(ValueError, 'unexpected/duplicate'):
            convert_form(100911, 'f', source, png)

    def test_public_catalog_archives_and_manifest_agree_for_every_form(self):
        catalog = json.loads((ROOT / 'pc_cats.json').read_text())['pc_catalog']
        manifest = json.loads((ROOT / 'cats_pc/manifest.json').read_text())
        self.assertEqual(17, len(catalog))
        self.assertEqual(35, sum(len(u['forms']) for u in catalog.values()))
        self.assertEqual(set(catalog), set(manifest['archives']))
        for key, unit in catalog.items():
            self.assertEqual(int(key), 100000 + int(unit['info']['source_id']))
            content = (ROOT / 'cats_pc' / (key + '.zip')).read_bytes()
            self.assertEqual(manifest['archives'][key]['sha256'], hashlib.sha256(content).hexdigest())
            self.assertEqual(manifest['archives'][key]['size'], len(content))
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                entries = {Path(n).name: archive.read(n) for n in archive.namelist()}
                result = validate_archive(int(key), entries)
                self.assertFalse(result.errors)
                self.assertEqual(tuple(f['code'] for f in unit['forms']), result.forms)
                for form in unit['forms']:
                    for index in range(4):
                        self.assertIn(f"{key}_{form['code']}{index:02}.maanim", entries)
        # Explicitly retain source omissions instead of borrowing another form.
        self.assertTrue(any('100911/f' in w for w in manifest['warnings']))
        self.assertIsNone(catalog['100914']['forms'][0]['backswing'])
        mobile = json.loads((ROOT / 'cats_data.json').read_text())
        self.assertEqual(catalog, mobile['pc_catalog'])


if __name__ == '__main__':
    unittest.main()
