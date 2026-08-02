import base64
import io
import unittest
import zipfile

from cat_animation_sync import (
    build_deterministic_zip,
    merge_entries,
    parse_resource_name,
    validate_archive,
)


VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def complete_form_entries(unit_id: int, form: str) -> dict[str, bytes]:
    prefix = f"{unit_id}_{form}"
    return {
        f"{prefix}.png": VALID_PNG,
        f"{prefix}.imgcut": b"[imgcut]\n1\n0,0,1,1\n",
        f"{prefix}.mamodel": b"[modelanim:model]\n3\n0\n",
        f"{prefix}00.maanim": b"[modelanim:animation]\n1\n0\n",
    }


class ResourceNameTests(unittest.TestCase):
    def test_accepts_unit_assets_and_removes_leading_zeroes(self):
        parsed = parse_resource_name("076_u02.maanim")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.unit_id, 76)
        self.assertEqual(parsed.form, "u")
        self.assertEqual(parsed.canonical_name, "76_u02.maanim")
        self.assertEqual(parsed.archive_path, "76/u/76_u02.maanim")

    def test_accepts_named_animation_suffixes(self):
        parsed = parse_resource_name("204_f_entry.maanim")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.canonical_name, "204_f_entry.maanim")

    def test_rejects_non_unit_lookalikes(self):
        for name in (
            "000_stamp_f.png",
            "006_charaawa.maanim",
            "455_x.png",
            "455_f.csv",
        ):
            self.assertIsNone(parse_resource_name(name), name)


class MergeAndZipTests(unittest.TestCase):
    def test_merge_adds_replaces_preserves_and_counts(self):
        result = merge_entries(
            {"1_f.png": b"old", "1_f00.maanim": b"keep"},
            {"1_f.png": b"new", "1_f.imgcut": b"cut"},
        )

        self.assertEqual(result.entries["1_f.png"], b"new")
        self.assertEqual(result.entries["1_f00.maanim"], b"keep")
        self.assertEqual(result.entries["1_f.imgcut"], b"cut")
        self.assertEqual(result.added, 1)
        self.assertEqual(result.replaced, 1)
        self.assertEqual(result.unchanged, 0)
        self.assertEqual(result.preserved, 1)

    def test_merge_counts_identical_incoming_entry_as_unchanged(self):
        result = merge_entries({"1_f.png": b"same"}, {"1_f.png": b"same"})

        self.assertEqual(result.unchanged, 1)
        self.assertEqual(result.replaced, 0)

    def test_deterministic_zip_is_byte_identical(self):
        entries = complete_form_entries(1, "f")

        first = build_deterministic_zip(1, entries)
        second = build_deterministic_zip(
            1, dict(reversed(list(entries.items())))
        )

        self.assertEqual(first, second)
        with zipfile.ZipFile(io.BytesIO(first)) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(
                archive.namelist(),
                [
                    "1/f/1_f.imgcut",
                    "1/f/1_f.mamodel",
                    "1/f/1_f.png",
                    "1/f/1_f00.maanim",
                ],
            )

    def test_zip_rejects_resource_for_another_unit(self):
        with self.assertRaisesRegex(ValueError, "Unsafe animation entry"):
            build_deterministic_zip(1, complete_form_entries(2, "f"))


class ArchiveValidationTests(unittest.TestCase):
    def test_complete_present_form_is_valid(self):
        result = validate_archive(455, complete_form_entries(455, "s"))

        self.assertEqual(result.forms, ("s",))
        self.assertEqual(result.errors, ())

    def test_present_form_requires_core_files_and_animation(self):
        entries = complete_form_entries(455, "s")
        entries.pop("455_s.png")

        result = validate_archive(455, entries)

        self.assertTrue(any("455_s.png" in error for error in result.errors))

    def test_png_signature_and_utf8_text_are_checked(self):
        entries = complete_form_entries(455, "s")
        entries["455_s.png"] = b"not-png"
        entries["455_s.mamodel"] = b"\xff"

        result = validate_archive(455, entries)

        self.assertTrue(any("PNG" in error for error in result.errors))
        self.assertTrue(any("UTF-8" in error for error in result.errors))

    def test_zero_byte_and_mismatched_unit_are_rejected(self):
        entries = complete_form_entries(455, "s")
        entries["455_s00.maanim"] = b""
        entries["456_f.png"] = VALID_PNG

        result = validate_archive(455, entries)

        self.assertTrue(any("empty" in error for error in result.errors))
        self.assertTrue(any("unit 456" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
