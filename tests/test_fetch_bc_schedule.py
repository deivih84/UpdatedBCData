import unittest

import fetch_bc_schedule as schedule


def festival_entry(gacha_id, text, super_chance, uber_chance, legend_chance=30):
    return {
        "gacha_id": gacha_id,
        "tsv_name": text,
        "tsv_full": text,
        "super_chance": super_chance,
        "uber_chance": uber_chance,
        "legend_chance": legend_chance,
    }


class GachaEntryParsingTests(unittest.TestCase):
    def test_extracts_rarity_rates_from_standard_gacha_entry(self):
        title = "Squire Luno added! Special Capsules featuring powerful limited units!"
        cols = [
            "0", "0", "0", "0", "0", "0", "0", "0",
            "1", "1",
            "1061", "150", "0", "0",
            "0", "0", "6470", "0", "2600", "0",
            "900", "0", "30", "0", title,
        ]

        entry = schedule._extract_gacha_entries(cols)[0]

        self.assertEqual(entry["rare_chance"], 6470)
        self.assertEqual(entry["super_chance"], 2600)
        self.assertEqual(entry["uber_chance"], 900)
        self.assertEqual(entry["legend_chance"], 30)


class FestivalResolutionTests(unittest.TestCase):
    def test_known_current_pool_resolves_to_uberfest(self):
        entry = festival_entry(
            1061,
            "Squire Luno added! Special Capsules featuring powerful limited units!",
            2600,
            900,
        )

        name = schedule._resolve_gacha_name(
            entry,
            {1061: "Uberfest"},
            {},
        )

        self.assertEqual(name, "Uberfest")
        self.assertEqual(
            schedule._build_entry(name, "2026-07-29", "2026-08-03", [])["id"],
            "uberfest_2026-07-29",
        )

    def test_known_superfest_pool_remains_superfest(self):
        entry = festival_entry(
            1051,
            "New unit Lone Moon Lunos added! Special Capsules featuring powerful limited units!",
            2500,
            1000,
        )

        name = schedule._resolve_gacha_name(
            entry,
            {1051: "Superfest"},
            {},
        )

        self.assertEqual(name, "Superfest")

    def test_rejects_superfest_alias_for_nine_percent_banner(self):
        text = "A new cat! Special Capsules featuring powerful limited units!"
        entry = festival_entry(9999, text, 2600, 900)

        name = schedule._resolve_gacha_name(
            entry,
            {},
            {text.lower(): "Superfest"},
        )

        self.assertEqual(name, text)

    def test_infers_superfest_from_rates_when_featured_cat_changes(self):
        text = "Unknown future cat added! Special Capsules featuring powerful limited units!"
        entry = festival_entry(9998, text, 2500, 1000)

        name = schedule._resolve_gacha_name(entry, {}, {})

        self.assertEqual(name, "Superfest")

    def test_does_not_guess_between_unknown_uberfest_and_epicfest(self):
        text = "Unknown future cat added! Special Capsules featuring powerful limited units!"
        entry = festival_entry(9997, text, 2600, 900)

        name = schedule._resolve_gacha_name(entry, {}, {})

        self.assertEqual(name, text)

    def test_repository_catalog_resolves_current_and_previous_festivals(self):
        by_id, alias_db = schedule._load_name_dbs()
        current = festival_entry(
            1061,
            "Squire Luno added! Special Capsules featuring powerful limited units!",
            2600,
            900,
        )
        previous = festival_entry(
            1051,
            "New unit Lone Moon Lunos added! Special Capsules featuring powerful limited units!",
            2500,
            1000,
        )

        self.assertEqual(
            schedule._resolve_gacha_name(current, by_id, alias_db),
            "Uberfest",
        )
        self.assertEqual(
            schedule._resolve_gacha_name(previous, by_id, alias_db),
            "Superfest",
        )


if __name__ == "__main__":
    unittest.main()
