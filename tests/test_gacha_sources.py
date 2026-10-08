import io
import json
import unittest

from PIL import Image
import requests

from gacha_sources import BannerSource, parse_godfat_pool, png_bytes


def pool_html(selected="2026-10-05_1077", count=2):
    return f'''<select name="event"><option selected value="{selected}">Banner</option></select>
    <div class="information"><ul>
    <li>Rare: 70% ({count} cats) <a href="//bc.godfat.org/cats/1?seed=1">A</a>
    <a href="//bc.godfat.org/cats/1?seed=1">A again</a></li>
    <li>Super: 25% (1 cat) <a href="/cats/2?seed=1">B</a></li>
    <li>Uber: 5% (1 cat) <a href="/cats/3?seed=1">C</a></li></ul></div>'''


class PoolSourceTests(unittest.TestCase):
    def test_legendary_label_is_read_in_legend_capsules(self):
        html = '''<select name="event"><option selected value="2026-07-24_1064">Legend</option></select>
        <div class="information"><li>Uber: 95% (1 cat) <a href="/cats/3?seed=1">C</a></li>
        <li>Legendary: 5% (1 cat) <a href="/cats/4?seed=1">D</a></li></div>'''
        pool = parse_godfat_pool(html, "2026-07-24_1064")
        self.assertEqual(pool["legendChance"], 500)
        self.assertEqual(pool["legends"], [3])

    def test_godfat_ids_are_zero_based_and_weights_are_preserved(self):
        pool = parse_godfat_pool(pool_html(), "2026-10-05_1077")
        self.assertEqual(pool["rares"], [0, 0])
        self.assertEqual(pool["ubers"], [2])
        self.assertEqual(pool["legendChance"], 0)

    def test_wrong_selected_event_cannot_supply_another_banners_pool(self):
        with self.assertRaises(ValueError):
            parse_godfat_pool(pool_html("other"), "2026-10-05_1077")

    def test_truncated_cat_list_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_godfat_pool(pool_html(count=3), "2026-10-05_1077")


class ImageTests(unittest.TestCase):
    def test_en_rejects_unlabelled_exact_banner_and_uses_labelled_img_id(self):
        class Session:
            headers = {}
            def get(self, url, params=None, timeout=None):
                response = requests.Response()
                response.status_code = 403 if "ponos" in url else 200
                if params and params.get("prop") == "imageinfo":
                    data = {"query": {"pages": {
                        "1": {"title": "File:Gatya bnr1061.png", "imageinfo": [
                            {"url": "https://images/jp.png", "width": 860, "height": 240}]},
                        "2": {"title": "File:Gatya bnr1033 en.png", "imageinfo": [
                            {"url": "https://images/en.png", "width": 860, "height": 240}]}}}}
                else:
                    data = {"query": {"imageusage": []}}
                response._content = json.dumps(data).encode()
                return response
        self.assertEqual(BannerSource(Session()).metadata(1061, {"imgID": 1033})["image_url"],
                         "https://images/en.png")

    def test_en_does_not_publish_unlabelled_banner_when_en_is_missing(self):
        class Session:
            headers = {}
            def get(self, url, params=None, timeout=None):
                response = requests.Response()
                response.status_code = 403 if "ponos" in url else 200
                data = {"query": {"pages": {"1": {
                    "title": "File:Gatya bnr1077.png", "imageinfo": [
                        {"url": "https://images/jp.png", "width": 860, "height": 240}]}}}}
                response._content = json.dumps(data).encode()
                return response
        self.assertNotIn("image_url", BannerSource(Session()).metadata(1077))

    def test_html_error_page_cannot_be_published_as_banner(self):
        with self.assertRaises(ValueError):
            png_bytes(b"<html>Access denied</html>")

    def test_real_image_is_decoded_and_normalized(self):
        buffer = io.BytesIO()
        Image.new("RGB", (860, 240), "red").save(buffer, format="PNG")
        result = png_bytes(buffer.getvalue())
        self.assertEqual(png_bytes(result), result)
        with Image.open(io.BytesIO(result)) as image:
            self.assertEqual(image.size, (860, 240))
            self.assertEqual(image.getpixel((50, 10)), (255, 0, 0, 255))

    def test_buttons_and_large_portraits_cannot_be_published_as_banners(self):
        for size in ((186, 54), (225, 54), (860, 54), (860, 860)):
            with self.subTest(size=size):
                buffer = io.BytesIO()
                Image.new("RGB", size, "red").save(buffer, format="PNG")
                with self.assertRaises(ValueError):
                    png_bytes(buffer.getvalue())

    def test_small_exact_image_is_skipped_for_full_img_id_banner(self):
        class Session:
            headers = {}
            def get(self, url, params=None, timeout=None):
                response = requests.Response()
                response.status_code = 403 if "ponos" in url else 200
                if params and params.get("prop") == "imageinfo":
                    self.dimensions_requested = "size" in params["iiprop"]
                    data = {"query": {"pages": {
                        "1": {"title": "File:Gatya bnr1078 en.png", "imageinfo": [
                            {"url": "https://images/button.png", "width": 225, "height": 54}]},
                        "2": {"title": "File:Gatya bnr973 en.png", "imageinfo": [
                            {"url": "https://images/full.png", "width": 860, "height": 240}]}}}}
                else:
                    data = {"query": {"imageusage": []}}
                response._content = json.dumps(data).encode()
                return response
        session = Session()
        meta = BannerSource(session).metadata(1078, {"seriesID": 47, "imgID": 973})
        self.assertEqual(meta["image_url"], "https://images/full.png")
        self.assertTrue(session.dimensions_requested)

    def test_verified_family_banner_is_used_when_new_id_is_not_on_wiki(self):
        class Session:
            headers = {}
            def get(self, url, params=None, timeout=None):
                response = requests.Response()
                response.status_code = 403 if "ponos" in url else 200
                if params and params.get("prop") == "imageinfo":
                    self.titles = params["titles"]
                    data = {"query": {"pages": {"1": {
                        "title": "File:Gatya bnr174.png", "imageinfo": [
                            {"url": "https://images/platinum.png", "width": 860, "height": 240}]}}}}
                else:
                    data = {"query": {"imageusage": [{"title": "Platinum Capsules (Gacha Event)"}]}}
                response._content = json.dumps(data).encode()
                return response
        session = Session()
        meta = BannerSource(session).metadata(1071, {"seriesID": 21, "imgID": 970}, fallback_image_id=174)
        self.assertIn("File:Gatya bnr174.png", session.titles)
        self.assertNotIn("Gatya btn", session.titles)
        self.assertEqual(meta["image_url"], "https://images/platinum.png")
        self.assertEqual(meta["name"], "Platinum Capsules")

    def test_button_only_or_missing_dimensions_does_not_supply_artwork(self):
        for dimensions in ({"width": 186, "height": 54}, {}):
            with self.subTest(dimensions=dimensions):
                class Session:
                    headers = {}
                    def get(self, url, params=None, timeout=None):
                        response = requests.Response()
                        response.status_code = 403 if "ponos" in url else 200
                        if params and params.get("prop") == "imageinfo":
                            data = {"query": {"pages": {"1": {
                                "title": "File:Gatya bnr1071 en.png", "imageinfo": [
                                    {"url": "https://images/small.png", **dimensions}]}}}}
                        else:
                            data = {"query": {"imageusage": []}}
                        response._content = json.dumps(data).encode()
                        return response
                self.assertNotIn("image_url", BannerSource(Session()).metadata(1071))

    def test_exact_artwork_on_second_wiki_precedes_family_fallback_on_first(self):
        class Session:
            headers = {}
            def get(self, url, params=None, timeout=None):
                response = requests.Response()
                response.status_code = 403 if "ponos" in url else 200
                if params and params.get("prop") == "imageinfo":
                    exact = "fandom" in url
                    title = "File:Gatya bnr1071 en.png" if exact else "File:Gatya bnr174.png"
                    image_url = "https://images/exact.png" if exact else "https://images/family.png"
                    data = {"query": {"pages": {"1": {"title": title, "imageinfo": [
                        {"url": image_url, "width": 860, "height": 240}]}}}}
                else:
                    data = {"query": {"imageusage": []}}
                response._content = json.dumps(data).encode()
                return response
        meta = BannerSource(Session()).metadata(1071, {"seriesID": 21, "imgID": 970}, fallback_image_id=174)
        self.assertEqual(meta["image_url"], "https://images/exact.png")

    def test_banner_lookup_uses_exact_id_even_when_wiki_returns_different_order(self):
        class Session:
            headers = {}
            def get(self, url, params=None, timeout=None):
                result = requests.Response()
                result.status_code = 403 if "ponos" in url else 200
                if params and params.get("prop") == "imageinfo":
                    result._content = json.dumps({"query": {"pages": {
                        "1": {"title": "File:Gatya btn70.png", "imageinfo": [{"url": "https://images/series.png", "width": 860, "height": 240}]},
                        "2": {"title": "File:Gatya bnr1077 en.png", "imageinfo": [{"url": "https://images/exact.png", "width": 860, "height": 240}]}}}}).encode()
                else:
                    result._content = json.dumps({"query": {"imageusage": [
                        {"title": "Best of the Best Milestone Edition (Gacha Event)/Gallery"}]}}).encode()
                return result
        meta = BannerSource(Session()).metadata(1077, {"seriesID": 70, "imgID": -1})
        self.assertEqual(meta["image_url"], "https://images/exact.png")
        self.assertEqual(meta["name"], "Best of the Best Milestone Edition")

    def test_english_artwork_is_preferred_when_the_wiki_has_both_languages(self):
        class Session:
            headers = {}
            def get(self, url, params=None, timeout=None):
                response = requests.Response()
                response.status_code = 403 if "ponos" in url else 200
                if params and params.get("prop") == "imageinfo":
                    data = {"query": {"pages": {
                        "1": {"title": "File:Gatya bnr1077.png", "imageinfo": [{"url": "https://images/jp.png", "width": 860, "height": 240}]},
                        "2": {"title": "File:Gatya bnr1077 en.png", "imageinfo": [{"url": "https://images/en.png", "width": 860, "height": 240}]}}}}
                else:
                    data = {"query": {"imageusage": []}}
                response._content = json.dumps(data).encode()
                return response
        self.assertEqual(BannerSource(Session()).metadata(1077)["image_url"], "https://images/en.png")

    def test_ambiguous_wiki_usage_does_not_invent_a_canonical_name(self):
        class Session:
            headers = {}
            def get(self, url, params=None, timeout=None):
                result = requests.Response()
                result.status_code = 403 if "ponos" in url else 200
                if params and params.get("prop") == "imageinfo":
                    data = {"query": {"pages": {"1": {"title": "File:Gatya bnr1077 en.png",
                            "imageinfo": [{"url": "https://images/exact.png", "width": 860, "height": 240}]}}}}
                else:
                    data = {"query": {"imageusage": [{"title": "One (Gacha Event)"},
                                                      {"title": "Other (Gacha Event)"}]}}
                result._content = json.dumps(data).encode()
                return result
        meta = BannerSource(Session()).metadata(1077)
        self.assertNotIn("name", meta)

    def test_malformed_wiki_shapes_fall_back_without_aborting_valid_pool_work(self):
        for malformed in ([], {"query": []}, {"query": {"pages": []}},
                          {"query": {"pages": {"1": []}}}):
            with self.subTest(malformed=malformed):
                class Session:
                    headers = {}
                    def get(self, url, params=None, timeout=None):
                        response = requests.Response()
                        response.status_code = 403 if "ponos" in url else 200
                        response._content = json.dumps(malformed).encode()
                        return response
                meta = BannerSource(Session()).metadata(1077)
                self.assertNotIn("image_url", meta)
                self.assertEqual(len(meta["warnings"]), 2)


if __name__ == "__main__":
    unittest.main()
