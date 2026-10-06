import io
import json
import contextlib
from types import SimpleNamespace
from datetime import date
from pathlib import Path
import tempfile
import unittest
from PIL import Image
import requests
from unittest.mock import patch

from bc_schedule_sources import download_schedule
from gacha_sources import load_local_game, BannerSource, parse_godfat_pool
from gacha_catalog_sync import label_key, plan_catalog, plan_images
from test_gacha_sync import banner, event, game
from test_gacha_sources import pool_html


class RegionTests(unittest.TestCase):
    def test_japanese_names_remain_distinct_identity_keys(self):
        self.assertNotEqual(label_key('\u8d85\u30cd\u30b3\u796d'), label_key('\u6975\u30cd\u30b3\u796d'))
        self.assertTrue(label_key('\u8d85\u30cd\u30b3\u796d'))

    def test_jp_variants_use_jp_labels_and_do_not_learn_promotional_headers(self):
        result = plan_catalog({'gachas': [banner()]}, {}, {},
            [event(), event(101,'2026-10-11','2026-10-15')], game(), {'1':'The Dynamites'}, {},
            today=date(2026,10,6), region='jp')
        self.assertIn('The Dynamites (JP #101)', [b['nombre'] for b in result[0]['gachas']])
        self.assertNotIn('New hero added!', result[0]['gachas'][0]['aliases'])

    def test_local_jp_version_cannot_use_en_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'latest.txt').write_text('15.6.0en\n15.7.1jp')
            data=root/'15.7.1jp/DataLocal'; data.mkdir(parents=True)
            (data/'GatyaDataSetR1.csv').write_text('0,-1')
            (data/'unitbuy.csv').write_text(','.join(['0']*13+['4']))
            (data/'GatyaData_Option_SetR.tsv').write_text('GatyaSetID\tseriesID\timgID\n0\t1\t2')
            result=load_local_game(root,region='jp')
            self.assertEqual(result['version'],'15.7.1')
            self.assertEqual(result['pools'][0]['ubers'],[0])

    def test_mirror_download_is_region_scoped(self):
        class Session:
            def get(self,url,timeout):
                self.url=url
                response=requests.Response(); response.status_code=200
                response._content=b'20261005\t1100\t20261030\t0\t150600\t999999\t0\t0\t1'
                return response
        session=Session()
        download_schedule('gatya.tsv',session=session,region='jp')
        self.assertIn('/jp/gatya.tsv',session.url)

    def test_online_pool_must_confirm_jp_language(self):
        with self.assertRaises(ValueError):
            parse_godfat_pool(pool_html(), '2026-10-05_1077', region='jp')
        html='<select name="lang"><option selected value="jp">JP</option></select>'+pool_html()
        self.assertEqual(parse_godfat_pool(html,'2026-10-05_1077',region='jp')['ubers'],[2])

    def test_jp_image_file_does_not_overwrite_en(self):
        buffer=io.BytesIO(); Image.new('RGB',(860,240),'red').save(buffer,format='PNG')
        with tempfile.TemporaryDirectory() as folder:
            catalog={'gachas':[banner()]}
            state={'banners':{'100':{'name':'The Dynamites','start_date':'2026-10-01'}}}
            report={'pending':[],'images':[]}
            outputs=plan_images(catalog,state,{100:{'image_url':'https://image/banner.png'}},
                lambda _:buffer.getvalue(),Path(folder),'https://public/',report,region='jp')
            self.assertTrue(all(p.name.startswith('banner_jp_') for p in outputs))


class RegionalCliTests(unittest.TestCase):
    def test_jp_apply_and_dry_run_never_modify_en_files(self):
        from sync_gacha_catalog import run
        buffer=io.BytesIO(); Image.new('RGB',(860,240),'red').save(buffer,format='PNG')
        class Source:
            session=None
            def __init__(self,region):
                self.region=region
            def metadata(self,gid,option,fallback_image_id=None):
                return {'image_url':'https://image/jp.png'}
            def image(self,url):
                return buffer.getvalue()
        with tempfile.TemporaryDirectory() as folder:
            repo=Path(folder)
            en_files=['all_gachas_en.json','gacha_id_cache.json','gacha_sync_state.json','gacha_sync_report.json']
            for name in en_files:
                (repo/name).write_bytes(b'EN sentinel')
            (repo/'gacha_sync_config_jp.json').write_text(json.dumps({
                'seriesNames':{'1':'The Dynamites'},'publicImageBase':'https://public/'}))
            args=SimpleNamespace(repo=repo,region='jp',bcdata=repo/'BCData',online=False,
                tsv=None,today=date(2026,10,6),app_drawables=None,skip_images=False,dry_run=True)
            before={p.name:p.read_bytes() for p in repo.iterdir()}
            with patch('sync_gacha_catalog.BannerSource',Source), \
                 patch('bc_schedule_sources.download_schedule',return_value=('fixture',{'url':'JP fixture'})), \
                 patch('sync_gacha_catalog.scheduled_events',return_value=[event()]), \
                 patch('sync_gacha_catalog.load_local_game',return_value=game()), \
                 contextlib.redirect_stdout(io.StringIO()):
                run(args)
                self.assertEqual({p.name:p.read_bytes() for p in repo.iterdir()},before)
                args.dry_run=False
                run(args)
            for name in en_files:
                self.assertEqual((repo/name).read_bytes(),b'EN sentinel')
            self.assertTrue((repo/'all_gachas_jp.json').is_file())
            self.assertTrue((repo/'.gacha_sync_run_jp.json').is_file())

    def test_jp_calendar_preserves_events_and_ignores_unverified_ads(self):
        import fetch_bc_schedule as schedule
        with tempfile.TemporaryDirectory() as folder:
            repo=Path(folder)
            (repo/'all_gachas_jp.json').write_text(json.dumps({'gachas':[banner(),banner('Starter')]}))
            (repo/'gacha_id_cache_jp.json').write_text(json.dumps({'100':'The Dynamites','102':'Starter'}))
            path=repo/'gachas_eventos_actualizados_jp1.json'
            path.write_text(json.dumps({'gachas':[],'eventos':[{'nombre':'JP event sentinel'}]}))
            row={'start_date':'2026-10-06','end_date':'2026-10-10','entries':[
                {'gacha_id':100,'tsv_name':'Advertising'},
                {'gacha_id':101,'tsv_name':'Unverified advertising'},
                {'gacha_id':102,'gacha_type':2,'tsv_name':'Conditional first purchase'}]}
            with patch('bc_schedule_sources.download_schedule',return_value=('fixture',{'url':'JP'})), \
                 patch('fetch_bc_schedule.parse_gatya_tsv',return_value=[row]), \
                 contextlib.redirect_stdout(io.StringIO()):
                schedule.main(['--region','jp','--repo',str(repo)])
            result=json.loads(path.read_text())
            self.assertEqual(result['eventos'],[{'nombre':'JP event sentinel'}])
            self.assertEqual([g['nombre'] for g in result['gachas']],['The Dynamites'])


class SharedIdAndUnicodeTests(unittest.TestCase):
    def test_mixed_unicode_calendar_names_do_not_share_an_id(self):
        from fetch_bc_schedule import _snake
        self.assertNotEqual(_snake('\u8d85\u30cd\u30b3\u796d 2026'), _snake('\u6975\u30cd\u30b3\u796d 2026'))

    def test_starter_snapshot_cannot_bypass_normal_pool_download(self):
        from sync_gacha_catalog import run
        with tempfile.TemporaryDirectory() as folder:
            repo=Path(folder)
            saved={'region':'jp','banners':{'100':{'family':'The Dynamites','name':'The Dynamites',
                'pool':game()['pools'][100],'rates':{f:event()[f] for f in
                ('rareChance','supaChance','uberChance','legendChance')},
                'option':{'seriesID':1},'source':'JP pack','gameVersion':'15.7.1'}}}
            for name,data in [('gacha_sync_config_jp.json',{'publicImageBase':'https://public/',
                                 'seriesNames':{'1':'The Dynamites'}}),
                              ('all_gachas_jp.json',{'gachas':[banner()]}),
                              ('gacha_sync_state_jp.json',saved),('gacha_id_cache_jp.json',{'100':'The Dynamites'})]:
                (repo/name).write_text(json.dumps(data),encoding='utf-8')
            args=SimpleNamespace(repo=repo,region='jp',bcdata=None,online=True,tsv=None,
                today=date(2026,10,6),app_drawables=None,skip_images=True,dry_run=True)
            starter=event();starter['gacha_type']=2
            normal=event();normal['gacha_type']=1
            with patch('sync_gacha_catalog.BannerSource') as source, \
                 patch('bc_schedule_sources.download_schedule',return_value=('fixture',{'url':'JP'})), \
                 patch('sync_gacha_catalog.scheduled_events',return_value=[starter,normal]), \
                 contextlib.redirect_stdout(io.StringIO()):
                source.return_value.pool.side_effect=ValueError('wrong normal pool')
                with self.assertRaises(ValueError):run(args)
                source.return_value.pool.assert_called_once()


class JapaneseArtworkPreferenceTests(unittest.TestCase):
    def test_ja_banner_precedes_generic_family_art_and_never_queries_en_file(self):
        class Session:
            headers={}
            def get(self,url,params=None,timeout=None):
                response=requests.Response()
                response.status_code=403 if 'ponos' in url else 200
                if params and params.get('prop')=='imageinfo':
                    self.titles=params['titles']
                    result={'query':{'pages':{
                        '1':{'title':'File:Gatya bnr174.png','imageinfo':[
                            {'url':'https://images/shared.png','width':860,'height':240}]},
                        '2':{'title':'File:Gatya bnr174 ja.png','imageinfo':[
                            {'url':'https://images/japanese.png','width':860,'height':240}]}}}}
                else:result={'query':{'imageusage':[{'title':'Platinum Capsules (Gacha Event)'}]}}
                response._content=json.dumps(result).encode()
                return response
        session=Session()
        metadata=BannerSource(session,region='jp').metadata(1071,{'imgID':970},fallback_image_id=174)
        self.assertEqual(metadata['image_url'],'https://images/japanese.png')
        self.assertNotIn(' en.png',session.titles)
