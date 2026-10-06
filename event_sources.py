"""Game ID/name snapshots and explicitly declared event posters from the wiki."""
import io
import re
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

from bs4 import BeautifulSoup
from PIL import Image
import requests

from bc_event_name_resolver import BCEventNameResolver
from gacha_sources import USER_AGENT, WIKIS


def event_dimensions(width, height):
    if (not isinstance(width, int) or not isinstance(height, int)
            or not (600 <= width <= 4096 and 300 <= height <= 4096)
            or not 1.5 <= width / height <= 3):
        raise ValueError(f'Unexpected event poster dimensions {width}x{height}')


def event_png_bytes(data):
    if len(data) > 12 * 1024 * 1024:
        raise ValueError('Event poster exceeds 12 MB')
    try:
        with Image.open(io.BytesIO(data)) as image:
            event_dimensions(*image.size)
            image.load()
            stream = io.BytesIO()
            image.convert('RGBA').save(stream, format='PNG')
            return stream.getvalue()
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError('Source did not return a valid event poster') from error


def declared_banner(wikitext):
    match = re.search(r'\{\{\s*PageBanner\s*\|\s*([^|}\n]+)', wikitext, re.I)
    return match.group(1).strip().removeprefix('File:') if match else None


def wiki_page_for(name, event, config):
    if name in config.get('wikiPages', {}):
        return config['wikiPages'][name]
    url = urlparse(event.get('url', ''))
    if url.hostname in ('battlecats.miraheze.org', 'battle-cats.fandom.com') and '/wiki/' in url.path:
        return unquote(url.path.split('/wiki/', 1)[1]).replace('_', ' ')
    campaign = re.fullmatch(r'(\d+)M Download Celebration!', name)
    if campaign:
        return f'Million Downloads Event/{campaign.group(1)} Million'
    anniversary = re.fullmatch(r'(\d+)(?:st|nd|rd|th) Anniversary', name)
    if anniversary:
        number = int(anniversary.group(1))
        suffix = 'th' if 10 <= number % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
        return f'Anniversary/{number}{suffix} Year'
    return name


class EventWikiSource:
    def __init__(self, session=None):
        self.session = session or requests.Session()
        self.session.headers.update({'User-Agent': USER_AGENT})

    def metadata(self, name, event, config):
        page = wiki_page_for(name, event, config)
        explicit_banner = config.get('bannerFiles', {}).get(name)
        if urlparse(event.get('url', '')).fragment and not explicit_banner:
            return {'warnings': ['section_has_no_verified_poster']}
        warnings = []
        for api in WIKIS:
            try:
                response = self.session.get(api, params={'action': 'parse', 'format': 'json',
                    'page': page, 'prop': 'wikitext|text', 'redirects': 1}, timeout=20)
                response.raise_for_status()
                parsed = response.json().get('parse', {})
                if not isinstance(parsed, dict) or not isinstance(parsed.get('title'), str):
                    continue
                text = parsed.get('wikitext', {}).get('*', '')
                banner = explicit_banner or declared_banner(text)
                if not banner or re.search(r'(?:\s|_)(?:ja|jp)\.', banner, re.I):
                    continue
                # Prefer the EN original, never a thumbnail URL.
                candidates = [banner]
                if not re.search(r'(?:\s|_)en\.', banner, re.I):
                    candidates.insert(0, re.sub(r'(\.[^.]+)$', r' en\1', banner))
                response = self.session.get(api, params={'action': 'query', 'format': 'json',
                    'prop': 'imageinfo', 'iiprop': 'url|size',
                    'titles': '|'.join('File:' + title for title in candidates)}, timeout=25)
                response.raise_for_status()
                pages = response.json().get('query', {}).get('pages', {})
                if not isinstance(pages, dict):
                    raise ValueError('Malformed wiki image pages')
                by_title = {p['title']: p for p in pages.values() if isinstance(p, dict) and 'title' in p}
                for candidate in candidates:
                    info = by_title.get('File:' + candidate, {}).get('imageinfo', [])
                    if not info or not isinstance(info[0], dict):
                        continue
                    try:
                        event_dimensions(info[0].get('width'), info[0].get('height'))
                    except ValueError:
                        continue
                    if urlparse(info[0].get('url', '')).scheme != 'https':
                        continue
                    base = 'https://battlecats.miraheze.org/wiki/' if 'miraheze' in api else 'https://battle-cats.fandom.com/wiki/'
                    from urllib.parse import quote
                    url = base + quote(parsed['title'].replace(' ', '_'), safe='/!()')
                    # A short attributed excerpt; never mirror the full article.
                    html = parsed.get('text', {}).get('*', '')
                    description = ''
                    for paragraph in BeautifulSoup(html, 'html.parser').find_all('p', recursive=True):
                        text = paragraph.get_text(' ', strip=True)
                        if paragraph.find('i') or 'not to be confused' in text.lower():
                            continue
                        # Promotional wiki dates can describe an older recurrence.
                        sentences = re.split(r'(?<=[.!?])\s+', text)
                        sentences = [sentence for sentence in sentences if not re.search(
                            r'\b(?:January|February|March|April|May|June|July|August|September|October|November|December)\b|\d{1,2}:\d{2}|\b20\d{2}\b',
                            sentence, re.I)]
                        words = ' '.join(sentences).split()
                        if len(words) >= 8:
                            description = ' '.join(words[:25]) + ('…' if len(words) > 25 else '')
                            break
                    return {'url': url, 'wikiPage': parsed['title'], 'image_url': info[0]['url'],
                            'image_source': info[0].get('descriptionurl', url),
                            'description': description, 'warnings': warnings}
            except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError):
                warnings.append('wiki_unavailable: ' + api)
        return {'warnings': warnings}

    def image(self, url):
        if urlparse(url).scheme != 'https':
            raise ValueError('Poster source must use HTTPS')
        response = self.session.get(url, timeout=30)
        response.raise_for_status()
        return event_png_bytes(response.content)


def index_from_resolver(resolver):
    result = {'schemaVersion': 1, 'version': resolver.version_dir.name[:-2] if resolver.version_dir else '0.0.0',
              'source': 'BCData EN resources', 'names': {}}
    for event_id in sorted(resolver.by_id):
        hit = resolver.best_hit(event_id)
        result['names'][str(event_id)] = {'name': hit.name, 'source': hit.source,
                                        'calendar': resolver.is_calendar_hit(hit)}
    return result


def version_key(version):
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Invalid BCData EN version')
    return tuple(int(n) for n in version.split('.'))


def load_event_index(existing, session, *, bcdata=None, online=False):
    warnings = []
    local = BCEventNameResolver(bcdata)
    index = existing or index_from_resolver(local)
    if local.available and version_key(local.version_dir.name[:-2]) >= version_key(index['version']):
        index = index_from_resolver(local)
    if online or not local.available:
        base = 'https://raw.githubusercontent.com/fieryhenry/BCData/master/'
        try:
            response = session.get(base + 'latest.txt', timeout=20)
            response.raise_for_status()
            versions = [line.strip()[:-2] for line in response.text.splitlines() if line.strip().endswith('en')]
            if len(versions) != 1:
                raise ValueError('BCData must declare one EN version')
            version = versions[0]
            if version_key(version) >= version_key(index['version']):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp) / (version + 'en')
                    files = ['resLocal/All_day_event.tsv', 'resLocal/Map_Name.csv', 'resLocal/Mission_Name.csv',
                             'resLocal/GamatotoExpedition_Stage_nameEvent_en.csv', 'DataLocal/GamatotoExpedition_Stage_EVENT.csv']
                    for file in files:
                        response = session.get(base + version + 'en/' + file, timeout=25)
                        response.raise_for_status()
                        target = root / file
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(response.content)
                    refreshed = index_from_resolver(BCEventNameResolver(root))
                    if not any(hit['source'] == 'All_day_event' for hit in refreshed['names'].values()):
                        raise ValueError('Online BCData contains no event names')
                    # The remote subset omits login resources; retain names already
                    # learned from complete local packs, including at equal versions.
                    refreshed['names'] = {**index['names'], **refreshed['names']}
                    index = refreshed
                    index['source'] = base + version + 'en/'
            elif version_key(version) < version_key(index['version']):
                warnings.append('remote_name_index_older_than_saved: ' + version)
        except (requests.RequestException, ValueError, KeyError, OSError):
            warnings.append('name_index_unavailable; saved index retained')
    return index, warnings
