"""Download EN schedules without allowing error pages to replace live data."""
import hashlib
import re
import requests


def download_schedule(filename, direct=None, *, session=None, region="en"):
    if region not in ('en', 'jp'):
        raise ValueError('Unsupported schedule region')
    if filename not in ('sale.tsv', 'gatya.tsv'):
        raise ValueError('Unsupported schedule')
    fallback = None
    if direct is not None:
        try:
            content = direct()
            validate_schedule(content)
            return content, {'url': 'PONOS ' + region.upper() + ' ' + filename,
                             'sha256': hashlib.sha256(content.encode()).hexdigest()}
        except (requests.RequestException, RuntimeError, ValueError, KeyError) as error:
            # Exception strings can contain JWT URLs: record only the class.
            fallback = type(error).__name__
    url = 'https://bc-seek.godfat.org/seek/' + region + '/' + filename
    response = (session or requests.Session()).get(url, timeout=30)
    response.raise_for_status()
    content = response.content.decode('utf-8-sig')
    validate_schedule(content)
    return content, {'url': url, 'sha256': hashlib.sha256(content.encode()).hexdigest(),
                     **({'fallbackReason': fallback} if fallback else {})}


def validate_schedule(content):
    if not isinstance(content, str) or not any(
        re.match(r'^20\d{6}\t\d+\t20\d{6}\t', line) and len(line.split('\t')) >= 9
        for line in content.splitlines()
    ):
        raise ValueError('Source returned no valid schedule rows')
