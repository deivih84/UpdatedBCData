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
                "limited_summer_capsules_with_a_exciting_hero_tap_banner_for_info_2026-08-07",
                "gals_of_summer_sunshine_2026-08-07",
                "Gals of Summer Sunshine",
            ),
            (
                "mamoluga_added_unstoppable_eldritch_cats_2026-08-07",
                "luga_families_2026-08-07",
                "Luga Families",
            ),
            (
                "mighty_morta_loncha_added_ultimate_anti_zombie_firepower_2026-08-10",
                "iron_legion_2026-08-10",
                "Iron Legion",
            ),
            (
                "lone_moon_lunos_added_special_capsules_featuring_powerful_limited_units_2026-08-14",
                "epicfest_2026-08-14",
                "Epicfest",
            ),
            (
                "mamoluga_added_unstoppable_eldritch_cats_2026-08-21",
                "luga_families_2026-08-21",
                "Luga Families",
            ),
            (
                "mighty_morta_loncha_added_ultimate_anti_zombie_firepower_2026-08-21",
                "iron_legion_2026-08-21",
                "Iron Legion",
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
