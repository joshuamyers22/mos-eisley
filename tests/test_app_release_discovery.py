"""Preview discovery exercises the actual bounded downloader without network I/O."""

from __future__ import annotations

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from mos_eisley import app_release
from mos_eisley.app_release import ReleaseError


def entry(version: str, **fields: object) -> dict[str, object]:
    return {
        "tag_name": f"v{version}",
        "draft": False,
        "prerelease": True,
        **fields,
    }


class PreviewDiscoveryTests(unittest.TestCase):
    def test_asset_heavy_inventory_selects_semantic_preview_with_small_metadata(
        self,
    ) -> None:
        entries = [
            entry("0.1.0-rc.9"),
            entry("0.1.0-rc.999", draft=True),
            entry("0.1.0", prerelease=False),
            entry("0.1.0-rc.16"),
        ]
        for item in entries:
            item["assets"] = [{"name": "ignored-public-asset", "body": "x" * 230_000}]
            item["url"] = "https://untrusted.invalid/ignored"
        raw = json.dumps(entries).encode()
        self.assertGreater(len(raw), app_release.MAX_METADATA)
        with patch.object(app_release, "build_opener") as build:
            transport = build.return_value.open
            transport.side_effect = [io.BytesIO(raw), io.BytesIO(b"selected metadata")]
            self.assertEqual(
                app_release.release_metadata("preview"), b"selected metadata"
            )
            self.assertEqual(
                [call.args[0].full_url for call in transport.call_args_list],
                [
                    app_release.FEEDS["preview"],
                    f"{app_release.RELEASE_ORIGIN}v0.1.0-rc.16/release.json",
                ],
            )
            self.assertTrue(
                all(call.kwargs == {"timeout": 10} for call in transport.call_args_list)
            )

    def test_inventory_byte_boundary_is_finite_and_does_not_fetch_metadata(
        self,
    ) -> None:
        for extra, reason in ((0, "no published preview"), (1, "byte limit")):
            with (
                self.subTest(extra=extra),
                patch.object(app_release, "build_opener") as build,
            ):
                raw = b"[]" + b" " * (app_release.MAX_PREVIEW_INVENTORY - 2 + extra)
                build.return_value.open.return_value = io.BytesIO(raw)
                with self.assertRaisesRegex(ReleaseError, reason):
                    app_release.release_metadata("preview")
                self.assertEqual(build.return_value.open.call_count, 1)

    def test_record_bound_and_invalid_inventory_fail_without_metadata_fetch(
        self,
    ) -> None:
        for value in (
            dict[str, object](),
            [None],
            [entry("0.1.0-rc.16")] * 11,
            [entry("../bad")],
            [entry("0.1.0-rc.16", tag_name=16)],
        ):
            with (
                self.subTest(value=value),
                patch.object(app_release, "build_opener") as build,
            ):
                build.return_value.open.return_value = io.BytesIO(
                    json.dumps(value).encode()
                )
                with self.assertRaises(ReleaseError):
                    app_release.release_metadata("preview")
                self.assertEqual(build.return_value.open.call_count, 1)

    def test_invalid_json_encoding_and_nesting_become_controlled_release_errors(
        self,
    ) -> None:
        for raw in (
            b"{",
            b"\xff",
            b"[" * 5000 + b"]" * 5000,
            b"[" + b"1" * 5000 + b"]",
        ):
            with (
                self.subTest(length=len(raw)),
                patch.object(app_release, "build_opener") as build,
            ):
                build.return_value.open.return_value = io.BytesIO(raw)
                with self.assertRaises(ReleaseError):
                    app_release.release_metadata("preview")
                self.assertEqual(build.return_value.open.call_count, 1)

    def test_drafts_stable_and_nonboolean_flags_cannot_offer_a_preview(self) -> None:
        for item in (
            entry("0.1.0-rc.16", draft=True),
            entry("0.1.0", prerelease=False),
            entry("0.1.0-rc.16", draft=0),
            entry("0.1.0-rc.16", prerelease=1),
        ):
            with (
                self.subTest(item=item),
                patch.object(app_release, "build_opener") as build,
            ):
                build.return_value.open.return_value = io.BytesIO(
                    json.dumps([item]).encode()
                )
                with self.assertRaisesRegex(ReleaseError, "no published preview"):
                    app_release.release_metadata("preview")
                self.assertEqual(build.return_value.open.call_count, 1)

    def test_preview_metadata_keeps_the_128_kib_limit(self) -> None:
        with patch.object(app_release, "build_opener") as build:
            build.return_value.open.side_effect = [
                io.BytesIO(json.dumps([entry("0.1.0-rc.16")]).encode()),
                io.BytesIO(b"x" * (app_release.MAX_METADATA + 1)),
            ]
            with self.assertRaisesRegex(ReleaseError, "byte limit"):
                app_release.release_metadata("preview")
            self.assertEqual(build.return_value.open.call_count, 2)

    def test_stable_metadata_keeps_its_endpoint_and_size_limit(self) -> None:
        with patch.object(app_release, "build_opener") as build:
            build.return_value.open.return_value = io.BytesIO(
                b"x" * (app_release.MAX_METADATA + 1)
            )
            with self.assertRaisesRegex(ReleaseError, "byte limit"):
                app_release.release_metadata("stable")
            self.assertEqual(
                build.return_value.open.call_args.args[0].full_url,
                app_release.FEEDS["stable"],
            )
            self.assertEqual(build.return_value.open.call_count, 1)

    def test_untrusted_endpoint_and_expired_read_deadline_still_refuse(self) -> None:
        for destination in (
            "https://untrusted.invalid/release.json",
            "http://github.com/unsafe/release.json",
            "https://user:placeholder@github.com/unsafe/release.json",
            app_release.FEEDS["preview"] + "&page=2",
        ):
            with (
                self.subTest(destination=destination),
                patch.object(app_release, "build_opener") as build,
                self.assertRaises(ReleaseError),
            ):
                app_release.download(destination, app_release.MAX_PREVIEW_INVENTORY)
            build.assert_not_called()
        with (
            patch.object(app_release, "build_opener") as build,
            patch.object(app_release.time, "monotonic", side_effect=[0, 61]),
        ):
            build.return_value.open.return_value = io.BytesIO(b"[]")
            with self.assertRaisesRegex(ReleaseError, "deadline"):
                app_release.release_metadata("preview")
            self.assertEqual(build.return_value.open.call_count, 1)

    def test_http_failure_is_not_retried_or_followed_by_a_metadata_fetch(self) -> None:
        with patch.object(app_release, "build_opener") as build:
            build.return_value.open.side_effect = URLError("synthetic unavailable feed")
            with self.assertRaises(URLError):
                app_release.release_metadata("preview")
            self.assertEqual(build.return_value.open.call_count, 1)


if __name__ == "__main__":
    unittest.main()
