import contextlib
from datetime import date
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from event_updater import run, merge_calendar
from event_sources import load_event_index


def occurrence(name, start='2026-10-05', end='2026-10-29'):
    return {'id': name + '_' + start, 'nombre': name, 'fecha_inicio': start,
            'fecha_fin': end, 'caracteristicas': []}


class CalendarMergeTests(unittest.TestCase):
    def test_new_numbered_campaign_supersedes_only_stale_overlapping_calendar(self):
        current = [occurrence('120M Download Celebration!')]
        old = [occurrence('111M Download Celebration!'), occurrence('Heavenly Tower')]
        catalog = {'events': [{'nombre': '120M Download Celebration!', 'event_ids': [24074]},
                             {'nombre': '111M Download Celebration!'}, {'nombre': 'Heavenly Tower'}]}
        result = merge_calendar(current, old, catalog, [], date(2026, 10, 6))
        self.assertEqual({e['nombre'] for e in result}, {'120M Download Celebration!', 'Heavenly Tower'})
        # Two independently scheduled variants remain distinct.
        result = merge_calendar(current + [old[0]], [], catalog, [], date(2026, 10, 6))
        self.assertEqual(len(result), 2)

    def test_conflict_retains_previous_calendar_until_identity_is_resolved(self):
        old = [occurrence('Existing')]
        catalog = {'events': [{'nombre': 'Existing', 'event_ids': [7]}]}
        result = merge_calendar([], old, catalog,
                               [{'reason': 'identity_conflict', 'names': ['Existing', 'Other']}], date(2026, 10, 6))
        self.assertEqual(result, old)


class UpdaterIntegrationTests(unittest.TestCase):
    def fixture(self, directory):
        repo = Path(directory)
        catalog = {'events': [{'nombre': 'Heavenly Tower', 'event_ids': [7000],
                               'imagen_url': 'https://remote/curated.png', 'descripcion': 'Keep me'}]}
        calendar = {'gachas': [{'nombre': 'Rare sentinel'}], 'eventos': [], 'ultima_actualizacion': 'before'}
        for filename, data in [('all_events.json', catalog), ('gachas_eventos_actualizados_en1.json', calendar),
                               ('event_sync_config.json', {'publicImageBase': 'https://public/events/'})]:
            (repo / filename).write_text(json.dumps(data), encoding='utf-8')
        args = SimpleNamespace(repo=repo, dry_run=True, tsv=None, today=date(2026, 10, 6),
                               bcdata=None, online=False, skip_images=True, app_drawables=None)
        index = {'version': '15.6.0', 'source': 'fixture', 'names': {
            '7000': {'name': 'Heavenly Tower', 'source': 'All_day_event', 'calendar': True}}}
        return repo, args, index

    def test_dry_run_creates_no_files_and_apply_preserves_gachas(self):
        with tempfile.TemporaryDirectory() as folder:
            repo, args, index = self.fixture(folder)
            before = {p.name: p.read_bytes() for p in repo.iterdir()}
            tsv = '20261005\t1100\t20261030\t0\t150600\t999999\t0\t0\t1\t7000\t0'
            with patch('event_updater.download_schedule', return_value=(tsv, {'url': 'fixture'})), \
                 patch('event_updater.load_event_index', return_value=(index, [])), \
                 contextlib.redirect_stdout(io.StringIO()):
                run(args)
                self.assertEqual({p.name: p.read_bytes() for p in repo.iterdir()}, before)
                args.dry_run = False
                run(args)
            data = json.loads((repo / 'gachas_eventos_actualizados_en1.json').read_text())
            self.assertEqual(data['gachas'], [{'nombre': 'Rare sentinel'}])
            self.assertEqual(data['eventos'][0]['nombre'], 'Heavenly Tower')

    def test_empty_or_failed_schedule_never_replaces_existing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            repo, args, index = self.fixture(folder)
            before = {p.name: p.read_bytes() for p in repo.iterdir()}
            with patch('event_updater.download_schedule', return_value=('', {'url': 'bad'})), \
                 contextlib.redirect_stdout(io.StringIO()), self.assertRaises(ValueError):
                run(args)
            self.assertEqual({p.name: p.read_bytes() for p in repo.iterdir()}, before)

    def test_cloud_retains_newer_saved_name_index(self):
        class Resolver:
            available = False
        class Session:
            def get(self, url, timeout):
                response = SimpleNamespace(text='14.7.0en\n15.0.0jp')
                response.raise_for_status = lambda: None
                return response
        saved = {'version': '15.6.0', 'source': 'fixture', 'names': {
            '7000': {'name': 'Heavenly Tower', 'source': 'All_day_event', 'calendar': True}}}
        with patch('event_sources.BCEventNameResolver', return_value=Resolver()):
            index, warnings = load_event_index(saved, Session(), online=True)
        self.assertEqual(index, saved)
        self.assertTrue(warnings)

    def test_partial_cloud_refresh_preserves_login_names_at_same_version(self):
        saved = {'version': '15.6.0', 'source': 'fixture', 'names': {
            '35000': {'name': 'Login campaign', 'source': 'DailyLoginEventText', 'calendar': True}}}
        refreshed = {'version': '15.6.0', 'source': 'remote', 'names': {
            '7000': {'name': 'Heavenly Tower', 'source': 'All_day_event', 'calendar': True}}}
        class Resolver:
            available = False
        class Session:
            def get(self, url, timeout):
                response = SimpleNamespace(text='15.6.0en', content=b'fixture')
                response.raise_for_status = lambda: None
                return response
        with patch('event_sources.BCEventNameResolver', return_value=Resolver()), \
             patch('event_sources.index_from_resolver', return_value=refreshed):
            index, warnings = load_event_index(saved, Session(), online=True)
        self.assertEqual(index['names']['35000'], saved['names']['35000'])
        self.assertIn('7000', index['names'])


    def test_configured_original_is_used_without_wiki_and_remains_identical_on_second_run(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            repo, args, index = self.fixture(folder)
            config = {'publicImageBase': 'https://public/events/',
                      'imageOverrides': {'Heavenly Tower': 'curated.png'}}
            (repo / 'event_sync_config.json').write_text(json.dumps(config), encoding='utf-8')
            (repo / 'images/events').mkdir(parents=True)
            stream = io.BytesIO()
            Image.new('RGB', (960, 480), 'red').save(stream, format='PNG')
            original = stream.getvalue()
            (repo / 'images/events/curated.png').write_bytes(original)
            args.app_drawables = repo / 'app'
            args.app_drawables.mkdir()
            args.skip_images = False
            args.dry_run = False
            tsv = '20261005\t1100\t20261030\t0\t150600\t999999\t0\t0\t1\t7000\t0'
            with patch('event_updater.download_schedule', return_value=(tsv, {'url': 'fixture'})), \
                 patch('event_updater.load_event_index', return_value=(index, [])), \
                 patch('event_updater.EventWikiSource.metadata', side_effect=AssertionError('wiki lookup')), \
                 contextlib.redirect_stdout(io.StringIO()):
                run(args)
                first = (repo / 'all_events.json').read_bytes()
                result = run(args)
            self.assertEqual(result['pendingWrites'], [])
            self.assertEqual((repo / 'all_events.json').read_bytes(), first)
            self.assertEqual((repo / 'app/curated.png').read_bytes(), original)
            catalog = json.loads(first)
            self.assertEqual(catalog['events'][0]['imagen_url'], 'https://public/events/curated.png')



if __name__ == '__main__':
    unittest.main()
