"""Tests for Dreame cloud region routing."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_MODULE_PATH = (
    Path(__file__).parents[1] / "custom_components" / "dreame_mf10" / "dreame_cloud.py"
)
_SPEC = importlib.util.spec_from_file_location(
    "dreame_cloud_regions_under_test", _MODULE_PATH
)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
DreameCloud = _MODULE.DreameCloud

_CONST_PATH = _MODULE_PATH.with_name("const.py")
_CONST_SPEC = importlib.util.spec_from_file_location(
    "dreame_mf10_const_regions_under_test", _CONST_PATH
)
assert _CONST_SPEC is not None and _CONST_SPEC.loader is not None
_CONST_MODULE = importlib.util.module_from_spec(_CONST_SPEC)
sys.modules[_CONST_SPEC.name] = _CONST_MODULE
_CONST_SPEC.loader.exec_module(_CONST_MODULE)
REGION_OPTIONS = _CONST_MODULE.REGION_OPTIONS


class DreameCloudRegionTests(unittest.TestCase):
    def test_canada_is_available_in_config_flow_options(self) -> None:
        self.assertEqual(REGION_OPTIONS["ca"], "Canada (US cloud)")

    def test_canada_uses_us_cloud_cluster(self) -> None:
        cloud = DreameCloud("user", "password", "ca", object())

        self.assertEqual(cloud.api_region, "us")
        self.assertEqual(cloud.api_url, "https://us.iot.dreame.tech:13267")

    def test_existing_regions_are_unchanged(self) -> None:
        for region in ("eu", "cn", "us", "sg", "ru"):
            with self.subTest(region=region):
                cloud = DreameCloud("user", "password", region, object())

                self.assertEqual(cloud.api_region, region)
                self.assertEqual(
                    cloud.api_url,
                    f"https://{region}.iot.dreame.tech:13267",
                )

    def test_canada_does_not_receive_china_only_header(self) -> None:
        cloud = DreameCloud("user", "password", "ca", object())
        cloud._access_token = "access-token"

        self.assertNotIn("Dreame-Rlc", cloud._auth_headers())


if __name__ == "__main__":
    unittest.main()
