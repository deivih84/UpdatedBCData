import io
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from event_catalog_sync import plan_events
from event_sources import event_png_bytes, wiki_page_for, declared_banner


def artwork():
    stream = io.BytesIO()
    Image.new('RGB', (960, 480), 'red').save(stream, format='PNG')
    return stream.getvalue()


class EventSyncTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        (self.repo / 'app').mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self, catalog=None, metadata=None, fetch=None):
        return plan_events(catalog or {'events': []}, {},
            [{'start_date': '2026-10-05', 'end_date': '2026-10-29', 'pack_ids': [24074]}],
            {'24074': {'name': '120M Download Celebration!', 'source': 'All_day_event'}},
            metadata if metadata is not None else {'120M Download Celebration!': {
                'url': 'https://wiki/campaign', 'image_url': 'https://wiki/banner.png',
                'description': '120 million downloads worldwide.'}},
            fetch or (lambda _: artwork()), self.repo, 'https://public/events/', drawables=self.repo / 'app')

    def test_new_campaign_gets_image_copied_to_both_destinations(self):
        catalog, _, schedule, outputs, report = self.plan()
        self.assertEqual(catalog['events'][0]['event_ids'], [24074])
        self.assertEqual(schedule[0]['nombre'], '120M Download Celebration!')
        images = [data for path, data in outputs.items() if path.suffix == '.png']
        self.assertEqual(len(images), 2)
        self.assertEqual(images[0], images[1])
        self.assertEqual(report['pending'], [])

    def test_failed_artwork_preserves_curated_fields_and_previous_image(self):
        original = {'events': [{'nombre': '120M Download Celebration!', 'event_ids': [24074],
                    'imagen_url': 'https://public/old.png', 'descripcion': 'Curated description'}]}
        def fail(_):
            raise ValueError('small image')
        catalog, _, schedule, outputs, report = self.plan(original, fetch=fail)
        self.assertEqual(catalog, original)
        self.assertEqual(outputs, {})
        self.assertEqual(schedule[0]['nombre'], original['events'][0]['nombre'])
        self.assertEqual(report['pending'][0]['reason'], 'image_unavailable')

    def test_new_event_without_verified_banner_is_pending_not_invented(self):
        catalog, _, schedule, _, report = self.plan(metadata={})
        self.assertEqual(catalog['events'], [])
        self.assertEqual(schedule, [])
        self.assertEqual(report['pending'][0]['reason'], 'image_not_found')

    def test_identity_conflict_cannot_reassign_an_existing_id(self):
        original = {'events': [{'nombre': 'Other Event', 'event_ids': [24074], 'imagen_url': 'old', 'descripcion': ''},
                               {'nombre': '120M Download Celebration!', 'imagen_url': 'other', 'descripcion': ''}]}
        catalog, _, schedule, _, report = self.plan(original)
        self.assertEqual(catalog, original)
        self.assertEqual(schedule, [])
        self.assertEqual(report['pending'][0]['reason'], 'identity_conflict')

    def test_equal_inputs_and_files_are_noop(self):
        catalog, state, _, outputs, _ = self.plan()
        for path, data in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        again = plan_events(catalog, state,
            [{'start_date': '2026-10-05', 'end_date': '2026-10-29', 'pack_ids': [24074]}],
            {'24074': {'name': '120M Download Celebration!', 'source': 'All_day_event'}},
            {'120M Download Celebration!': {'url': 'https://wiki/campaign', 'image_url': 'https://wiki/banner.png',
                                           'description': '120 million downloads worldwide.'}},
            lambda _: artwork(), self.repo, 'https://public/events/', drawables=self.repo / 'app')
        self.assertEqual(again[0], catalog)
        self.assertEqual(again[1], state)
        self.assertEqual(again[4]['changes'], [])
        self.assertEqual(again[4]['images'], [])

    def test_shared_row_and_unicode_names_keep_all_events_with_unique_ids(self):
        names = ['River City Three-Leg Race \u2460', 'River City Three-Leg Race \u2461']
        catalog = {'events': [{'nombre': name, 'event_ids': [1262 + i], 'imagen_url': 'old', 'descripcion': ''}
                              for i, name in enumerate(names)]}
        result = plan_events(catalog, {}, [{'start_date': '2026-10-05', 'end_date': '2026-10-29',
                                           'pack_ids': [1262, 1263]}], {}, {}, lambda _: None,
                             self.repo, 'https://public/')
        self.assertEqual({e['nombre'] for e in result[2]}, set(names))
        self.assertEqual(len({e['id'] for e in result[2]}), 2)

    def test_selected_original_image_overrides_wiki_and_is_copied_unchanged(self):
        target = self.repo / 'images/events/event_seal.png'
        target.parent.mkdir(parents=True)
        target.write_bytes(artwork())
        catalog = {'events': [{'nombre': 'Baron Seal Strikes', 'event_ids': [24020],
                              'imagen_url': 'https://public/generated.png', 'descripcion': 'Keep'}]}
        def unwanted_download(url):
            self.fail('Selected original image must not download the wiki replacement')
        result = plan_events(catalog, {},
            [{'start_date': '2026-10-05', 'end_date': '2026-10-29', 'pack_ids': [24020]}], {},
            {'Baron Seal Strikes': {'image_url': 'https://wiki/other.png'}}, unwanted_download,
            self.repo, 'https://public/events/', drawables=self.repo / 'app',
            image_overrides={'Baron Seal Strikes': 'event_seal.png'})
        self.assertEqual(result[0]['events'][0]['imagen_url'], 'https://public/events/event_seal.png')
        self.assertEqual(result[3][self.repo / 'app/event_seal.png'], artwork())
        self.assertEqual(result[4]['pending'], [])
        self.assertEqual(result[1]['events']['Baron Seal Strikes']['image']['file'], 'event_seal.png')

    def test_missing_original_image_keeps_previous_photo_without_wiki_fallback(self):
        catalog = {'events': [{'nombre': 'Baron Seal Strikes', 'event_ids': [24020],
                              'imagen_url': 'https://public/current.png', 'descripcion': 'Keep'}]}
        result = plan_events(catalog, {},
            [{'start_date': '2026-10-05', 'end_date': '2026-10-29', 'pack_ids': [24020]}], {},
            {'Baron Seal Strikes': {'image_url': 'https://wiki/other.png'}}, lambda _: self.fail('wiki fallback'),
            self.repo, 'https://public/events/', image_overrides={'Baron Seal Strikes': 'event_seal.png'})
        self.assertEqual(result[0], catalog)
        self.assertEqual(result[4]['pending'][0]['reason'], 'image_unavailable')



class EventArtworkTests(unittest.TestCase):
    def test_only_declared_banner_can_supply_image(self):
        self.assertEqual(declared_banner('{{PageBanner|Eve l 196 1 en.png|event}}'), 'Eve l 196 1 en.png')
        self.assertIsNone(declared_banner('{{PageImage|ITicon.png}} [[File:Random.png]]'))

    def test_campaign_page_mapping_preserves_numbered_identity(self):
        self.assertEqual(wiki_page_for('120M Download Celebration!', {}, {}), 'Million Downloads Event/120 Million')
        self.assertEqual(wiki_page_for('111M Download Celebration!', {}, {}), 'Million Downloads Event/111 Million')

    def test_menu_icons_and_gacha_buttons_are_rejected(self):
        for size in [(225, 54), (254, 196), (860, 240), (960, 960)]:
            with self.subTest(size=size):
                stream = io.BytesIO()
                Image.new('RGB', size, 'red').save(stream, format='PNG')
                with self.assertRaises(ValueError):
                    event_png_bytes(stream.getvalue())
        self.assertEqual(event_png_bytes(event_png_bytes(artwork())), event_png_bytes(artwork()))
