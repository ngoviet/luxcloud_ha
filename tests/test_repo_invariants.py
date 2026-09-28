"""Bất biến của repo: domain, manifest, HACS, chuỗi dịch.

Mỗi test ở đây tương ứng một quy tắc đã từng làm CI ĐỎ hoặc làm entity_id sai
(xem CLAUDE.md §3) — giữ chúng ở dạng test để không tái phạm.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
COMPONENT = REPO / "custom_components" / "luxcloud_ha"

from custom_components.luxcloud_ha import const  # noqa: E402


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


# ── Domain ─────────────────────────────────────────────────────


def test_domain_is_valid_for_ha() -> None:
    """HA chỉ cho `[a-z0-9_]` — `luxcloud-ha` và `LuxCloud` đều KHÔNG hợp lệ."""
    from homeassistant.core import valid_domain

    assert valid_domain(const.DOMAIN) is True
    assert const.DOMAIN == "luxcloud_ha"


def test_domain_is_not_taken_by_the_other_luxcloud_integration() -> None:
    """`luxcloud` đã bị BeardedTech0o/ha-luxcloud chiếm (có trong HACS default)."""
    assert const.DOMAIN != "luxcloud"


def test_manifest_domain_matches_folder_and_const() -> None:
    manifest = _load(COMPONENT / "manifest.json")
    assert manifest["domain"] == const.DOMAIN
    assert COMPONENT.name == const.DOMAIN


def test_manifest_keys_are_sorted_for_hassfest() -> None:
    """hassfest: `domain`, `name` trước, phần còn lại theo alphabet."""
    keys = list(_load(COMPONENT / "manifest.json"))
    assert keys[:2] == ["domain", "name"], f"domain/name phải đứng đầu: {keys[:2]}"
    rest = keys[2:]
    assert rest == sorted(rest), f"các key còn lại phải theo alphabet: {rest}"


def test_manifest_urls_point_at_the_real_repository() -> None:
    """Repo là `luxcloud_ha` (gạch dưới) — `luxcloud-ha` là 404."""
    manifest = _load(COMPONENT / "manifest.json")
    for key in ("documentation", "issue_tracker"):
        assert manifest[key].startswith("https://github.com/ngoviet/luxcloud_ha")
        assert "luxcloud-ha" not in manifest[key]


def test_manifest_declares_no_third_party_requirements() -> None:
    """README hứa `requirements: []` — chỉ stdlib + HA."""
    manifest = _load(COMPONENT / "manifest.json")
    assert manifest["requirements"] == []
    assert manifest["config_flow"] is True


def test_manifest_version_is_pep440_ish() -> None:
    version = _load(COMPONENT / "manifest.json")["version"]
    assert re.fullmatch(r"\d+\.\d+\.\d+([.-]?[0-9A-Za-z.]+)?", version), version


# ── HACS ───────────────────────────────────────────────────────


def test_hacs_json_exists_and_points_at_component() -> None:
    hacs = _load(REPO / "hacs.json")
    assert hacs["content_in_root"] is False
    assert (COMPONENT / "manifest.json").is_file()


def test_readme_installation_url_matches_repository_name() -> None:
    readme = (REPO / "README.md").read_text(encoding="utf-8")
    assert "github.com/ngoviet/luxcloud_ha" in readme
    assert "github.com/ngoviet/luxcloud-ha" not in readme
    assert "repository=luxcloud_ha" in readme


# ── Chuỗi dịch ─────────────────────────────────────────────────


def test_strings_json_and_english_translation_are_identical() -> None:
    """`strings.json` là nguồn; `translations/en.json` phải khớp từng byte."""
    strings = _load(COMPONENT / "strings.json")
    english = _load(COMPONENT / "translations" / "en.json")
    assert strings == english


def test_translation_covers_every_config_flow_error_key() -> None:
    """Mọi error key mà config_flow trả về phải có chuỗi dịch."""
    strings = _load(COMPONENT / "strings.json")
    errors = strings["config"]["error"]
    source = (COMPONENT / "config_flow.py").read_text(encoding="utf-8")
    returned = set(re.findall(r'return "([a-z_]+)"', source))
    # "reauth_successful" là abort reason, không phải error key
    missing = {k for k in returned if k != "reauth_successful"} - set(errors)
    assert not missing, f"thiếu chuỗi dịch cho error key: {sorted(missing)}"


# ── Hằng số giao thức ──────────────────────────────────────────


def test_regions_are_https_wmanage_endpoints() -> None:
    for region, url in const.REGIONS.items():
        assert url.startswith("https://"), region
        assert url.endswith("/WManage"), region
        assert region == url.split("//")[1].split(".")[0], region


def test_firmware_catalogue_host_is_the_as_region() -> None:
    """Danh mục firmware CHỈ trả ở host `as.` — host vùng trả 0 dòng."""
    assert const.MAJOR_URL == const.REGIONS["as"]


def test_aes_key_is_a_32_byte_aes256_key() -> None:
    assert isinstance(const.AES_KEY, bytes)
    assert len(const.AES_KEY) == 32


def test_scan_interval_bounds_are_sane() -> None:
    assert const.MIN_SCAN_INTERVAL < const.DEFAULT_SCAN_INTERVAL < const.MAX_SCAN_INTERVAL
    assert const.MIN_SCAN_INTERVAL >= 60, "dưới 60s dễ đụng session với app điện thoại"


def test_config_bit_keys_are_unique_and_non_empty() -> None:
    keys = const.CONFIG_BIT_KEYS
    assert keys, "phải có ít nhất 1 bit"
    assert len(keys) == len(set(keys))
    assert all(k.startswith("FUNC_") for k in keys)


def test_phase_one_stays_read_only() -> None:
    """Phase 1 là READ-ONLY: không được có platform ghi."""
    forbidden = {"switch.py", "number.py", "select.py", "button.py", "light.py", "climate.py"}
    present = {p.name for p in COMPONENT.glob("*.py")} & forbidden
    assert not present, f"Phase 1 không được thêm platform ghi: {sorted(present)}"

    init = (COMPONENT / "__init__.py").read_text(encoding="utf-8")
    assert "Platform.SWITCH" not in init
    assert "Platform.NUMBER" not in init
    assert "Platform.SELECT" not in init


def _calls_and_kwargs(source: str) -> tuple[set[str], set[str]]:
    """Tên hàm/method được GỌI và tên keyword được truyền (bỏ qua comment/docstring)."""
    import ast

    calls: set[str] = set()
    kwargs: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                calls.add(func.attr)
            elif isinstance(func, ast.Name):
                calls.add(func.id)
            for keyword in node.keywords:
                if keyword.arg:
                    kwargs.add(keyword.arg)
    return calls, kwargs


def test_no_deprecated_device_registry_api_is_used() -> None:
    """Hai API cũ chết ở HA 2027.8 (xem CLAUDE.md §3.5).

    Phân tích AST nên KHÔNG bắt nhầm phần docstring giải thích lý do không dùng.
    """
    for name in ("device.py", "__init__.py", "sensor.py", "binary_sensor.py"):
        calls, kwargs = _calls_and_kwargs((COMPONENT / name).read_text(encoding="utf-8"))
        assert "async_get_device" not in calls, f"{name} gọi DeviceRegistry.async_get_device"
        assert "via_device" not in kwargs, f"{name} truyền keyword `via_device` (cũ)"


def test_device_linking_uses_the_modern_api() -> None:
    """Mặt khác của §3.5: phải THẬT SỰ dùng API mới, không chỉ tránh API cũ."""
    calls, _kwargs = _calls_and_kwargs((COMPONENT / "device.py").read_text(encoding="utf-8"))
    assert "async_get_device_id_by_identifier" in calls
    assert "via_device_id" in (COMPONENT / "device.py").read_text(encoding="utf-8")


@pytest.mark.parametrize("platform_file", ["sensor.py", "binary_sensor.py"])
def test_entity_names_do_not_repeat_the_device_name(platform_file: str) -> None:
    """entity_id = slug(device) + slug(entity) → tên entity không lặp tên device.

    Đã từng ra `binary_sensor.luxcloud_dongle_dongle_mat_ket_noi`.
    """
    source = (COMPONENT / platform_file).read_text(encoding="utf-8")
    names = re.findall(r'^\s+name="([^"]+)"', source, re.MULTILINE)
    assert names, f"không tìm thấy name= nào trong {platform_file}"
    for name in names:
        tokens = {t.lower() for t in re.split(r"[^0-9A-Za-zÀ-ỹ]+", name) if t}
        assert "luxcloud" not in tokens, f"{platform_file}: tên '{name}' lặp tên device"
