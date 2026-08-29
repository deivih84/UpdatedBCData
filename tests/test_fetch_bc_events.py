import json
import tempfile
import unittest
from pathlib import Path

import fetch_bc_events as events
from bc_event_name_resolver import BCEventNameResolver, EventNameHit


class EventMetadataTests(unittest.TestCase):
    def test_repository_resolves_current_mola_mola_and_summer_break_events(self):
        by_id, by_name = events.load_event_db()
        sale_rows = [{
            "start_date": "2026-08-28",
            "end_date": "2026-09-18",
            "pack_ids": [2088, 24019],
        }]

        resolved, resolved_ids = events.build_bcdata_events(
            sale_rows,
            BCEventNameResolver(),
            by_name,
        )

        self.assertEqual(by_id[18100]["nombre"], "Survive! Mola Mola!")
        self.assertEqual(by_id[24019]["nombre"], "Summer Break Cats")
        self.assertEqual(
            [(item["nombre"], item["fecha_inicio"], item["fecha_fin"]) for item in resolved],
            [
                ("Survive! Mola Mola!", "2026-08-28", "2026-09-18"),
                ("Summer Break Cats", "2026-08-28", "2026-09-18"),
            ],
        )
        self.assertEqual(resolved_ids, {2088, 24019})

    def test_dedupes_same_named_event_ranges_contained_by_full_campaign(self):
        entries = [
            events._build_event_entry("Survive! Mola Mola!", "2026-08-28", "2026-09-18"),
            events._build_event_entry("Survive! Mola Mola!", "2026-08-28", "2026-09-03"),
            events._build_event_entry("Survive! Mola Mola!", "2026-09-04", "2026-09-10"),
            events._build_event_entry("Survive! Mola Mola!", "2026-09-11", "2026-09-18"),
            events._build_event_entry("Summer Break Cats", "2026-08-28", "2026-09-18"),
        ]

        deduped = events.dedupe_contained_event_ranges(entries)

        self.assertEqual(
            [(item["nombre"], item["fecha_inicio"], item["fecha_fin"]) for item in deduped],
            [
                ("Survive! Mola Mola!", "2026-08-28", "2026-09-18"),
                ("Summer Break Cats", "2026-08-28", "2026-09-18"),
            ],
        )

    def test_load_event_db_indexes_event_ids_and_aliases(self):
        with tempfile.TemporaryDirectory() as tmp:
            original_events_file = events.EVENTS_FILE
            try:
                events.EVENTS_FILE = Path(tmp) / "all_events.json"
                events.EVENTS_FILE.write_text(
                    json.dumps({
                        "events": [
                            {
                                "nombre": "Mugen Train",
                                "aliases": ["Mugen Train Arc", "無限列車の戦い"],
                                "event_id": 9493,
                                "event_ids": [9494, 9495],
                                "descripcion": "Collab stage",
                            }
                        ]
                    }),
                    encoding="utf-8",
                )

                by_id, by_name = events.load_event_db()

                self.assertEqual(by_id[9493]["nombre"], "Mugen Train")
                self.assertEqual(by_id[9494]["nombre"], "Mugen Train")
                self.assertEqual(by_id[9495]["nombre"], "Mugen Train")
                self.assertEqual(by_name["mugen train"]["nombre"], "Mugen Train")
                self.assertEqual(by_name["mugen train arc"]["nombre"], "Mugen Train")
                self.assertEqual(by_name["無限列車の戦い"]["nombre"], "Mugen Train")
            finally:
                events.EVENTS_FILE = original_events_file

    def test_build_unknown_event_report_groups_ids_and_suggests_candidates(self):
        sale_rows = [
            {
                "start_date": "2026-03-13",
                "end_date": "2026-03-30",
                "pack_ids": [9424, 9493],
            },
            {
                "start_date": "2026-03-18",
                "end_date": "2026-03-30",
                "pack_ids": [9424],
            },
            {
                "start_date": "2026-04-01",
                "end_date": "2026-04-02",
                "pack_ids": [777],
            },
        ]
        by_id = {
            9493: {"nombre": "Known Event"},
        }
        discord_events = [
            {
                "nombre": "Demon Slayer Corps Final Selection",
                "start_date": "2026-03-13",
                "end_date": "2026-03-30",
            },
            {
                "nombre": "Mission: Slay Rui!",
                "start_date": "2026-03-18",
                "end_date": "2026-03-30",
            },
            {
                "nombre": "Otherworld Colosseum",
                "start_date": "2026-04-01",
                "end_date": "2026-04-15",
            },
        ]

        report = events.build_unknown_event_report(sale_rows, by_id, discord_events)

        self.assertEqual(report["summary"]["unknown_event_ids"], 2)
        first = report["unknown_event_ids"][0]
        self.assertEqual(first["event_id"], 9424)
        self.assertEqual(len(first["occurrences"]), 2)
        self.assertEqual(first["candidates"][0]["nombre"], "Demon Slayer Corps Final Selection")
        self.assertEqual(first["candidates"][0]["confidence"], "exact_dates")
        second = report["unknown_event_ids"][1]
        self.assertEqual(second["event_id"], 777)
        self.assertEqual(second["candidates"][0]["nombre"], "Otherworld Colosseum")
        self.assertEqual(second["candidates"][0]["confidence"], "date_overlap")

    def test_build_bcdata_events_adds_calendar_hits_and_skips_mission_only_hits(self):
        class Resolver:
            def best_hit(self, event_id):
                return {
                    1417: EventNameHit(1417, "Birthday Present!", "All_day_event", 10),
                    9641: EventNameHit(9641, "Special Mission", "Mission_Name", 60),
                }.get(event_id)

            def is_calendar_hit(self, hit):
                return hit.source != "Mission_Name"

        sale_rows = [{
            "start_date": "2026-06-19",
            "end_date": "2026-08-03",
            "pack_ids": [1417, 9641],
        }]
        by_name = {
            "birthday present!": {
                "nombre": "Birthday Present!",
                "descripcion": "Login reward stage",
            }
        }

        bcdata_events, resolved_ids = events.build_bcdata_events(sale_rows, Resolver(), by_name)

        self.assertEqual(len(bcdata_events), 1)
        self.assertEqual(bcdata_events[0]["nombre"], "Birthday Present!")
        self.assertEqual(bcdata_events[0]["caracteristicas"], ["Login reward stage"])
        self.assertEqual(resolved_ids, {1417, 9641})

        report = events.build_unknown_event_report(sale_rows, {}, [], by_name, resolved_ids=resolved_ids)

        self.assertEqual(report["summary"]["unknown_event_ids"], 0)

    def test_build_bcdata_events_keeps_only_recognized_events_from_all_day_data(self):
        class Resolver:
            def best_hit(self, event_id):
                return {
                    7000: EventNameHit(7000, "Heavenly Tower", "All_day_event", 10),
                    9326: EventNameHit(9326, "Crimson Catastrophe", "All_day_event", 10),
                    9328: EventNameHit(9328, "Peerless", "All_day_event", 10),
                    11041: EventNameHit(11041, "Arena of Destiny (Talent Tournament)", "All_day_event", 10),
                }.get(event_id)

            def is_calendar_hit(self, hit):
                return hit.source == "All_day_event"

        sale_rows = [{
            "start_date": "2026-06-26",
            "end_date": "2026-07-03",
            "pack_ids": [7000, 9326, 9328, 11041],
        }]
        by_name = {
            "heavenly tower": {
                "nombre": "Heavenly Tower",
                "descripcion": "Tower event",
            },
            "arena of destiny": {
                "nombre": "Arena of Destiny",
                "descripcion": "Dojo event",
            },
        }

        bcdata_events, resolved_ids = events.build_bcdata_events(sale_rows, Resolver(), by_name)

        self.assertEqual(
            [ev["nombre"] for ev in bcdata_events],
            ["Heavenly Tower", "Arena of Destiny"],
        )
        self.assertEqual(resolved_ids, {7000, 9326, 9328, 11041})

    def test_filter_relevant_events_removes_entries_that_already_ended(self):
        events_to_filter = [
            {"nombre": "Ended", "fecha_inicio": "2026-06-01", "fecha_fin": "2026-06-19"},
            {"nombre": "Active", "fecha_inicio": "2026-06-19", "fecha_fin": "2026-08-03"},
            {"nombre": "Future", "fecha_inicio": "2026-07-01", "fecha_fin": "2026-07-15"},
        ]

        filtered = events.filter_relevant_event_entries(events_to_filter, today=events._parse_iso_date("2026-06-28"))

        self.assertEqual([ev["nombre"] for ev in filtered], ["Active", "Future"])

        recent = events.filter_relevant_event_entries(
            [
                {"nombre": "Stale Discord", "start_date": "2026-03-21", "end_date": "2026-06-28"},
                {"nombre": "Recent Discord", "start_date": "2026-06-19", "end_date": "2026-08-03"},
            ],
            today=events._parse_iso_date("2026-06-28"),
            max_start_age_days=30,
        )

        self.assertEqual([ev["nombre"] for ev in recent], ["Recent Discord"])

    def test_filter_kept_old_events_keeps_only_recognized_metadata(self):
        old_events = [
            {
                "id": "heavenly_tower_2026-06-19",
                "nombre": "Heavenly Tower",
                "fecha_inicio": "2026-06-19",
                "fecha_fin": "2026-07-17",
            },
            {
                "id": "crimson_catastrophe_2026-06-26",
                "nombre": "Crimson Catastrophe",
                "fecha_inicio": "2026-06-26",
                "fecha_fin": "2026-07-03",
            },
        ]
        by_name = {"heavenly tower": {"nombre": "Heavenly Tower"}}

        kept = events.filter_kept_old_events(
            old_events,
            seen_ids=set(),
            new_names_by_date={},
            by_name=by_name,
            today=events._parse_iso_date("2026-06-28"),
        )

        self.assertEqual([ev["nombre"] for ev in kept], ["Heavenly Tower"])


if __name__ == "__main__":
    unittest.main()
