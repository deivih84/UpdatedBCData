import json
import tempfile
import unittest
from pathlib import Path

import fetch_bc_events as events


class EventMetadataTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
