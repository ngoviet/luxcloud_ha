# LuxCloud (LuxPower Cloud API) — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/ngoviet/luxcloud-ha.svg)](https://github.com/ngoviet/luxcloud-ha/releases)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2026.9%2B-41BDF5)](https://www.home-assistant.io)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ngoviet&repository=luxcloud-ha&category=integration)

Reads your **LuxPower** hybrid inverter through the **LuxCloud** cloud API — the same data the
phone app shows, including the parts a local Modbus connection cannot see: dongle health,
localised fault history, BMS cell detail, the firmware catalogue, the intraday power curve,
yearly totals and the HR[179] configuration bits.

> **Phase 1 — read-only.** 29 entities, 2 devices. No switch/number/select platforms yet;
> the write path (configuration bits, quick charge/discharge) is the next milestone.
> See [Roadmap](#roadmap).

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

- **29 entities across 2 devices** — one device per inverter, plus the datalogger as a
  separate device linked with `via_device`.
- **Config flow with validation** — credentials and serial are verified during setup, plus a
  reauth step and an options step (no YAML at all).
- **Adjustable polling** — 60 s to 3600 s (default 300 s).
- **Slow-key scheduling** — firmware catalogue, intraday curve and yearly totals are fetched
  every 6th poll (~30 min), so the fast path stays cheap.
- **Diagnostics support** — download a redacted config dump from the UI.
- **No third-party dependencies** — stdlib plus Home Assistant itself (`requirements: []`).
- **Real fault text** — the cloud returns already-localised fault strings (Vietnamese here),
  no client-side translation table to maintain.

---

## Requirements

| Requirement | Details |
|---|---|
| Home Assistant | 2026.9 or newer (verified on 2026.9.3) |
| Python | 3.14 (shipped with that HA release) |
| LuxPower account | The account you use in the LuxCloud app |
| Inverter | LuxPower hybrid with a WiFi/LAN datalogger that is online |

---

## Installation

### HACS (custom repository)

1. HACS → **⋮ → Custom repositories**
2. Add `https://github.com/ngoviet/luxcloud-ha` with category **Integration**
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
| 1 | Read-only: health, faults, BMS, power, energy, firmware, day curve, totals, config bits | ✅ shipped |
| 2 | `switch` for HR[179] config bits, `button`/services for quick charge/discharge and `set_bit` | ⏳ planned |
| 3 | Options polish, translations, HACS default submission | ⏳ planned |

Until phase 2 lands, write access stays out of the integration on purpose: an integration that
can quietly change inverter settings needs the register map verified on more than one device
type first.

---

## Removing

**Settings → Devices & Services → LuxCloud → ⋮ → Delete.** Entities and both devices are
removed; your account and the inverter settings are untouched.

## License

[MIT](LICENSE) © 2026 ngoviet
