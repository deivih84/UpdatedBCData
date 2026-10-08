import unittest
from event_sources import EventWikiSource


class WikiPosterTests(unittest.TestCase):
    def test_unlabelled_poster_is_rejected_unless_explicitly_verified(self):
        class Response:
            def __init__(self, data):
                self.data = data
            def raise_for_status(self):
                pass
            def json(self):
                return self.data
        class Session:
            headers = {}
            def get(self, api, params, timeout):
                if params['action'] == 'parse':
                    return Response({'parse': {'title': 'Silver Week',
                        'wikitext': {'*': '{{PageBanner|Eve l 053 1.png}}'}, 'text': {'*': ''}}})
                return Response({'query': {'pages': {'1': {'title': 'File:Eve l 053 1.png',
                    'imageinfo': [{'url': 'https://wiki/unlabelled.png', 'width': 960, 'height': 480}]}}}})
        source = EventWikiSource(Session())
        self.assertNotIn('image_url', source.metadata('Silver Week', {}, {}))
        self.assertEqual(source.metadata('Silver Week', {}, {
            'bannerFiles': {'Silver Week': 'Eve l 053 1.png'}})['image_url'], 'https://wiki/unlabelled.png')

    def test_original_en_image_is_selected_and_old_promotional_dates_are_omitted(self):
        class Response:
            def __init__(self, data):
                self.data = data
            def raise_for_status(self):
                pass
            def json(self):
                return self.data
        class Session:
            headers = {}
            def get(self, api, params, timeout):
                if params['action'] == 'parse':
                    return Response({'parse': {'title': 'Silver Week',
                        'wikitext': {'*': '{{PageBanner|Eve l 053 1.png}}'},
                        'text': {'*': '<p>The season of feasting has arrived! It is the Silver Week Event! On from October 10th until October 27th!</p>'}}})
                return Response({'query': {'pages': {'1': {'title': 'File:Eve l 053 1 en.png',
                    'imageinfo': [{'url': 'https://wiki/original.png', 'thumburl': 'https://wiki/tiny.png',
                                   'width': 960, 'height': 480}]}}}})
        result = EventWikiSource(Session()).metadata('Silver Week', {}, {})
        self.assertEqual(result['image_url'], 'https://wiki/original.png')
        self.assertNotIn('October', result['description'])
        self.assertIn('Silver Week', result['description'])
