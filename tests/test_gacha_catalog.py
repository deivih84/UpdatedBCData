import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "all_gachas_en.json"
SCHEDULE_PATH = ROOT / "gachas_eventos_actualizados_en1.json"


class GachaCatalogCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["gachas"]
        self.schedule = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))["gachas"]

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

    def test_schedule_uses_canonical_summer_break_cats_paradise_entry(self):
        entry = next(
            entry for entry in self.schedule
            if entry["fecha_inicio"] == "2026-08-15"
            and entry["fecha_fin"] == "2026-08-28"
        )

        self.assertEqual(
            (entry["id"], entry["nombre"]),
            ("summer_break_cats_paradise_2026-08-15", "Summer Break Cats Paradise"),
        )

    def test_epicfest_pool_contains_lunacia_and_lone_moon_lunos(self):
        epicfest = next(banner for banner in self.catalog if banner["nombre"] == "Epicfest")

        self.assertIn(787, epicfest["ubers"])
        self.assertIn(859, epicfest["ubers"])

    def test_schedule_uses_canonical_names_for_corrected_campaigns(self):
        campaigns = [
            (
                "limited_summer_capsules_with_a_new_hero_tap_banner_for_info_2026-08-28",
                "gals_of_summer_blue_ocean_2026-08-28",
                "Gals of Summer Blue Ocean",
            ),
            (
                "survive_mola_mola_collab_capsules_2026-08-28",
                "mola_mola_collab_gacha_2026-08-28",
                "Mola Mola Collab Gacha",
            ),
        ]

        for raw_id, canonical_id, canonical_name in campaigns:
            entry = next(
                entry for entry in self.schedule
                if entry["id"] in (raw_id, canonical_id)
            )
            self.assertEqual((entry["id"], entry["nombre"]), (canonical_id, canonical_name))


if __name__ == "__main__":
    unittest.main()
