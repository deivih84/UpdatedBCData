import unittest
import requests
from bc_schedule_sources import download_schedule


TSV = '20261005\t1100\t20261030\t0\t150600\t999999\t0\t0\t1\t24074\t0\n'


class ScheduleDownloadTests(unittest.TestCase):
    def test_auth_failure_uses_mirror_and_records_provenance(self):
        class Session:
            def get(self, url, timeout):
                result = requests.Response()
                result.status_code = 200
                result._content = TSV.encode()
                return result
        def denied():
            raise requests.HTTPError('token must not be printed')
        text, provenance = download_schedule('sale.tsv', denied, session=Session())
        self.assertEqual(text, TSV)
        self.assertIn('godfat', provenance['url'])
        self.assertEqual(provenance['fallbackReason'], 'HTTPError')

    def test_html_or_empty_failure_cannot_be_used_to_clear_schedule(self):
        class Session:
            def get(self, url, timeout):
                result = requests.Response()
                result.status_code = 200
                result._content = b'<html>error</html>'
                return result
        with self.assertRaises(ValueError):
            download_schedule('sale.tsv', lambda: '', session=Session())


if __name__ == '__main__':
    unittest.main()
