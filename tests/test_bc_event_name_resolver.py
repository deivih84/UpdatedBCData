import tempfile
import unittest
from pathlib import Path

from bc_event_name_resolver import BCEventNameResolver, EventNameHit, discover_bcdata_version_dir


class BCEventNameResolverTests(unittest.TestCase):
    def test_resolves_map_mission_and_all_day_event_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            version = root / "15.4.1en"
            res = version / "resLocal"
            data = version / "DataLocal"
            res.mkdir(parents=True)
            data.mkdir(parents=True)

            (res / "All_day_event.tsv").write_text(
                "Birthday Present!\t1417\t0\t2\n"
                "Cybear's Vengeance\t1173\t0\t0\n",
                encoding="utf-8",
            )
            (res / "Map_Name.csv").write_text(
                "1417|Birthday Present!\n"
                "1173|Cybear's Vengeance\n",
                encoding="utf-8",
            )
            (res / "Mission_Name.csv").write_text(
                "9641|13th Anniv. Special Mission 1:<br>Complete all missions up to [Round 3]!\n",
                encoding="utf-8",
            )
            (res / "DailyLoginEventText_35047_en.tsv").write_text(
                "13th Anniversary Login Stamp No. 1!<br>You got 1 Rare Ticket!\tDay 1\n",
                encoding="utf-8",
            )
            (res / "GamatotoExpedition_Stage_nameEvent_en.csv").write_text(
                "XP Harvest (Easy)|\nCats Eye Caverns|\nShooting Range|\n",
                encoding="utf-8",
            )
            (data / "GamatotoExpedition_Stage_EVENT.csv").write_text(
                "8000,0,0,0,0,0,5011,//5011:ignored jp name\n"
                "8000,0,0,0,0,0,5014,//5014:ignored jp name\n",
                encoding="utf-8",
            )

            resolver = BCEventNameResolver(root)

            self.assertEqual(resolver.best_name(1417), "Birthday Present!")
            self.assertEqual(resolver.best_name(9641), "13th Anniv. Special Mission 1: Complete all missions up to [Round 3]!")
            self.assertEqual(resolver.best_name(35047), "13th Anniversary Login Stamp No. 1!")
            self.assertEqual(resolver.best_name(5011), "Cats Eye Caverns")
            self.assertEqual(resolver.best_name(5014), "Shooting Range")

    def test_manual_overrides_cover_special_sale_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            version = Path(tmp) / "15.4.1en"
            (version / "resLocal").mkdir(parents=True)
            (version / "DataLocal").mkdir(parents=True)

            resolver = BCEventNameResolver(Path(tmp))

            self.assertEqual(resolver.best_name(18007), "Wildcat Slots")
            self.assertEqual(resolver.best_name(15082), "13th Anniversary")
            self.assertIsNone(resolver.best_name(999999))

    def test_discover_bcdata_version_dir_picks_latest_en_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "15.3.0en").mkdir()
            (root / "15.4.1en").mkdir()
            (root / "15.4.0jp").mkdir()

            self.assertEqual(discover_bcdata_version_dir(root), root / "15.4.1en")


if __name__ == "__main__":
    unittest.main()
