import importlib
import tempfile
import unittest
import subprocess
import sys
import os
from pathlib import Path
from PIL import Image
from workspace_paths import ROOT


class ImageToolTests(unittest.TestCase):
    def test_import_has_no_side_effects(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'Mixed Case.txt'
            marker.write_bytes(b'keep original')
            code = '; '.join('import scripts.tools.' + name for name in
                             ['actualizar_imagenes', 'cambiarnombrescompose', 'redimensionarcatunits', 'rename_descriptions'])
            env = dict(os.environ, PYTHONPATH=str(ROOT), PYTHONDONTWRITEBYTECODE='1')
            result = subprocess.run([sys.executable, '-c', code], cwd=tmp, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual([p.name for p in Path(tmp).iterdir()], ['Mixed Case.txt'])
            self.assertEqual(marker.read_bytes(), b'keep original')

    def test_medal_help_never_opens_or_changes_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/tools/update_medals.py'), '--help'],
                                    cwd=tmp, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_image_processing_preserves_source_and_writes_both_destinations(self):
        module = importlib.import_module('scripts.tools.actualizar_imagenes')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            original = source / 'UNI Example.png'
            Image.new('RGBA', (150, 100), 'red').save(original)
            before = original.read_bytes()
            module.process_images(source, root / 'public', root / 'drawable', kind='cats')
            self.assertEqual(original.read_bytes(), before)
            self.assertEqual((root / 'public/uni_example.png').read_bytes(), (root / 'drawable/uni_example.png').read_bytes())
            with Image.open(root / 'public/uni_example.png') as image:
                self.assertEqual(image.size, (110, 85))

    def test_processing_refuses_to_overwrite_an_original(self):
        module = importlib.import_module('scripts.tools.actualizar_imagenes')
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            original = source / 'uni.png'
            Image.new('RGBA', (150, 100), 'red').save(original)
            before = original.read_bytes()
            with self.assertRaises(ValueError):
                module.process_images(source, source)
            self.assertEqual(original.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
