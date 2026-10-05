import json
import unittest
from pathlib import Path

import fetch_bc_schedule as schedule
from gacha_sources import POOL_FIELDS, RATE_FIELDS, parse_godfat_pool
from gacha_catalog_sync import validate_pool


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "all_gachas_en.json"


class GachaCatalogCorrectionTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))["gachas"]
        # Historical regressions exercise source parsing, not mutable live pools.
        fixtures = json.loads((ROOT / "tests/fixtures/gacha_pools_2026_08.json").read_text(encoding="utf-8"))["gachas"]
        self.historical_catalog = []
        for fixture in fixtures:
            event_id = "historical_fixture"
            html = f'<select name="event"><option selected value="{event_id}">Fixture</option></select><div class="information">'
            for label, ids_field, rate_field in zip(("Rare", "Super", "Uber", "Legendary"), POOL_FIELDS, RATE_FIELDS):
                ids = fixture[ids_field]
                html += f'<li>{label}: {fixture[rate_field] / 100:g}% ({len(ids)} cats)'
                html += " ".join(f'<a href="/cats/{unit + 1}?seed=1">Cat</a>' for unit in ids)
                html += '</li>'
            html += '</div>'
            self.historical_catalog.append({"nombre": fixture["nombre"], **parse_godfat_pool(html, event_id)})

    def test_live_catalogue_has_valid_rarity_rates_and_pool_membership(self):
        for banner in self.catalog:
            if any(banner.get(field) for field in POOL_FIELDS):
                validate_pool({"event_id": banner["nombre"],
                               **{field: banner[field] for field in RATE_FIELDS}}, banner)

    def test_promotional_aliases_belong_to_canonical_banners(self):
        expected = {
            "Limited Summer capsules with a exciting hero! Tap banner for info!": "Gals of Summer Sunshine",
            "Limited Summer capsules with a new hero! Tap banner for info!": "Gals of Summer Blue Ocean",
            "Survive! Mola Mola! Collab Capsules!": "Mola Mola Collab Gacha",
            "Mamoluga added! Unstoppable Eldritch Cats(?)!": "Luga Families",
            "Mighty Morta-Loncha added! Ultimate anti-Zombie firepower!": "Iron Legion",
            "Lone Moon Lunos added! Special Capsules featuring powerful limited units!": "Epicfest",
            "NEW Uber Rare heroes Shirou Emiya and True Assassin!": "Fate/Stay Night: Heaven's Feel Collaboration",
            "Capsules featuring Colossus Slayer units!  With Increasing Capsules!": "Colossus Busters",
        }
        aliases = {
            alias: banner["nombre"]
            for banner in self.catalog
            for alias in banner.get("aliases", [])
        }

        self.assertEqual({alias: aliases.get(alias) for alias in expected}, expected)

    def test_historical_fate_heavens_feel_pool_matches_ponos_event_1081(self):
        fate = next(
            banner for banner in self.historical_catalog
            if banner["nombre"] == "Fate/Stay Night: Heaven's Feel Collaboration"
        )

        self.assertEqual(
            (fate["rareChance"], fate["supaChance"], fate["uberChance"], fate["legendChance"]),
            (7000, 2500, 500, 0),
        )
        self.assertEqual(fate["ubers"], [864, 865, 362, 363, 364, 365, 366, 367, 368, 456])
        self.assertEqual(fate["super_rares"][0], 460)
        self.assertEqual(fate["rares"][:5], [370, 371, 372, 458, 459])
        self.assertEqual(
            tuple(len(fate[field]) for field in ("rares", "super_rares", "ubers", "legends")),
            (30, 18, 10, 0),
        )

    def test_historical_sunshine_pool_contains_only_sunshine_uber_rares(self):
        sunshine = next(banner for banner in self.historical_catalog if banner["nombre"] == "Gals of Summer Sunshine")

        self.assertEqual(sunshine["ubers"], [275, 354, 438, 563, 666, 820])

    def test_historical_blue_ocean_pool_matches_ponos_event_1076(self):
        blue_ocean = next(
            banner for banner in self.historical_catalog
            if banner["nombre"] == "Gals of Summer Blue Ocean"
        )

        self.assertEqual(blue_ocean["ubers"], [872, 494, 759, 714, 614, 564, 274])
        self.assertEqual(
            tuple(len(blue_ocean[field]) for field in ("rares", "super_rares", "ubers", "legends")),
            (25, 23, 7, 0),
        )

    def test_historical_mola_mola_pool_matches_ponos_event_1002(self):
        mola_mola = next(
            banner for banner in self.historical_catalog
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

    def test_historical_epicfest_pool_contains_lunacia_and_lone_moon_lunos(self):
        epicfest = next(banner for banner in self.historical_catalog if banner["nombre"] == "Epicfest")

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
            (
                "NEW Uber Rare heroes Shirou Emiya and True Assassin!",
                "Fate/Stay Night: Heaven's Feel Collaboration",
            ),
            (
                "Capsules featuring Colossus Slayer units!  With Increasing Capsules!",
                "Colossus Busters",
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
