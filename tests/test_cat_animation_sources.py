import base64
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from tbcml import core

from cat_animation_sources import (
    PackageIdentity,
    SourceInspectionError,
    SourcePackage,
    decrypt_animation_resources,
    parse_badging,
    select_pending_sources,
)


VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def source(version: str, region: str = "jp") -> SourcePackage:
    parsed = tuple(int(part) for part in version.split("."))
    return SourcePackage(
        version=parsed,
        region=region,
        path=Path(f"{region}-{version}.xapk"),
        install_pack_member="InstallPack.apk",
        base_apk_member=f"jp.co.ponos.battlecats{'' if region == 'jp' else region}.apk",
    )


def write_pack(
    apk: zipfile.ZipFile, pack_name: str, files: dict[str, bytes]
) -> None:
    pack = core.PackFile(
        pack_name,
        core.CountryCode.JP,
        core.GameVersion.from_string("15.5.1"),
    )
    for name, data in files.items():
        pack.set_file(name, core.Data(data))
    _, pack_data, list_data = pack.to_pack_list_file()
    apk.writestr(f"assets/{pack_name}.pack", pack_data.to_bytes())
    apk.writestr(f"assets/{pack_name}.list", list_data.to_bytes())


class BadgingTests(unittest.TestCase):
    def test_badging_parser_maps_jp_package_and_dotted_version(self):
        identity = parse_badging(
            "package: name='jp.co.ponos.battlecats' versionCode='1505010' "
            "versionName='15.5.1'"
        )

        self.assertEqual(
            identity,
            PackageIdentity(
                package_name="jp.co.ponos.battlecats",
                region="jp",
                version=(15, 5, 1),
            ),
        )

    def test_badging_parser_maps_all_supported_regions(self):
        packages = {
            "jp.co.ponos.battlecatsen": "en",
            "jp.co.ponos.battlecatskr": "kr",
            "jp.co.ponos.battlecatstw": "tw",
        }
        for package, region in packages.items():
            identity = parse_badging(
                f"package: name='{package}' versionCode='1504010' "
                "versionName='15.4.1'"
            )
            self.assertEqual(identity.region, region)

    def test_badging_parser_rejects_unknown_package(self):
        with self.assertRaisesRegex(SourceInspectionError, "Unsupported"):
            parse_badging(
                "package: name='com.example.notbattlecats' "
                "versionCode='1' versionName='1.0.0'"
            )

    def test_badging_parser_rejects_incomplete_version(self):
        with self.assertRaisesRegex(SourceInspectionError, "version"):
            parse_badging(
                "package: name='jp.co.ponos.battlecats' "
                "versionCode='1' versionName='15.5'"
            )


class SourceSelectionTests(unittest.TestCase):
    def test_pending_sources_are_semantically_sorted(self):
        selected = select_pending_sources(
            [source("15.5.1"), source("15.5.0"), source("15.4.1")],
            applied={("jp", "15.4.1")},
            desired_version=(15, 5, 1),
            force=False,
        )

        self.assertEqual(
            [item.version_text for item in selected], ["15.5.0", "15.5.1"]
        )

    def test_selection_excludes_versions_newer_than_data(self):
        selected = select_pending_sources(
            [source("15.5.1"), source("15.6.0")],
            applied=set(),
            desired_version=(15, 5, 1),
            force=False,
        )

        self.assertEqual([item.version_text for item in selected], ["15.5.1"])

    def test_force_reapplies_recorded_source(self):
        selected = select_pending_sources(
            [source("15.5.1")],
            applied={("jp", "15.5.1")},
            desired_version=(15, 5, 1),
            force=True,
        )

        self.assertEqual([item.version_text for item in selected], ["15.5.1"])


class PackDecryptionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def build_source(
        self,
        image_data_files: dict[str, bytes],
        number_files: dict[str, bytes],
    ) -> SourcePackage:
        install_pack = io.BytesIO()
        with zipfile.ZipFile(install_pack, "w") as apk:
            write_pack(apk, "ImageDataLocal", image_data_files)
            write_pack(apk, "NumberLocal", number_files)
        outer_path = self.root / "synthetic.xapk"
        with zipfile.ZipFile(outer_path, "w") as outer:
            outer.writestr("InstallPack.apk", install_pack.getvalue())
        return SourcePackage(
            version=(15, 5, 1),
            region="jp",
            path=outer_path,
            install_pack_member="InstallPack.apk",
            base_apk_member="jp.co.ponos.battlecats.apk",
        )

    def test_decrypts_real_tbcml_packs_and_normalizes_names(self):
        synthetic_source = self.build_source(
            {
                "076_u02.maanim": b"animation-data",
                "000_stamp_f.imgcut": b"not-a-unit",
            },
            {"076_u.png": VALID_PNG},
        )

        resources = decrypt_animation_resources(synthetic_source)

        self.assertEqual(resources["76_u02.maanim"], b"animation-data")
        self.assertEqual(resources["76_u.png"], VALID_PNG)
        self.assertNotIn("000_stamp_f.imgcut", resources)

    def test_conflicting_names_after_normalization_are_rejected(self):
        synthetic_source = self.build_source(
            {
                "076_u02.maanim": b"first",
                "76_u02.maanim": b"second",
            },
            {"076_u.png": VALID_PNG},
        )

        with self.assertRaisesRegex(SourceInspectionError, "canonical"):
            decrypt_animation_resources(synthetic_source)


if __name__ == "__main__":
    unittest.main()
