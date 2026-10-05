import copy
from datetime import date
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
import io

import gacha_catalog_sync as sync
from gacha_sources import parse_game_data, scheduled_events


def banner(name="The Dynamites"):
    return {"nombre": name, "aliases": [name], "imagen_url": "old.png",
            "rareChance": 7000, "supaChance": 2500, "uberChance": 500,
            "legendChance": 0, "rares": [0], "super_rares": [1],
            "ubers": [2], "legends": []}


def event(gid=100, start="2026-10-01", end="2026-10-10", text="New hero added!"):
    return {"gacha_id": gid, "event_id": f"{start}_{gid}", "start_date": start,
            "end_date": end, "tsv_full": text, "tsv_name": text,
            "rareChance": 7000, "supaChance": 2500, "uberChance": 500,
            "legendChance": 0}


def game():
    return {"version": "15.6.0", "source": "fixture", "pools": {
        100: {"rares": [0], "super_rares": [1], "ubers": [2], "legends": []},
        101: {"rares": [0], "super_rares": [1], "ubers": [2, 3], "legends": []}},
        "options": {100: {"seriesID": 1, "imgID": -1},
                    101: {"seriesID": 1, "imgID": -1}}}


class CatalogPlanningTests(unittest.TestCase):
    def plan(self, events=None, catalog=None, cache=None, state=None, names=None, meta=None):
        return sync.plan_catalog(
            catalog or {"gachas": [banner()]}, cache or {}, state or {},
            events or [event()], game(), names or {"1": "The Dynamites"},
            meta or {}, today=date(2026, 10, 6))

    def test_new_promotional_name_resolves_by_series_and_records_id(self):
        catalog, cache, state, report = self.plan()
        self.assertEqual(cache, {"100": "The Dynamites"})
        self.assertIn("New hero added!", catalog["gachas"][0]["aliases"])
        self.assertEqual(state["banners"]["100"]["family"], "The Dynamites")
        self.assertEqual(report["pending"], [])

    def test_future_content_does_not_replace_current_pool(self):
        current, future = event(), event(101, "2026-10-11", "2026-10-15")
        catalog, cache, state, report = self.plan([future, current])
        entries = {g["nombre"]: g for g in catalog["gachas"]}
        self.assertEqual(entries["The Dynamites"]["ubers"], [2])
        self.assertEqual(entries["The Dynamites (EN #101)"]["ubers"], [2, 3])
        self.assertEqual(cache["101"], "The Dynamites (EN #101)")
        # Generic promotional aliases may not belong to both variants.
        self.assertNotIn("New hero added!", entries["The Dynamites (EN #101)"]["aliases"])

    def test_variant_becomes_current_without_losing_its_old_identity(self):
        first = self.plan([event(), event(101, "2026-10-11", "2026-10-15")])
        next_event = event(101, "2026-10-11", "2026-10-15")
        result = sync.plan_catalog(first[0], first[1], first[2], [next_event],
                                   game(), {"1": "The Dynamites"}, {},
                                   today=date(2026, 10, 12))
        entries = {g["nombre"]: g for g in result[0]["gachas"]}
        self.assertEqual(entries["The Dynamites"]["ubers"], [2, 3])
        self.assertEqual(result[1]["101"], "The Dynamites")

    def test_identity_conflict_is_pending_and_preserves_catalogue(self):
        original = {"gachas": [banner(), banner("Epicfest")]}
        catalog, cache, state, report = self.plan(catalog=original, cache={"100": "Epicfest"})
        self.assertEqual(catalog, original)
        self.assertEqual(cache, {"100": "Epicfest"})
        self.assertEqual(report["pending"][0]["reason"], "identity_conflict")

    def test_recorded_id_does_not_hide_a_new_conflicting_exact_alias(self):
        initial = self.plan()
        initial[0]["gachas"].append(banner("Epicfest"))
        original = copy.deepcopy(initial[0])
        changed = event(text="Epicfest")
        data = game()
        data["options"] = {}
        data["pools"][100]["ubers"] = [999]
        result = sync.plan_catalog(initial[0], initial[1], initial[2], [changed], data,
                                   {}, {}, today=date(2026, 10, 6))
        self.assertEqual(result[0], original)
        self.assertEqual(result[3]["pending"][0]["reason"], "identity_conflict")

    def test_new_id_matching_a_variant_alias_resolves_its_family_online(self):
        initial = self.plan([event(), event(101, "2026-10-11", "2026-10-15", "Unique next hero")])
        fresh = event(102, "2026-10-20", "2026-10-25", "Unique next hero")
        data = game()
        data["options"] = {}
        data["pools"][102] = data["pools"][101]
        result = sync.plan_catalog(initial[0], initial[1], initial[2], [fresh], data,
                                   {}, {}, today=date(2026, 10, 20))
        self.assertEqual(result[3]["pending"], [])
        self.assertEqual(result[1]["102"], "The Dynamites")
        self.assertEqual(result[2]["banners"]["102"]["family"], "The Dynamites")

    def test_unknown_banner_requires_independent_name_before_creation(self):
        result = self.plan(names={"99": "Unused"})
        self.assertEqual(len(result[0]["gachas"]), 1)
        self.assertEqual(result[3]["pending"][0]["reason"], "unknown_identity")

    def test_verified_wiki_name_allows_new_banner(self):
        result = self.plan(names={"99": "Unused"}, meta={100: {
            "name": "New Collaboration", "name_source": "wiki", "image_url": ""}})
        self.assertEqual(result[0]["gachas"][-1]["nombre"], "New Collaboration")
        self.assertEqual(result[0]["gachas"][-1]["ubers"], [2])

    def test_bad_rates_abort_instead_of_writing_partial_pools(self):
        invalid = event()
        invalid["rareChance"] = 9900
        with self.assertRaises(ValueError):
            self.plan([invalid])

    def test_same_numeric_id_with_different_rates_is_pending_not_overwritten(self):
        other = event(start="2026-10-11", end="2026-10-15")
        other.update(rareChance=6900, uberChance=600)
        original = {"gachas": [banner()]}
        result = self.plan([event(), other], catalog=original)
        self.assertEqual(result[0], original)
        self.assertEqual(result[3]["pending"][0]["reason"], "conflicting_id_variants")

    def test_nonzero_rarity_cannot_have_empty_pool(self):
        data = game()
        data["pools"][100]["ubers"] = []
        with self.assertRaises(ValueError):
            sync.plan_catalog({"gachas": [banner()]}, {}, {}, [event()], data,
                              {"1": "The Dynamites"}, {}, today=date(2026, 10, 6))

    def test_equal_inputs_do_not_change_catalogue_cache_or_state(self):
        first = self.plan()
        second = self.plan(catalog=first[0], cache=first[1], state=first[2])
        self.assertEqual(second[:3], first[:3])
        self.assertEqual(second[3]["changes"], [])

    def test_changed_same_id_reports_added_unit(self):
        data = game()
        data["pools"][100]["ubers"].append(3)
        result = sync.plan_catalog({"gachas": [banner()]}, {"100": "The Dynamites"}, {},
                                   [event()], data, {}, {}, today=date(2026, 10, 6))
        self.assertEqual(result[0]["gachas"][0]["ubers"], [2, 3])
        self.assertEqual(result[3]["changes"][0]["units"]["ubers"]["added"], [3])


class SourceParsingTests(unittest.TestCase):
    def test_direct_game_pool_preserves_order_and_weighted_duplicates(self):
        units = [",".join(["0"] * 13 + [str(r)]) for r in [2, 3, 4]]
        data = parse_game_data({"GatyaDataSetR1.csv": "2,0,2,1,-1\n",
                                "unitbuy.csv": "\n".join(units),
                                "GatyaData_Option_SetR.tsv": "GatyaSetID\tseriesID\timgID\n0\t1\t9\n"})
        self.assertEqual(data["pools"][0]["ubers"], [2, 2])
        self.assertEqual(data["pools"][0]["rares"], [0])

    def test_unknown_unit_in_game_pool_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_game_data({"GatyaDataSetR1.csv": "999,-1\n", "unitbuy.csv": "0\n",
                             "GatyaData_Option_SetR.tsv": "GatyaSetID\tseriesID\timgID\n"})

    def test_future_permanent_capsules_keep_real_start_date(self):
        tsv = "\t".join(["20261016", "1100", "20300101", "0", "150600", "999999", "0", "0",
                         "1", "1", "1071", "150", "0", "0", "0", "0", "0", "0", "0", "0",
                         "10000", "0", "0", "0", "Platinum Capsules"])
        result = scheduled_events(tsv, date(2026, 10, 6))
        self.assertEqual(result[0]["start_date"], "2026-10-16")
        self.assertEqual(result[0]["end_date"], "2029-12-31")
        self.assertEqual(result[0]["uberChance"], 10000)
        # PONOS retains disabled slots with an empty final name column.
        disabled = "\t".join(["20170101", "0", "20300101", "0", "80200", "999999", "0", "0",
                              "2", "1", "0", "30", "0", "0", "0", "0", "7500", "0", "2000", "0",
                              "500", "0", "0", "0", ""])
        self.assertEqual(len(scheduled_events(tsv + "\n" + disabled, date(2026, 10, 6))), 1)

    def test_extra_capsules_do_not_use_a_rare_pool_with_the_same_numeric_id(self):
        rare = "\t".join(["20261005", "1100", "20261030", "1100", "150600", "999999", "0", "0",
                          "1", "1", "1077", "150", "0", "0", "0", "0", "7000", "0", "2500", "0",
                          "500", "0", "0", "0", "Rare Capsules"])
        extra = "\t".join(["20261005", "1100", "20261030", "1100", "150600", "999999", "0", "0",
                           "4", "1", "55", "0", "0", "0", "1000", "0", "4500", "0", "3000", "0",
                           "1500", "0", "0", "0", "Starshines", "", ""])
        events = scheduled_events(rare + "\n" + extra, date(2026, 10, 6))
        self.assertEqual([ev["gacha_id"] for ev in events], [1077])


class PublishingTests(unittest.TestCase):
    def test_image_is_hashed_copied_to_drawables_and_second_plan_is_identical(self):
        with tempfile.TemporaryDirectory() as folder:
            repo, drawable = Path(folder) / "repo", Path(folder) / "drawable"
            drawable.mkdir()
            source = io.BytesIO()
            Image.new("RGBA", (200, 50), "red").save(source, format="PNG")
            catalog = {"gachas": [banner()]}
            state = {"banners": {"100": {"name": "The Dynamites", "start_date": "2026-10-01"}}}
            report = {"images": [], "pending": []}
            metadata = {100: {"image_url": "https://wiki/exact.png", "image_source": "wiki"}}
            outputs = sync.plan_images(catalog, state, metadata, lambda _: source.getvalue(),
                                        repo, "https://public/images/", report, drawable,
                                        today=date(2026, 10, 6))
            sync.publish(outputs)
            image_url = catalog["gachas"][0]["imagen_url"]
            self.assertTrue(image_url.startswith("https://public/images/banner_en_100_"))
            filename = image_url.rsplit("/", 1)[1]
            self.assertEqual((drawable / filename).read_bytes(),
                             (repo / "images" / "gacha" / filename).read_bytes())
            again = sync.plan_images(catalog, state, metadata, lambda _: source.getvalue(),
                                      repo, "https://public/images/", {"images": [], "pending": []},
                                      drawable, today=date(2026, 10, 6))
            self.assertEqual(sync.publish(again, dry_run=True), [])
            self.assertEqual(catalog["gachas"][0]["imagen_url"], image_url)

    def test_image_failure_keeps_existing_image(self):
        with tempfile.TemporaryDirectory() as folder:
            original = {"gachas": [banner()]}
            catalog = copy.deepcopy(original)
            state = {"banners": {"100": {"name": "The Dynamites", "start_date": "2026-10-01"}}}
            report = {"images": [], "pending": []}
            def fail(_):
                raise ValueError("not an image")
            outputs = sync.plan_images(catalog, state, {100: {"image_url": "https://wiki/exact.png"}},
                                        fail, Path(folder), "https://public/images/", report,
                                        today=date(2026, 10, 6))
            self.assertEqual(catalog, original)
            self.assertEqual(outputs, {})
            self.assertEqual(report["pending"][0]["reason"], "image_unavailable")

    def test_dry_run_never_creates_or_overwrites_files(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.json"
            path.write_bytes(b"old")
            missing = Path(folder) / "images" / "new.png"
            sync.publish({path: b"new", missing: b"image"}, dry_run=True)
            self.assertEqual(path.read_bytes(), b"old")
            self.assertFalse(missing.exists())

    def test_identical_publication_is_noop(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "catalog.json"
            self.assertEqual(sync.publish({path: b"new"}), [path])
            timestamp = path.stat().st_mtime_ns
            self.assertEqual(sync.publish({path: b"new"}), [])
            self.assertEqual(path.stat().st_mtime_ns, timestamp)

    def test_failed_replacement_restores_previously_written_files(self):
        with tempfile.TemporaryDirectory() as folder:
            a, b = Path(folder) / "a.json", Path(folder) / "b.json"
            a.write_bytes(b"old-a")
            b.write_bytes(b"old-b")
            def replace(source, destination):
                if destination == b:
                    raise OSError("simulated disk failure")
                source.replace(destination)
            with self.assertRaises(OSError):
                sync.publish({a: b"new-a", b: b"new-b"}, replace_file=replace)
            self.assertEqual(a.read_bytes(), b"old-a")
            self.assertEqual(b.read_bytes(), b"old-b")


if __name__ == "__main__":
    unittest.main()
