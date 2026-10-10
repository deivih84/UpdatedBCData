"""Reviewed PC catalog identity and merge; importing this module never writes."""
from __future__ import annotations

import copy
import json
import math
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

PC_OFFSET = 100000
PC_LIMIT = 200000
FIELDS = {'health', 'damage', 'range', 'speed', 'knockbacks', 'cost', 'foreswing',
          'attack_frequency', 'recharge_time'}


def pc_key(source_id: str) -> str:
    if not isinstance(source_id, str) or not source_id.isascii() or not source_id.isdigit():
        raise ValueError('PC source_id must be a decimal string')
    number = int(source_id)
    if str(number) != source_id or not 0 <= number < PC_OFFSET:
        raise ValueError('PC source_id outside the canonical reserved range')
    return str(PC_OFFSET + number)


def _url(value):
    if not isinstance(value, str) or urlparse(value).scheme not in ('http', 'https') or not urlparse(value).netloc:
        raise ValueError('PC source URL must be an HTTP(S) URL')


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_pc_source(source: dict) -> None:
    """Reject incomplete identity, evidence and malformed measurements before writing."""
    if not isinstance(source, dict) or type(source.get('schema_version')) is not int or source['schema_version'] != 1:
        raise ValueError('Unsupported PC source schema_version')
    try:
        date.fromisoformat(source['reviewed_at'])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError('PC reviewed_at must be an ISO date') from exc
    if not isinstance(source.get('entries'), list):
        raise ValueError('PC entries must be an array')
    seen = set()
    for entry in source['entries']:
        if not isinstance(entry, dict):
            raise ValueError('PC entry must be an object')
        key = pc_key(entry.get('source_id'))
        if key in seen:
            raise ValueError(f'Duplicate PC ID {key}')
        seen.add(key)
        info = entry.get('info')
        if not isinstance(info, dict) or info.get('platform') != 'pc' or info.get('source_id') != entry['source_id']:
            raise ValueError(f'{key}: inconsistent PC identity')
        for field in ('rarity', 'name_basic', 'obtain_method'):
            if not isinstance(info.get(field), str) or not info[field].strip():
                raise ValueError(f'{key}: missing info.{field}')
        if info['rarity'] not in ('N', 'EX', 'RR', 'SR', 'UR', 'LR') or not isinstance(info.get('names_evolved'), str):
            raise ValueError(f'{key}: invalid rarity or evolved names')
        _url(info.get('source_url'))
        forms = entry.get('forms')
        if not isinstance(forms, list) or not 1 <= len(forms) <= 4:
            raise ValueError(f'{key}: one to four documented forms required')
        for index, form in enumerate(forms):
            if not isinstance(form, dict) or form.get('code') != 'fcsu'[index] or not isinstance(form.get('name'), str) or not form['name'].strip():
                raise ValueError(f'{key}: invalid form order/name')
            if not isinstance(form.get('measurements'), list) or not isinstance(form.get('abilities'), list):
                raise ValueError(f'{key}: measurements and abilities must be arrays')
            for measure in form['measurements']:
                if not isinstance(measure, dict) or measure.get('field') not in FIELDS or not {'value', 'unit', 'level', 'treasures', 'source_url'} <= measure.keys():
                    raise ValueError(f'{key}: invalid PC measurement')
                if measure['value'] is not None and not _number(measure['value']):
                    raise ValueError(f'{key}: measurement must be finite or null')
                if not isinstance(measure['unit'], str) or not measure['unit'].strip():
                    raise ValueError(f'{key}: measurement unit is required')
                if measure['level'] is not None and (type(measure['level']) is not int or measure['level'] < 1):
                    raise ValueError(f'{key}: measurement level must be positive or null')
                if measure['treasures'] is not None and not isinstance(measure['treasures'], str):
                    raise ValueError(f'{key}: invalid treasure context')
                _url(measure['source_url'])
            for ability in form['abilities']:
                if not isinstance(ability, dict) or not isinstance(ability.get('text'), str) or not ability['text'].strip() or type(ability.get('pvp_only')) is not bool:
                    raise ValueError(f'{key}: invalid PC ability')
                _url(ability.get('source_url'))
        if forms[0]['name'] != info['name_basic'] or ' / '.join(f['name'] for f in forms[1:]) != info['names_evolved']:
            raise ValueError(f'{key}: form names differ from info')
        status = entry.get('status')
        if status == 'catalog_only':
            if 'stats' in entry or 'conversion_evidence' in entry:
                raise ValueError(f'{key}: catalog-only entry cannot declare converted stats')
        elif status == 'verified':
            stats, evidence = entry.get('stats'), entry.get('conversion_evidence')
            if not isinstance(stats, list) or len(stats) != len(forms) or not isinstance(evidence, list):
                raise ValueError(f'{key}: verified stats/evidence required per form')
            covered = set()
            for item in evidence:
                if not isinstance(item, dict) or item.get('form') not in tuple('fcsu'[:len(forms)]) or type(item.get('column')) is not int or not isinstance(item.get('explanation'), str) or not item['explanation'].strip():
                    raise ValueError(f'{key}: invalid conversion evidence')
                _url(item.get('source_url'))
                identity = (item['form'], item['column'])
                if identity in covered:
                    raise ValueError(f'{key}: duplicate conversion evidence')
                covered.add(identity)
            expected = set()
            for form, row in zip(forms, stats):
                if not isinstance(row, list) or len(row) < 52 or any(not _number(value) for value in row):
                    raise ValueError(f'{key}: verified numeric CSV row required')
                expected.update((form['code'], column) for column in range(len(row)))
            if covered != expected:
                raise ValueError(f'{key}: every CSV column needs conversion evidence')
            raise ValueError(f'{key}: PC combat conversion is not supported by the current consumer; keep catalog_only')
        else:
            raise ValueError(f'{key}: invalid verification status')


def load_pc_source(path: Path) -> dict:
    source = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    validate_pc_source(source)
    return source


def merge_pc_source(data: dict, source: dict) -> dict:
    validate_pc_source(source)
    result = copy.deepcopy(data)
    mobile = {}
    for key, unit in result['units'].items():
        platform = unit.get('info', {}).get('platform', 'mobile')
        if platform == 'pc':
            if key != pc_key(unit['info'].get('source_id')):
                raise ValueError(f'{key}: inconsistent existing PC identity')
            continue
        if platform != 'mobile' or not key.isascii() or not key.isdigit() or key != str(int(key)).zfill(3) or PC_OFFSET <= int(key) < PC_LIMIT:
            raise ValueError(f'{key}: invalid mobile ID/platform or reserved ID collision')
        mobile[key] = unit
    result['units'] = mobile
    result['pc_catalog'] = {}
    verified_count = 0
    for entry in sorted(source['entries'], key=lambda item: int(item['source_id'])):
        key = pc_key(entry['source_id'])
        info, forms = copy.deepcopy(entry['info']), copy.deepcopy(entry['forms'])
        if entry['status'] == 'verified':
            result['units'][key] = {'info': info, 'stats': copy.deepcopy(entry['stats']),
                                    'pc_forms': forms, 'backswing': [None] * len(forms)}
            verified_count += 1
        else:
            result['pc_catalog'][key] = {'info': info, 'forms': forms}
    result['metadata'].update(total_units=len(result['units']), mobile_units=len(mobile) - verified_count,
                              pc_units=verified_count, pc_catalog_units=len(result['pc_catalog']),
                              pc_source_revision=source['reviewed_at'])
    return result
