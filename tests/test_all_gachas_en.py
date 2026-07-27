import json
import re
import unicodedata
import unittest
from collections import defaultdict
from pathlib import Path


CATALOG_PATH = Path(__file__).resolve().parents[1] / "all_gachas_en.json"


def normalize_label(value):
    ascii_value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", ascii_value.lower()).strip()


class GachaCatalogTests(unittest.TestCase):
    def test_names_and_aliases_do_not_identify_multiple_banners(self):
        catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["gachas"]
        owners = defaultdict(set)

        for index, banner in enumerate(catalog):
            labels = {banner["nombre"], *banner.get("aliases", [])}
            for label in labels:
                owners[normalize_label(label)].add((index, banner["nombre"]))

        collisions = {
            label: sorted(entries)
            for label, entries in owners.items()
            if label and len(entries) > 1
        }
        self.assertEqual(collisions, {})


if __name__ == "__main__":
    unittest.main()
