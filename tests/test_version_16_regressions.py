"""Regression fixtures for source-backed forms, JP additions and attack timing."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch



class VersionUpdateTests(unittest.TestCase):
    def test_ultra_form_name_preserves_three_localized_names_and_is_idempotent(self):
        from scripts.data.actualizar_names import supplement_ultra_form_names
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = ['0'] * 49
            row[26], row[38] = '60', '2000000'
            (root / 'unitbuy.csv').write_text(','.join(row) + '\n')
            (root / 'Unit_Explanation1_ja.csv').write_text('基本,desc\n進化,desc\n真,desc\n究極,desc\n')
            original = ['0\tUR\tLocal base\tLocal evolved / Local true\tCurated unlock']
            actual = supplement_ultra_form_names(original, root, root)
            fields = actual[0].split('\t')
            self.assertEqual(fields[2].strip(), 'Local base')
            self.assertEqual(fields[3].strip(), 'Local evolved / Local true / 究極')
            self.assertEqual(fields[4].strip(), 'Curated unlock')
            self.assertEqual(supplement_ultra_form_names(actual, root, root), actual)

    def test_validator_detects_ultra_truncation_even_with_stale_names(self):
        from scripts.tools.validate_cats_data import validate
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'unit001.csv').write_text('1,2\n3,4\n5,6\n7,8\n')
            row = ['0'] * 49
            row[26], row[38] = '60', '2000000'
            (root / 'unitbuy.csv').write_text(','.join(row) + '\n')
            (root / 'names.txt').write_text('0\tUR\tBase\tEvolved / True\t?\n')
            data = {'metadata': {'version': '16.0.0', 'total_units': 1}, 'units': {'000': {
                'info': {'rarity': 'UR', 'name_basic': 'Base', 'names_evolved': 'Evolved / True', 'obtain_method': '?'},
                'stats': [[1, 2], [3, 4], [5, 6]]}}}
            (root / 'cats.json').write_text(json.dumps(data))
            errors = validate(root / 'cats.json', root, root / 'names.txt', '16.0.0')
            self.assertIn('unit 000 requires at least 4 forms, got 3', errors)

    def test_combo_source_prefers_newer_jp_and_en_at_equal_version(self):
        from scripts.data import actualizar_combo_data as combos
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ['15.9.0en', '15.10.0jp']:
                (root / name / 'DataLocal').mkdir(parents=True)
            with patch.object(combos, 'BASE_GITHUB', tmp):
                self.assertIn('15.10.0jp', combos.buscar_rutas_maestras()[0])
                (root / '15.10.0en/DataLocal').mkdir(parents=True)
                self.assertIn('15.10.0en', combos.buscar_rutas_maestras()[0])

    def test_combo_append_keeps_matching_name_row_and_no_blank_line(self):
        from scripts.data import actualizar_combo_data as combos
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, names = root / 'source.csv', root / 'source_names.txt'
            current, current_names = root / 'current.csv', root / 'names.txt'
            source.write_text('0,1,2\n3069,6,3\n3070,7,4\n')
            names.write_text('Base\nFirst new\nSecond new\n')
            current.write_text('0,1,2\n')
            current_names.write_text('Curated base\n')
            with patch.object(combos, 'buscar_rutas_maestras', return_value=(str(source), str(names))), \
                 patch.object(combos, 'PATH_COMBOS', str(current)), patch.object(combos, 'PATH_NAMES', str(current_names)):
                combos.sincronizar_todo()
                self.assertEqual(current_names.read_text().splitlines(), ['Curated base', 'First new', 'Second new'])
                before = current.read_bytes(), current_names.read_bytes()
                combos.sincronizar_todo()
                self.assertEqual(before, (current.read_bytes(), current_names.read_bytes()))

    def test_missing_combo_name_does_not_partially_append_data(self):
        from scripts.data import actualizar_combo_data as combos
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, names, current, current_names = [root / name for name in ['source', 'source_names', 'current', 'names']]
            source.write_text('0,1\n1,2\n'); names.write_text('Old\n')
            current.write_text('0,1\n'); current_names.write_text('Curated\n')
            with patch.object(combos, 'buscar_rutas_maestras', return_value=(str(source), str(names))), \
                 patch.object(combos, 'PATH_COMBOS', str(current)), patch.object(combos, 'PATH_NAMES', str(current_names)):
                with self.assertRaises(ValueError):
                    combos.sincronizar_todo()
            self.assertEqual(current.read_text(), '0,1\n')
            self.assertEqual(current_names.read_text(), 'Curated\n')

    def test_stage_localization_fallback_preserves_row_and_cell_indices(self):
        from scripts.data import parse_stages as stages
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); en = root / 'en'; jp = root / 'jp'
            en.mkdir(); (jp / 'resLocal').mkdir(parents=True)
            (en / 'StageName_RND_en.csv').write_text('English||＠\n')
            (jp / 'resLocal/StageName_RND_ja.csv').write_text('日本語,補完,＠\n新章,第二,＠\n')
            with patch.object(stages, 'RES_LOCAL', str(en)), patch.object(stages, 'JP_DIR', str(jp)):
                self.assertEqual(stages.load_stage_names_file('StageName_RND_en.csv'),
                                 [['English', '補完'], ['新章', '第二']])

    def test_regional_stage_merge_preserves_en_only_maps_and_same_named_variants(self):
        from scripts.data.parse_stages import merge_regional_stages
        en_sub = {'id': 'collab_1', 'name': 'Same name', 'stages': [{'name': 'Curated EN'}]}
        en = {'chapters': [{'id': 'collab', 'subChapters': [en_sub]}], 'medals': [], 'enemyNames': {'0': 'Doge'}}
        jp = {'chapters': [{'id': 'collab', 'subChapters': [
            {'id': 'collab_1', 'stages': [{'name': 'JP replacement'}]},
            {'id': 'collab_2', 'name': 'Same name', 'stages': []}]}], 'medals': [], 'enemyNames': {'0': 'わんこ', '1': 'New'}}
        output = merge_regional_stages(copy.deepcopy(en), jp)
        self.assertEqual(output['chapters'][0]['subChapters'][0], en_sub)
        self.assertEqual([sub['id'] for sub in output['chapters'][0]['subChapters']], ['collab_1', 'collab_2'])
        self.assertEqual(output['enemyNames'], {'0': 'Doge', '1': 'New'})
        self.assertEqual(merge_regional_stages(copy.deepcopy(output), jp), output)

    def test_colosseum_keeps_same_named_maps_with_distinct_cat_groups(self):
        from scripts.data import parse_stages as stages
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for index in (27, 28):
                (root / f'stageRR{index:03d}_00.csv').write_text('fixture')
            options = {36027: {-1: {-1: {'colosseumGroup': {'groupId': 27}}}},
                       36028: {-1: {-1: {'colosseumGroup': {'groupId': 28}}}}}
            with patch.object(stages, 'DATA_LOCAL', str(root)), \
                 patch.object(stages, 'parse_stage_file', return_value={'enemies': []}), \
                 patch.object(stages, 'parse_map_stage_data', return_value=[]), \
                 patch.object(stages, 'parse_map_bg_id', return_value=9):
                chapter = stages.build_r_chapter('colosseum', 'Colosseum', 36000, 'RR', '', 'R',
                                                {36027: 'Same', 36028: 'Same'}, stage_options=options)
            self.assertEqual([sub['id'] for sub in chapter['subChapters']], ['colosseum_27', 'colosseum_28'])

    def test_enemy_json_uses_verified_id_duration_without_an_english_name(self):
        from scripts.data import build_enemies_json as builder
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            row = ['0'] * 13
            row[0], row[1], row[12] = '100', '1', '3'
            (root / 'enemy_data.csv').write_text('dummy\ndummy\n' + ','.join(row) + '\n')
            (root / 'enemy_attack_animations.json').write_text(json.dumps({'enemies': {'0': {'frames': 41}}}))
            output = root / 'enemies.json'
            with patch.object(builder, 'ASSETS_DIR', str(root)), \
                 patch.object(builder, 'paths', SimpleNamespace(data=root)), \
                 patch.object(builder, 'OUTPUT_APP', str(output)), patch.object(builder, 'OUTPUT_REMOTE', ''):
                builder.main()
            self.assertEqual(json.loads(output.read_text())['enemies'][0]['attackFreq'], 41)

    def test_enemy_duration_uses_last_incremental_source_and_skips_future(self):
        from scripts.data import enemy_attack_animations as sync
        from cat_animation_sources import SourcePackage
        def animation(end):
            return f'[modelanim:animation2]\n2\n1\n0,4,1,0,0,name\n2\n0,0,0,0\n{end},0,0,0\n'.encode()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'bc/16.0.0jp/DataLocal'; source.mkdir(parents=True)
            working = root / 'working'; working.mkdir()
            row = ['0'] * 13; row[12] = '3'
            (source / 't_unit.csv').write_text('\n'.join([','.join(row)] * 3) + '\n')
            sources = [SourcePackage(v, 'jp', root / str(v), None, None) for v in [(15, 7, 1), (16, 0, 0), (17, 0, 0)]]
            ws = SimpleNamespace(bcdata=root / 'bc', data=working)
            with patch.object(sync, 'discover_sources', return_value=sources), \
                 patch.object(sync, 'decrypt_named_resources', side_effect=[{'000_e02.maanim': animation(10)},
                                                                          {'000_e02.maanim': animation(40)}]) as decrypt:
                result = sync.sync_enemy_attack_animations(ws)
            self.assertEqual(result['0']['frames'], 41)
            self.assertEqual(result['0']['sourceVersion'], '16.0.0')
            self.assertEqual(decrypt.call_count, 2)
            self.assertEqual(len(result['0']['sha256']), 64)


if __name__ == '__main__':
    unittest.main()
