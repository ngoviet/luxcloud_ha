# LuxCloud (LuxPower Cloud API) — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/ngoviet/luxcloud_ha.svg)](https://github.com/ngoviet/luxcloud_ha/releases)
[![Test](https://github.com/ngoviet/luxcloud_ha/actions/workflows/test.yml/badge.svg)](https://github.com/ngoviet/luxcloud_ha/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2026.9%2B-41BDF5)](https://www.home-assistant.io)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ngoviet&repository=luxcloud_ha&category=integration)

Reads your **LuxPower** hybrid inverter through the **LuxCloud** cloud API — the same data the
phone app shows, including the parts a local Modbus connection cannot see: dongle health,
localised fault history, BMS cell detail, the firmware catalogue, the intraday power curve,
yearly totals and the HR[179] configuration bits. It can also **write** the handful of settings
only the cloud exposes.

> **36 entities, 2 devices.** 29 read-only entities, plus 3 `switch` entities for the HR[179]
> configuration bits a local Modbus integration does not expose, 4 `button`s for
> quick charge/discharge, and a `luxcloud_ha.set_bit` service.
> See [Writing to the inverter](#writing-to-the-inverter).

---

## Why cloud, when local Modbus already exists?

Both paths reach the same inverter, but they carry different data. This integration does **not**
replace a local integration — it fills the gaps the local one has no access to.

| Data | Local Modbus (e.g. `lxp_modbus`) | This integration (cloud) |
|---|---|---|
| Live power / voltage / SOC | ✅ real time | ✅ but delayed by the dongle upload interval |
| Full register read/write, settings | ✅ | ⛔ only what the app exposes |
| Dongle connectivity + last cloud report | ⛔ | ✅ `lost`, `lastUpdateTime` |
| Fault history with localised text | ⛔ | ✅ (server returns text in your app language) |
| Firmware catalogue + version check | ⛔ | ✅ per device type |
| Intraday power curve, yearly totals | ⛔ | ✅ |
| BMS cell min/max voltage & temperature, cycles | partial | ✅ |
| Works when the inverter is on another network | ⛔ | ✅ |

Local network access to the inverter is **not** required. Only an internet connection and a
LuxPower cloud account are.

---

## Features

- **36 entities across 2 devices** — one device per inverter, plus the datalogger as a
  separate device linked with `via_device`.
- **Config flow with validation** — credentials and serial are verified during setup, plus a
  reauth step and an options step (no YAML at all).
- **Adjustable polling** — 60 s to 3600 s (default 300 s).
- **Slow-key scheduling** — firmware catalogue, intraday curve and yearly totals are fetched
  every 6th poll (~30 min), so the fast path stays cheap.
- **Writes only what the cloud owns** — 3 `switch` entities plus quick charge/discharge
  `button`s and a `set_bit` service. See [Writing to the inverter](#writing-to-the-inverter).
- **Diagnostics support** — download a config dump from the UI with the account, password,
  serial numbers and plant name replaced by `**REDACTED**`, so the file is safe to attach to
  an issue. Raw readings, bit states and firmware codes are kept, because that is what makes
  the dump useful.
- **No third-party dependencies** — stdlib plus Home Assistant itself (`requirements: []`).
- **Real fault text** — the cloud returns already-localised fault strings (Vietnamese here),
  no client-side translation table to maintain.

---

## Requirements

| Requirement | Details |
|---|---|
| Home Assistant | 2026.9 or newer (verified on 2026.9.3 and, after the automatic update, on 2026.9.4) |
| Python | 3.14 (shipped with that HA release) |
| LuxPower account | The account you use in the LuxCloud app |
| Inverter | LuxPower hybrid with a WiFi/LAN datalogger that is online |

---

## Installation

### HACS (custom repository)

1. HACS → **⋮ → Custom repositories**
2. Add `https://github.com/ngoviet/luxcloud_ha` with category **Integration**
3. Search for **LuxCloud**, install it
4. Restart Home Assistant

### Manual

Copy `custom_components/luxcloud_ha/` into your Home Assistant `config/custom_components/`
directory and restart.

---

## Configuration

**Settings → Devices & Services → Add Integration → LuxCloud**

| Field | Notes |
|---|---|
| Account | The e-mail you sign in to the LuxCloud app with |
| Password | Your LuxPower account password |
| Inverter serial number | e.g. `61204F0266`; also visible in the app under Device → Info |
| Region | `vn` (default), `as`, `na`, `eu2`, `ind`, `af`, `phi`, `us` — one entry per region |
| Scan interval | Seconds between polls, 60–3600 |
| Enable series | Intraday power curve + yearly totals |
| Enable firmware | Firmware catalogue lookup (always uses the `as` host) |

Multiple inverters: add the integration once per serial number.

> **Region matters.** The firmware catalogue only answers on the `as` host — regional hosts
> return zero rows. This is handled internally; the setting is only for the main API.

---

## Entities

### Device 1 — the inverter

| Entity | Unit | Notes |
|---|---|---|
| `sensor.*_chu_ky_pin` | | Battery cycle count |
| `sensor.*_lech_cell` | mV | Max − min cell voltage |
| `sensor.*_cell_cao_nhat` / `_cell_thap_nhat` | mV | Highest / lowest cell voltage |
| `sensor.*_nhiet_do_cell_cao_nhat` / `_nhiet_do_cell_thap_nhat` | °C | Cell temperature extremes |
| `sensor.*_trang_thai_bms` | | BMS state (`Charging`, …) |
| `sensor.*_ngo_ra_ac_pinv` | W | AC output power |
| `sensor.*_rectifier_prec` | W | Rectifier / AC-charge power |
| `sensor.*_su_co_gan_nhat` | | Latest fault, localised by the server |
| `sensor.*_co2_giam` / `_than_giam` / `_tuong_duong_cay` | t / kg / trees | Lifetime CO₂, coal and tree equivalents |
| `sensor.*_ma_firmware_inverter` | | Firmware code, e.g. `CHAA-000303` |
| `sensor.*_firmware_moi_nhat` | | Newest catalogue version for this device type |
| `sensor.*_chuoi_cong_suat_hom_nay` | | Number of intraday points (curve in attributes) |
| `sensor.*_tong_theo_nam` | kWh | Current-year PV total (all years in attributes) |
| `sensor.*_bit_cau_hinh_hr_179_dang_bat` | | Count of enabled HR[179] bits (map in attributes) |
| `sensor.*_trang_thai_quick_charge_discharge` | | Cloud-side quick charge/discharge state |
| `sensor.*_tong_san_luong_plant` | kWh | Plant lifetime yield |
| `switch.*_grid_peak_shaving` | | `FUNC_GRID_PEAK_SHAVING` — **writes** (see below) |
| `switch.*_gen_peak_shaving` | | `FUNC_GEN_PEAK_SHAVING` — **writes** |
| `switch.*_active_power_limit_mode` | | `FUNC_ACTIVE_POWER_LIMIT_MODE` — **writes** |
| `button.*_quick_charge_start` / `_quick_charge_stop` | | Force battery charging (cloud side) — **writes** |
| `button.*_quick_discharge_start` / `_quick_discharge_stop` | | Force battery discharging (cloud side) — **writes** |
| `binary_sensor.*_su_co_dang_hieu_luc` | | A fault is currently active |
| `binary_sensor.*_dang_chay_quick_charge_discharge` | | A quick charge/discharge task is running |
| `binary_sensor.*_co_firmware_moi` | | Newer firmware available than installed |
| `binary_sensor.*_dang_chay_khong_luoi_isoffgrid` | | Running off-grid |
| `binary_sensor.*_cloud_co_du_lieu` | | Cloud returned usable runtime data |

### Device 2 — the datalogger (linked with `via_device`)

| Entity | Notes |
|---|---|
| `sensor.*_dongle_firmware` | Datalogger firmware, e.g. `V2.11` |
| `sensor.*_dongle_bao_cloud_lan_cuoi` | Timestamp of the last cloud upload |
| `sensor.*_dongle_kieu_ket_noi` | Datalogger type, e.g. `E Wi-Fi` |
| `binary_sensor.*_dongle_mat_ket_noi` | Datalogger offline |

> Entity IDs use the device name (`LuxCloud`) as a prefix, so ids read
> `sensor.luxcloud_chu_ky_pin`. Rename devices in Home Assistant freely — the entity ids
> follow your rename.

---

## Writing to the inverter

Everything below is a **real write** — cloud → datalogger → inverter, exactly what the phone
app does when you flip one of these in its settings screens. Nothing here is a local register
write.

| What | How |
|---|---|
| `FUNC_GRID_PEAK_SHAVING`, `FUNC_GEN_PEAK_SHAVING`, `FUNC_ACTIVE_POWER_LIMIT_MODE` | The 3 `switch` entities |
| Quick charge / quick discharge | The 4 `button` entities (`start`/`stop` each) |
| Any other HR[179] bit | The `luxcloud_ha.set_bit` service |

```yaml
service: luxcloud_ha.set_bit
target:
  device_id: 1a2b3c...        # optional when only one inverter is configured
data:
  function: FUNC_RSD_DISABLE
  enable: true
```

### Why only three switches

`FUNC_GRID_PEAK_SHAVING`, `FUNC_GEN_PEAK_SHAVING` and `FUNC_ACTIVE_POWER_LIMIT_MODE` belong to
the HR[179] block, which a local Modbus integration does **not** expose — so there is no second
way to change them.

The other bits this integration can read overlap with settings a local Modbus integration
already owns. Those deliberately have **no** `switch` entity, because two integrations writing
the same inverter setting is how you get them fighting each other. Use the `set_bit` service if
you genuinely need one, and pick a single source of truth for each setting.

Switches report `unavailable` when the cloud has not returned the bit map, rather than guessing
a state — so a stale `off` is never mistaken for a real one.

---

## Notes and limitations

- **Unofficial API.** Everything here was reverse engineered from the LuxCloud Android app
  (4.9.8) and verified against a live account. LuxPower can change or restrict it at any time
  without notice. The AES key used for one refresh call is a protocol constant taken from the
  app; the integration is not affiliated with or endorsed by LuxPower.
- **Cloud only.** No local Modbus/RS485. If the dongle is offline or the vendor cloud is
  unreachable, entities go stale — `binary_sensor.*_dongle_mat_ket_noi` and the last-report
  timestamp are there to tell you that.
- **Same upload delay as the app.** The dongle pushes to the cloud on its own schedule, so a
  fast `scan_interval` does not make the data younger.
- **Firmware check is a hint, not an instruction.** The catalogue lists the newest package per
  device type (e.g. `08`) while the inverter reports its own `fwVersion` (e.g. `3`). Cross-check
  the code (`CHAA-000303`) in the app before flashing anything — the `caveat` attribute records
  this warning on the entity.
- **Account sharing.** Like the phone app, this integration logs into your cloud account. A
  session is refreshed transparently; if you see intermittent auth errors while the app is
  open, increase the scan interval.
- **Writes go through the vendor cloud.** A write is only as reliable as the cloud→datalogger
  link: it needs the dongle online, and it takes a few seconds to show up in the reading. A
  rejected write raises an error in Home Assistant instead of silently pretending it worked.
- **Writing is only tested on one inverter model.** The read path is verified broadly; the
  write endpoints (`remoteSet/functionControl`) were confirmed on a single `CHAA` 6.5 kW unit.
  Treat the first write on a different model as something to watch.

---

## Troubleshooting

| Symptom | Check |
|---|---|
| Cannot connect during setup | Region (try the one your app uses), then confirm the inverter shows online in the app |
| Invalid auth | Password is case sensitive; Google/Apple sign-ins need a password set first |
| Entities unavailable | The dongle is offline — power, network or unplugged |
| Values frozen | Compare `binary_sensor.*_dongle_mat_ket_noi` and the last cloud report timestamp |
| No firmware found | Device type is derived from the firmware code prefix; open an issue with your `fwCode` |

---

## Roadmap

| Phase | Content | State |
|---|---|---|
| 1 | Read-only: health, faults, BMS, power, energy, firmware, day curve, totals, config bits | ✅ shipped as `v1.0.0` |
| 2 | `switch` for HR[179] config bits, `button`s for quick charge/discharge, `set_bit` service | ✅ shipped |
| 3 | Options polish, more translations, HACS default submission | ⏳ planned |

Writes stay deliberately narrow: only the settings the cloud owns, and only bits a local Modbus
integration does not already control.

---

## Removing

**Settings → Devices & Services → LuxCloud → ⋮ → Delete.** Entities and both devices are
removed; your account and the inverter settings are untouched.

## Development

All tooling runs from the repository root and needs no third-party packages beyond
`paramiko` (SSH deploy) and Node 22+ (WebSocket helper):

| Command | Purpose |
|---|---|
| `python tools/deploy_to_ha.py --restart` | push `custom_components/luxcloud_ha/` to a Home Assistant host over SSH, verify every file by md5, then restart and wait for it to come back |
| `python tools/verify_live.py` | acceptance check: config entry, all 36 entities, the inverter↔dongle device link, and the count of deprecation/error lines **after the last boot only** |
| `python tools/hass.py cfgcheck` | run `check_config` inside the Home Assistant container |
| `python tools/make_brand.py` | regenerate `brand/{icon,icon@2x,logo}.png` with the standard library |
| `python tools/setup_tests.py --run` | build the test virtualenv and run the suite |

### Tests

`tests/` holds 255 tests. Besides the read path (cloud-response normalisation — mV, ×10,
0.1 kWh, the `"False"` string booleans — every entity's value function, the coordinator's
slow-key cache, the config/reauth flows, and a full setup asserting every entity id and the
dongle→inverter device link), the write path is covered by pressing the **actual Home
Assistant services** (`switch.turn_on`, `button.press`, `luxcloud_ha.set_bit`) and asserting
both the command sent to the cloud and the resulting entity state — including rejected writes,
bad bit names, and the refusal to guess which inverter to write to when several are configured.

Three areas have their own files because they are easy to get subtly wrong:

- **`test_diagnostics.py`** serialises the diagnostics payload and scans it for the password,
  account e-mail, serial numbers and plant name, so a future field cannot quietly leak them.
  It also asserts the dump still carries the readings needed to debug.
- **`test_options_flow.py`** drives the real options flow and checks the entry actually reloads
  and the coordinator picks up the new interval — not just that the schema accepts a number.
- **`test_availability.py`** checks that entities go `unavailable` when the cloud fails
  (rather than silently keeping the last reading), recover afterwards, and that an auth failure
  starts a reauth flow.

The manifest and the config/service strings are verified through Home Assistant's own loader
and translation helper — including the bronze `config-flow` rule that every field carries a
`data_description`, checked against the flow's real schema rather than a hardcoded list.

```bash
python tools/setup_tests.py --run     # builds .venv, installs deps, runs pytest
```

`requirements_test.txt` pins `pytest-homeassistant-custom-component`, which pins
`homeassistant` to an exact version (0.13.367 → 2026.9.4) — bump that one line to move
the suite to a new HA release.

> **Windows.** Home Assistant's test harness imports the POSIX-only `fcntl` and `resource`
> modules, and blocks sockets in a way Windows' asyncio event loop cannot work around.
> `tools/setup_tests.py` drops small stubs into `.venv` (from `tools/win32_stubs/`) and
> `tests/conftest.py` relaxes the socket guard — **both only when running on Windows**.
> On Linux nothing is relaxed and the tests still cannot open a real socket.

Copy `.env.example` to `.env` and fill in the host, SSH password and a long-lived access
token. `.env` is git-ignored.

Two Home Assistant deprecations are already handled here and will stop working in **2027.8**
if they regress: `via_device_id` instead of `via_device`, and `async_get_device_id_by_identifier`
instead of `DeviceRegistry.async_get_device`.

### Quality scale

`manifest.json` declares `quality_scale: bronze`, and the [Bronze rules][qs-checklist] were
audited against the code rather than assumed:

| Rule | Where |
|---|---|
| `action-setup` | service registered in `async_setup` |
| `appropriate-polling` | scan interval configurable 60–3600 s |
| `brands` | `custom_components/luxcloud_ha/brand/` |
| `config-flow` (+ `data_description`) | every field described; enforced by a test against the flow's real schema |
| `config-flow-test-coverage` | `tests/test_config_flow.py` |
| `dependency-transparency` | `requirements: []` — stdlib plus HA only |
| `docs-*` | this README (actions, description, install, removal, limitations) |
| `entity-unique-id`, `has-entity-name` | asserted in `tests/test_setup.py` |
| `runtime-data` | `entry.runtime_data` |
| `test-before-configure`, `test-before-setup` | login probed in the config flow; `ConfigEntryNotReady`/`ConfigEntryAuthFailed` on setup |
| `unique-config-entry` | `async_set_unique_id` + `_abort_if_unique_id_configured` |

`docs-triggers` and `docs-conditions` do not apply — this integration registers neither.
Home Assistant reports `quality_scale: custom` for any non-core integration, so the manifest
value is documentation for readers and HACS, not something HA enforces.

[qs-checklist]: https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/

## License

[MIT](LICENSE) © 2026 ngoviet
