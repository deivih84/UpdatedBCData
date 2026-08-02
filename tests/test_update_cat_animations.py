import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
import zipfile

from cat_animation_sources import SourcePackage
from cat_animation_sync import build_deterministic_zip
from update_cat_animations import (
    AppliedSource,
    ArchiveRecord,
    SourceSelectionError,
    SyncConfig,
    TransactionError,
    apply_update,
    build_manifest,
    plan_update,
    serialize_json,
)


VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def complete_form_entries(
    unit_id: int, form: str, animation: bytes = b"anim\n"
) -> dict[str, bytes]:
    prefix = f"{unit_id}_{form}"
    return {
        f"{prefix}.png": VALID_PNG,
        f"{prefix}.imgcut": b"cut\n",
        f"{prefix}.mamodel": b"model\n",
        f"{prefix}00.maanim": animation,
    }


def tree_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(
            path.read_bytes()
        ).hexdigest()
        for path in root.rglob("*")
        if path.is_file()
    }


class FailOnNthReplace:
    def __init__(self, failure_index: int):
        self.failure_index = failure_index
        self.calls = 0

    def __call__(self, source: Path, destination: Path) -> None:
        self.calls += 1
        if self.calls == self.failure_index:
            raise OSError("injected replacement failure")
        os.replace(source, destination)


class UpdateFixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.bcdata = self.root / "bcdata"
        self.cats_dir = self.root / "cats"
        self.bcdata.mkdir()
        self.cats_dir.mkdir()
        (self.bcdata / "latest.txt").write_text(
            "15.4.1en\n15.5.1jp\n13.4.0kr\n14.7.0tw\n",
            encoding="utf-8",
        )
        self.cats_data = self.root / "cats_data.json"
        self.cats_data.write_text(
            json.dumps(
                {
                    "metadata": {"version": "15.5.1"},
                    "units": {
                        "001": {"stats": [[1]]},
                        "002": {"stats": [[1]]},
                    },
                }
            ),
            encoding="utf-8",
        )
        self.data_version = self.root / "data_version.json"
        self.data_version.write_text(
            json.dumps({"gameVersion": "15.5.1"}), encoding="utf-8"
        )
        self.old_unit_1 = complete_form_entries(1, "f", b"old-animation\n")
        (self.cats_dir / "1.zip").write_bytes(
            build_deterministic_zip(1, self.old_unit_1)
        )
        self.source_path = self.root / "15.5.1.xapk"
        self.source_path.write_bytes(b"fixture")
        self.source = SourcePackage(
            version=(15, 5, 1),
            region="jp",
            path=self.source_path,
            install_pack_member="InstallPack.apk",
            base_apk_member="base.apk",
        )
        incoming = complete_form_entries(2, "f")
        incoming["1_f00.maanim"] = b"new-animation\n"
        self.incoming = incoming

    def tearDown(self):
        self.temporary.cleanup()

    def config(self, dry_run: bool = False) -> SyncConfig:
        return SyncConfig(
            bcdata=self.bcdata,
            cats_dir=self.cats_dir,
            cats_data=self.cats_data,
            data_version=self.data_version,
            sources=(self.source_path,),
            region="jp",
            force=False,
            dry_run=dry_run,
        )

    def plan(self, dry_run: bool = False):
        return plan_update(
            self.config(dry_run),
            inspector=lambda _path: self.source,
            discovery=lambda _path, _region: [self.source],
            decryptor=lambda _source: self.incoming,
        )


class ManifestTests(unittest.TestCase):
    def test_manifest_revision_is_content_derived_and_deterministic(self):
        records = {
            455: ArchiveRecord(sha256="a" * 64, size=100),
            456: ArchiveRecord(sha256="b" * 64, size=200),
        }
        sources = (
            AppliedSource(region="jp", game_version="15.5.0"),
            AppliedSource(region="jp", game_version="15.5.1"),
        )

        first = build_manifest(records, sources, {})
        second = build_manifest(
            dict(reversed(list(records.items()))), sources, {}
        )

        self.assertEqual(serialize_json(first), serialize_json(second))
        self.assertTrue(first["revision"].startswith("sha256:"))


class PlanningTests(UpdateFixture):
    def test_plan_adds_new_unit_replaces_changed_file_and_preserves_others(self):
        plan = self.plan()

        self.assertEqual(plan.report.added_resources, 4)
        self.assertEqual(plan.report.replaced_resources, 1)
        self.assertEqual(plan.report.preserved_resources, 3)
        self.assertEqual(plan.report.created_archives, (2,))
        self.assertEqual(plan.report.modified_archives, (1,))
        self.assertIn(1, plan.archive_outputs)
        self.assertIn(2, plan.archive_outputs)

    def test_plan_records_declared_forms_missing_from_archives_as_warnings(self):
        data = json.loads(self.cats_data.read_text(encoding="utf-8"))
        data["units"]["001"]["stats"] = [[1], [2], [3]]
        self.cats_data.write_text(json.dumps(data), encoding="utf-8")

        plan = self.plan()

        self.assertEqual(plan.manifest["declaredFormWarnings"]["1"], ["c", "s"])
        self.assertEqual(plan.report.new_form_warnings, {1: ("c", "s")})

    def test_plan_rejects_latest_txt_mismatch(self):
        (self.bcdata / "latest.txt").write_text(
            "15.4.1en\n15.6.0jp\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(SourceSelectionError, "15.6.0"):
            self.plan()

    def test_plan_rejects_new_data_version_without_matching_source(self):
        data = json.loads(self.cats_data.read_text(encoding="utf-8"))
        data["metadata"]["version"] = "15.6.0"
        self.cats_data.write_text(json.dumps(data), encoding="utf-8")
        (self.bcdata / "latest.txt").write_text(
            "15.4.1en\n15.6.0jp\n", encoding="utf-8"
        )

        with self.assertRaisesRegex(SourceSelectionError, "15.6.0"):
            plan_update(
                self.config(),
                inspector=lambda _path: self.source,
                discovery=lambda _path, _region: [self.source],
                decryptor=lambda _source: self.incoming,
            )


class TransactionTests(UpdateFixture):
    def test_dry_run_leaves_tree_byte_identical(self):
        plan = self.plan(dry_run=True)
        before = tree_hashes(self.root)

        report = apply_update(plan)

        self.assertTrue(report.changed_paths)
        self.assertEqual(tree_hashes(self.root), before)

    def test_apply_writes_archives_manifest_and_data_version(self):
        plan = self.plan()

        report = apply_update(plan)

        self.assertEqual(report.created_archives, (2,))
        self.assertTrue((self.cats_dir / "2.zip").is_file())
        manifest = json.loads(
            (self.cats_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["latestSource"]["gameVersion"], "15.5.1")
        data_version = json.loads(
            self.data_version.read_text(encoding="utf-8")
        )
        self.assertEqual(
            data_version["animations"]["revision"], manifest["revision"]
        )

    def test_failed_replace_restores_all_prior_destinations(self):
        plan = self.plan()
        before = tree_hashes(self.root)

        with self.assertRaises(TransactionError):
            apply_update(plan, replace_file=FailOnNthReplace(2))

        self.assertEqual(tree_hashes(self.root), before)

    def test_second_plan_is_idempotent_after_apply(self):
        apply_update(self.plan())

        second = plan_update(
            self.config(dry_run=True),
            inspector=lambda _path: self.source,
            discovery=lambda _path, _region: [self.source],
            decryptor=lambda _source: self.incoming,
        )

        self.assertEqual(second.report.changed_paths, ())
        self.assertEqual(second.report.selected_sources, ())


if __name__ == "__main__":
    unittest.main()
