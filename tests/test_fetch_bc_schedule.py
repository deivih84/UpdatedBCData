import unittest
import json
from pathlib import Path
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

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
    def test_event_capsules_read_message_at_14_and_keep_category_separate(self):
        title = "Use Legendary Starshines in these limited-time Capsules until 10/29!"
        cols = ["20261005", "1100", "20261030", "0", "150600", "999999", "0", "0",
                "4", "2", "55", "0", "0", "0", "1000", "0", "4500", "0",
                "3000", "0", "1500", "0", "0", "0", title, "", "",
                "51", "0", "0", "0", "1000", "0", "4500", "0",
                "3000", "0", "1500", "0", "0", "0", "Limited Capsules", "", ""]
        entries = schedule._extract_gacha_entries(cols)
        self.assertEqual([e["gacha_id"] for e in entries], [55, 51])
        self.assertEqual(entries[0]["tsv_full"], title)
        self.assertEqual(entries[0]["gacha_type"], 4)
        self.assertFalse(entries[0]["is_legend"])
        self.assertNotIn("Legend Rare", schedule._build_characteristics(entries[0]))

    def test_future_permanent_pool_keeps_its_real_start_date(self):
        cols = ["20261016", "1100", "20300101", "0", "150600", "999999", "0", "0",
                "1", "1", "1071", "150", "0", "0", "0", "0", "0", "0", "0", "0",
                "10000", "0", "0", "0", "Platinum Capsules"]
        with patch.object(schedule, "datetime", wraps=datetime) as clock:
            clock.now.return_value = datetime(2026, 10, 6, tzinfo=timezone.utc)
            rows = schedule.parse_gatya_tsv("\t".join(cols))
        self.assertEqual(rows[0]["start_date"], "2026-10-16")

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
        self.assertNotIn("Legend Rare", schedule._build_characteristics(entry))


class EventCapsuleResolutionTests(unittest.TestCase):
    def test_id_lookup_is_scoped_to_capsule_type(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog, cache = Path(folder) / "catalog.json", Path(folder) / "cache.json"
            catalog.write_text(json.dumps({"gachas": [
                {"nombre": "Rare banner", "gacha_id": 55},
                {"nombre": "Download Celebration!", "gacha_id": 55, "gacha_type": 4},
                {"nombre": "Summer Break Cats Paradise", "gacha_id": 51, "gacha_type": 4}]}))
            cache.write_text(json.dumps({"55": "Rare banner"}))
            with patch.object(schedule, "GACHAS_FILE", catalog), patch.object(schedule, "ID_CACHE_FILE", cache):
                by_id, aliases = schedule._load_name_dbs()
            for category, gid, expected in [(1, 55, "Rare banner"), (4, 55, "Download Celebration!"),
                                            (4, 51, "Summer Break Cats Paradise")]:
                entry = {"gacha_id": gid, "gacha_type": category,
                         "tsv_name": "Limited Capsules", "tsv_full": "Limited Capsules"}
                self.assertEqual(schedule._resolve_gacha_name(entry, by_id, aliases), expected)

    def test_unknown_generic_capsule_name_does_not_select_summer_break(self):
        entry = {"gacha_id": 9999, "gacha_type": 4,
                 "tsv_name": "Limited Capsules", "tsv_full": "Limited Capsules"}
        self.assertIsNone(schedule._resolve_gacha_name(entry, {}, {"limited capsules": "Summer Break Cats Paradise"}))
        self.assertIsNone(schedule._resolve_gacha_name(entry, {}, {"special limited capsules": "Wrong Event"}))

    def test_normal_item_capsules_do_not_use_rare_ids_or_summer_alias(self):
        for gid, full, expected in [(65, "★ Limited Capsules ★ Pick up extra Catseyes in this special Capsule set!", "Cats Eye Capsules"),
                                    (3, "Limited Capsules ★ Collect Catfruit by drawing from this set!", "Catfruit Capsules")]:
            name, full = schedule._clean_tsv_name(full)
            entry = {"gacha_id": gid, "gacha_type": 0, "tsv_name": name, "tsv_full": full}
            self.assertEqual(schedule._resolve_gacha_name(entry, {gid: "Rare banner"},
                                                        {"limited capsules": "Summer Break Cats Paradise"}), expected)


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

    def test_repository_catalog_resolves_lone_moon_lunos_to_epicfest(self):
        by_id, alias_db = schedule._load_name_dbs()
        entry = festival_entry(
            9996,
            "Lone Moon Lunos added! Special Capsules featuring powerful limited units!",
            2600,
            900,
        )

        self.assertEqual(
            schedule._resolve_gacha_name(entry, by_id, alias_db),
            "Epicfest",
        )

    def test_does_not_match_aliases_when_tsv_name_is_empty(self):
        entry = festival_entry(64, "", 0, 0, 0)
        aliases = {
            "new units added to june bride capsules ★ tap banner for info!": "June Bride",
        }

        name = schedule._resolve_gacha_name(entry, {}, aliases)

        self.assertIsNone(name)

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
