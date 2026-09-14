import json
import unittest
from pathlib import Path

import fetch_bc_schedule as schedule


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "all_gachas_en.json"


class GachaCatalogCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["gachas"]

    def test_promotional_aliases_belong_to_canonical_banners(self):
        expected = {
            "Limited Summer capsules with a exciting hero! Tap banner for info!": "Gals of Summer Sunshine",
            "Limited Summer capsules with a new hero! Tap banner for info!": "Gals of Summer Blue Ocean",
            "Survive! Mola Mola! Collab Capsules!": "Mola Mola Collab Gacha",
            "Mamoluga added! Unstoppable Eldritch Cats(?)!": "Luga Families",
            "Mighty Morta-Loncha added! Ultimate anti-Zombie firepower!": "Iron Legion",
            "Lone Moon Lunos added! Special Capsules featuring powerful limited units!": "Epicfest",
        }
        aliases = {
            alias: banner["nombre"]
            for banner in self.catalog
            for alias in banner.get("aliases", [])
        }

        self.assertEqual({alias: aliases.get(alias) for alias in expected}, expected)

    def test_sunshine_pool_contains_only_sunshine_uber_rares(self):
        sunshine = next(banner for banner in self.catalog if banner["nombre"] == "Gals of Summer Sunshine")

        self.assertEqual(sunshine["ubers"], [275, 354, 438, 563, 666, 820])

    def test_current_blue_ocean_pool_matches_ponos_event_1076(self):
        blue_ocean = next(
            banner for banner in self.catalog
            if banner["nombre"] == "Gals of Summer Blue Ocean"
        )

        self.assertEqual(blue_ocean["ubers"], [872, 494, 759, 714, 614, 564, 274])
        self.assertEqual(
            tuple(len(blue_ocean[field]) for field in ("rares", "super_rares", "ubers", "legends")),
            (25, 23, 7, 0),
        )

    def test_current_mola_mola_pool_matches_ponos_event_1002(self):
        mola_mola = next(
            banner for banner in self.catalog
            if banner["nombre"] == "Mola Mola Collab Gacha"
        )

        self.assertEqual(mola_mola["ubers"], [174])
        self.assertEqual(mola_mola["super_rares"][:8], [173, 237, 238, 239, 129, 131, 144, 200])
        self.assertEqual(
            tuple(len(mola_mola[field]) for field in ("rares", "super_rares", "ubers", "legends")),
            (25, 25, 1, 0),
        )

    def test_limited_capsules_resolves_to_summer_break_cats_paradise(self):
        paradise = next(
            (
                banner for banner in self.catalog
                if banner["nombre"] == "Summer Break Cats Paradise"
            ),
            None,
        )

        self.assertEqual(
            None if paradise is None else (paradise["aliases"], paradise["gatos_ids"]),
            (["Summer Break Capsules Paradise", "Limited Capsules"], [342, 375, 822, 870]),
        )

    def test_catalog_resolves_summer_break_capsules_to_canonical_entry(self):
        by_id, alias_db = schedule._load_name_dbs()
        entry = {
            "gacha_id": 9999,
            "tsv_name": "Limited Capsules",
            "tsv_full": "Limited Capsules",
        }
        self.assertEqual(
            schedule._resolve_gacha_name(entry, by_id, alias_db),
            "Summer Break Cats Paradise",
        )

    def test_epicfest_pool_contains_lunacia_and_lone_moon_lunos(self):
        epicfest = next(banner for banner in self.catalog if banner["nombre"] == "Epicfest")

        self.assertIn(787, epicfest["ubers"])
        self.assertIn(859, epicfest["ubers"])

    def test_catalog_resolves_corrected_campaign_aliases(self):
        by_id, alias_db = schedule._load_name_dbs()
        campaigns = [
            (
                "Limited Summer capsules with a new hero! Tap banner for info!",
                "Gals of Summer Blue Ocean",
            ),
            (
                "Survive! Mola Mola! Collab Capsules!",
                "Mola Mola Collab Gacha",
            ),
        ]

        for raw_name, canonical_name in campaigns:
            entry = {
                "gacha_id": 9999,
                "tsv_name": raw_name,
                "tsv_full": raw_name,
            }
            self.assertEqual(
                schedule._resolve_gacha_name(entry, by_id, alias_db),
                canonical_name,
            )


if __name__ == "__main__":
    unittest.main()
