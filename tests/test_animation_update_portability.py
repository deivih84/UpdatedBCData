from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cat_animation_sources import SourcePackage, find_aapt
from update_cat_animations import SyncConfig, _inspect_requested_sources


class AnimationUpdatePortabilityTests(unittest.TestCase):
    def test_native_sdk_aapt_is_discovered(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / 'build-tools/36.0.0/aapt'
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch.dict('os.environ', {'ANDROID_HOME': directory}, clear=True), patch('shutil.which', return_value=None):
                self.assertEqual(find_aapt(), executable)

    def test_global_sources_are_included_in_semantic_order(self):
        config = SyncConfig(Path('.'), Path('cats'), Path('cats.json'), Path('version.json'), include_regions=('en',))
        sources = {
            'jp': [SourcePackage((15, 7, 1), 'jp', Path('jp.xapk'), None, None)],
            'en': [SourcePackage((15, 7, 0), 'en', Path('en.xapk'), None, None),
                   SourcePackage((15, 6, 1), 'en', Path('older.xapk'), None, None)],
        }
        actual = _inspect_requested_sources(config, None, lambda root, region: sources[region])
        self.assertEqual([source.key for source in actual], [('en', '15.6.1'), ('en', '15.7.0'), ('jp', '15.7.1')])
