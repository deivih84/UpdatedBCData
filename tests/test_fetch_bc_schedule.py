import unittest
import contextlib
import io
import json
from pathlib import Path
import tempfile
from datetime import date, datetime, timezone
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


class PermanentCapsuleTests(unittest.TestCase):
    def test_successors_retire_old_variants_only_when_they_start_in_both_regions(self):
        for region in ("en", "jp"):
            for family in ("Platinum Capsules", "Legend Capsules"):
                with self.subTest(region=region, family=family):
                    old = schedule._build_entry(f"{family} ({region.upper()} #1063)",
                                                "2026-07-24", "2030-01-01", ["G", "Guaranteed"])
                    current = schedule._build_entry(family, "2026-10-16", "2030-01-01", [])
                    future = schedule._build_entry(f"{family} ({region.upper()} #1081)",
                                                   "2026-11-01", "2030-01-01", ["S", "Step-Up"])
                    entries = [future, old, current]
                    for today, expected_names in (
                            (date(2026, 7, 1), [old["nombre"], family, future["nombre"]]),
                            (date(2026, 10, 15), [old["nombre"], family, future["nombre"]]),
                            (date(2026, 10, 16), [family, future["nombre"]]),
                            (date(2026, 10, 20), [family, future["nombre"]]),
                            (date(2026, 11, 1), [future["nombre"]])):
                        with self.subTest(today=today):
                            result = schedule._deduplicate_permanent_capsules(
                                entries, region=region, today=today)
                            result.sort(key=lambda g: g["fecha_inicio"])
                            self.assertEqual([g["nombre"] for g in result], expected_names)
                            for g in result:
                                original = next(e for e in entries if e["id"] == g["id"])
                                self.assertEqual(g["caracteristicas"], sorted(original["caracteristicas"]))
                                expected_end = {old["nombre"]: "2026-10-15", family: "2026-10-31",
                                                future["nombre"]: "2030-01-01"}[g["nombre"]]
                                self.assertEqual(g["fecha_fin"], expected_end)
                    self.assertEqual(old["fecha_fin"], "2030-01-01")

    def test_repeated_name_keeps_current_and_future_periods_and_merges_only_matching_rows(self):
        old = schedule._build_entry("Platinum Capsules", "2026-07-24", "2030-01-01", ["G"])
        future = schedule._build_entry("Platinum Capsules", "2026-10-16", "2030-01-01", [])
        duplicate = old | {"caracteristicas": ["P"]}
        result = schedule._deduplicate_permanent_capsules(
            [future, duplicate, old], today=date(2026, 10, 15))
        result.sort(key=lambda g: g["fecha_inicio"])
        self.assertEqual([g["fecha_inicio"] for g in result], ["2026-07-24", "2026-10-16"])
        self.assertEqual(result[0]["fecha_fin"], "2026-10-15")
        self.assertEqual(result[0]["caracteristicas"], ["G", "P"])
        self.assertEqual(result[1]["caracteristicas"], [])

    def test_other_families_and_other_region_suffixes_are_not_collapsed(self):
        names = ["The Dynamites", "The Dynamites (EN #1068)",
                 "Platinum Capsules Bonus", "Platinum Capsules Bonus (EN #1063)",
                 "Platinum Capsules (JP #1063)"]
        entries = [schedule._build_entry(name, "2026-07-24", "2030-01-01", []) for name in names]
        result = schedule._deduplicate_permanent_capsules(entries, today=date(2026, 10, 20))
        self.assertEqual(result, entries)

    def test_calendar_rollover_from_real_tsv_is_read_only_in_dry_run_and_preserves_events(self):
        for region in ("en", "jp"):
            with self.subTest(region=region), tempfile.TemporaryDirectory() as folder:
                repo = Path(folder)
                names, cache, lines = [], {}, []
                for family, old_id, new_id in (("Platinum Capsules", 1063, 1071),
                                               ("Legend Capsules", 1064, 1072)):
                    old_name = f"{family} ({region.upper()} #{old_id})"
                    names.extend([old_name, family])
                    cache.update({str(old_id): old_name, str(new_id): family})
                    for gid, start in ((old_id, "20260724"), (new_id, "20261016")):
                        # The parser and ID resolver both run, with no online sources.
                        cols = [start, "1100", "20300101", "1100", "150600", "999999", "0", "0",
                                "1", "1", str(gid), "150", "0", "0", "0", "0", "0", "0", "0", "0",
                                "10000", "0", "0", "0", "Shared promotional text"]
                        lines.append("\t".join(cols))
                (repo / f"all_gachas_{region}.json").write_text(json.dumps(
                    {"gachas": [{"nombre": name} for name in names]}))
                cache_file = "gacha_id_cache" + ("_jp" if region == "jp" else "") + ".json"
                (repo / cache_file).write_text(json.dumps(cache))
                tsv_path = repo / "gatya.tsv"
                tsv_path.write_text("\n".join(lines))
                output = repo / f"gachas_eventos_actualizados_{region}1.json"
                events = [{"id": "event_sentinel", "nombre": "Cats Eye Cave"}]
                output.write_text(json.dumps({"eventos": events}))
                args = ["--region", region, "--repo", str(repo), "--tsv", str(tsv_path)]
                before = {p.name: p.read_bytes() for p in repo.iterdir()}
                with patch.object(schedule, "datetime", wraps=datetime) as clock, \
                     contextlib.redirect_stdout(io.StringIO()):
                    clock.now.return_value = datetime(2026, 10, 15, tzinfo=timezone.utc)
                    schedule.main(args + ["--dry-run"])
                    self.assertEqual({p.name: p.read_bytes() for p in repo.iterdir()}, before)
                    schedule.main(args)
                    result = json.loads(output.read_text())
                    self.assertEqual(result["eventos"], events)
                    self.assertEqual(len(result["gachas"]), 4)
                    for g in result["gachas"]:
                        self.assertEqual(g["fecha_fin"], "2026-10-15" if "#" in g["nombre"] else "2030-01-01")
                    # At the replacement date, only the new pool of each family remains.
                    clock.now.return_value = datetime(2026, 10, 16, tzinfo=timezone.utc)
                    schedule.main(args)
                    result = json.loads(output.read_text())
                    self.assertEqual(result["eventos"], events)
                    self.assertEqual({g["nombre"] for g in result["gachas"]},
                                     {"Platinum Capsules", "Legend Capsules"})
                    snapshot = output.read_bytes()
                    schedule.main(args)
                    self.assertEqual(output.read_bytes(), snapshot)
                    # The same rule still applies when the sentinel end is <2 years away.
                    clock.now.return_value = datetime(2028, 6, 1, tzinfo=timezone.utc)
                    schedule.main(args)
                    result = json.loads(output.read_text())
                    self.assertEqual(len(result["gachas"]), 2)
                    for name, data in before.items():
                        if name != output.name:
                            self.assertEqual((repo / name).read_bytes(), data)


class EventCapsuleResolutionTests(unittest.TestCase):
    def test_en_calendar_hides_requested_capsules_but_keeps_festival_and_events(self):
        with tempfile.TemporaryDirectory() as folder:
            repo = Path(folder)
            (repo / "all_gachas_en.json").write_text(json.dumps({"gachas": []}))
            output = repo / "gachas_eventos_actualizados_en1.json"
            output.write_text(json.dumps({"eventos": [{"nombre": "Cats Eye Cave"}]}))
            rows = [{"start_date": "2026-10-05", "end_date": "2026-10-20",
                     "is_permanent": permanent, "entries": [
                         {"gacha_id": 65, "gacha_type": 0, "tsv_full": "Collect Catseyes!"},
                         {"gacha_id": 3, "gacha_type": 0, "tsv_full": "Collect Catfruit!"},
                         {"gacha_id": 66, "tsv_name": "Special Capsules"},
                         festival_entry(1061, "Squire Luno added! Special Capsules featuring powerful limited units!",
                                        2600, 900)]} for permanent in (False, True)]
            with patch("bc_schedule_sources.download_schedule", return_value=("fixture", {"url": "fixture"})), \
                 patch.object(schedule, "parse_gatya_tsv", return_value=rows), \
                 patch.object(schedule, "_load_name_dbs", return_value=({1061: "Uberfest"}, {})):
                schedule.main(["--repo", str(repo)])
            result = json.loads(output.read_text())
            self.assertEqual([g["nombre"] for g in result["gachas"]], ["Uberfest"])
            self.assertEqual(result["eventos"], [{"nombre": "Cats Eye Cave"}])

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
