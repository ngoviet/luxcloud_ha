# LuxCloud cho Home Assistant

<!-- readme-axi type=ha -->

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![GitHub release](https://img.shields.io/github/release/ngoviet/luxcloud_ha.svg)](https://github.com/ngoviet/luxcloud_ha/releases)
[![Test](https://github.com/ngoviet/luxcloud_ha/actions/workflows/test.yml/badge.svg)](https://github.com/ngoviet/luxcloud_ha/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![HA Version](https://img.shields.io/badge/Home%20Assistant-2026.9%2B-41BDF5)](https://www.home-assistant.io)
[![Python](https://img.shields.io/badge/python-3.14%2B-blue)](https://www.python.org)

[English](README.md) · **Tiếng Việt**

Đọc dữ liệu **inverter hybrid LuxPower** của bạn qua cloud API **LuxCloud** (LuxPower Cloud API) —
đúng dữ liệu app điện thoại hiển thị, kể cả những phần kết nối Modbus cục bộ không thấy được:
tình trạng dongle, lịch sử sự cố có chữ theo ngôn ngữ của bạn, chi tiết cell BMS, danh mục
firmware, đường cong công suất trong ngày, tổng theo năm và các bit cấu hình HR[179]. Integration
cũng **ghi** được vài thiết lập mà chỉ cloud mới cho phép.

[![Mở Home Assistant của bạn và mở một kho trong Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=ngoviet&repository=luxcloud_ha&category=integration)

> 🇻🇳 Dự án do một người Việt tự xây dựng và duy trì — nếu nó giúp ích cho bạn, hãy
> [ủng hộ dự án](#ủng-hộ-dự-án).

## Mục lục

- [Tính năng](#tính-năng)
- [Yêu cầu](#yêu-cầu)
- [Cài đặt](#cài-đặt)
- [Cấu hình](#cấu-hình)
- [Thực thể](#thực-thể)
- [Ghi xuống inverter](#ghi-xuống-inverter)
- [Xử lý sự cố](#xử-lý-sự-cố)
- [Cách hoạt động](#cách-hoạt-động)
- [Lộ trình](#lộ-trình)
- [Phát triển](#phát-triển)

## Tính năng

**55 entity, 2 thiết bị.** 48 entity chỉ đọc, cộng 3 entity `switch` cho các bit cấu hình
HR[179] mà integration Modbus cục bộ không có, 4 `button` cho quick charge/discharge, và dịch vụ
`luxcloud_ha.set_bit`. Xem [Ghi xuống inverter](#ghi-xuống-inverter).

- **55 entity trên 2 thiết bị** — mỗi inverter một thiết bị, cộng datalogger là một thiết bị
  riêng liên kết bằng `via_device`.
- **Config flow có kiểm tra** — thông tin đăng nhập và số serial được xác minh khi thiết lập,
  kèm bước reauth và bước options (hoàn toàn không cần YAML).
- **Chu kỳ poll điều chỉnh được** — 60 giây đến 3600 giây (mặc định 300 giây).
- **Điện năng theo kỳ hoá đơn** — PV, mua lưới, sạc/xả pin, EPS và tiêu thụ của kỳ hoá đơn hiện
  tại và năm dương lịch, tiền tiết kiệm tính bằng VND, và điện tiêu thụ chốt của hôm qua, lấy từ
  bảng `monthColumn`/`yearColumn` của cloud (làm mới mỗi lần poll). Ngày bắt đầu kỳ là một tuỳ
  chọn (`1` = tháng dương lịch; ví dụ `27` = ngày 27 → ngày 26 như kỳ ghi chỉ số công tơ của EVN).
- **Lịch cho các khoá chậm** — danh mục firmware, đường cong trong ngày và tổng theo năm được lấy
  mỗi 6 lần poll (~30 phút), để đường nhanh luôn nhẹ.
- **Chỉ ghi những gì cloud quản lý** — 3 entity `switch` cùng các `button` quick
  charge/discharge và dịch vụ `set_bit`. Các lệnh ghi được xếp tuần tự, nên hai lệnh bắn ra cùng
  lúc sẽ đến cloud đúng thứ tự bạn yêu cầu.
  Xem [Ghi xuống inverter](#ghi-xuống-inverter).
- **Hỗ trợ diagnostics** — tải bản dump cấu hình từ giao diện, với tài khoản, mật khẩu, số serial
  và tên plant được thay bằng `**REDACTED**`, nên tệp an toàn để đính kèm vào issue. Số đo thô,
  trạng thái bit và mã firmware được giữ lại, vì đó là thứ làm bản dump có ích. Nó cũng báo trạng
  thái coordinator — lần poll thành công gần nhất là lúc nào, lỗi gần nhất, và bao nhiêu lần poll
  liên tiếp đã lỗi — giúp phân biệt cloud chập chờn với thiết lập bị hỏng mà không cần lục log.
- **Không phụ thuộc bên thứ ba** — chỉ thư viện chuẩn và chính Home Assistant (`requirements: []`).
- **Chữ sự cố thật** — cloud trả về chuỗi sự cố đã bản địa hoá sẵn (ở đây là tiếng Việt), không
  phải duy trì bảng dịch phía client.

## Yêu cầu

| Yêu cầu | Chi tiết |
|---|---|
| Home Assistant | 2026.9 trở lên (đã kiểm tra trên 2026.9.3 và, sau khi tự cập nhật, trên 2026.9.4) |
| Python | 3.14 (đi kèm bản HA đó) |
| Tài khoản LuxPower | Tài khoản bạn dùng trong app LuxCloud |
| Inverter | Inverter hybrid LuxPower có datalogger WiFi/LAN đang online |

## Cài đặt

### HACS (custom repository)

1. HACS → **⋮ → Custom repositories**
2. Thêm `https://github.com/ngoviet/luxcloud_ha` với category **Integration**
3. Tìm **LuxCloud**, cài đặt
4. Khởi động lại Home Assistant

### Cài thủ công

Chép `custom_components/luxcloud_ha/` vào thư mục `config/custom_components/` của Home Assistant
rồi khởi động lại.

### Gỡ bỏ

**Settings → Devices & Services → LuxCloud → ⋮ → Delete.** Các entity và cả hai thiết bị bị xoá;
tài khoản của bạn và thiết lập trên inverter không bị đụng tới.

## Cấu hình

**Settings → Devices & Services → Add Integration → LuxCloud**

| Trường | Ghi chú |
|---|---|
| Account | E-mail bạn dùng để đăng nhập app LuxCloud |
| Password | Mật khẩu tài khoản LuxPower |
| Inverter serial number | Ví dụ `61204F0266`; cũng xem được trong app ở Device → Info |
| Region | `vn` (mặc định), `as`, `na`, `eu2`, `ind`, `af`, `phi`, `us` — mỗi entry một region |
| Scan interval | Số giây giữa các lần poll, 60–3600 (mặc định 300) |

Sau này, trong **Configure** trên thẻ integration (không cần khởi động lại):

| Tuỳ chọn | Ghi chú |
|---|---|
| Scan interval | Đổi chu kỳ poll |
| Enable series | Đường cong công suất trong ngày + tổng theo năm |
| Enable firmware | Tra danh mục firmware (luôn dùng host `as`) |
| Billing day | Ngày đầu kỳ hoá đơn cho các sensor `*_thang`, 1–28 (mặc định 1 = tháng dương lịch) |

Nhiều inverter: thêm integration một lần cho mỗi số serial. Mỗi entry giữ phiên cloud riêng, nên
hai inverter — kể cả trên hai tài khoản khác nhau — không đăng xuất lẫn nhau. Với tài khoản có
nhiều plant, integration đọc đúng plant chứa số serial bạn đã nhập.

> **Region quan trọng.** Danh mục firmware chỉ trả lời trên host `as` — các host theo vùng trả về
> 0 dòng. Việc này được xử lý bên trong; thiết lập region chỉ dành cho API chính.

## Thực thể

### Thiết bị 1 — inverter

| Entity | Đơn vị | Ghi chú |
|---|---|---|
| `sensor.*_chu_ky_pin` | | Số chu kỳ pin |
| `sensor.*_lech_cell` | mV | Điện áp cell cao nhất − thấp nhất |
| `sensor.*_cell_cao_nhat` / `_cell_thap_nhat` | mV | Điện áp cell cao nhất / thấp nhất |
| `sensor.*_nhiet_do_cell_cao_nhat` / `_nhiet_do_cell_thap_nhat` | °C | Nhiệt độ cell cao nhất / thấp nhất |
| `sensor.*_trang_thai_bms` | | Trạng thái BMS (`Charging`, …) |
| `sensor.*_ngo_ra_ac_pinv` | W | Công suất ngõ ra AC |
| `sensor.*_rectifier_prec` | W | Công suất rectifier / sạc từ AC |
| `sensor.*_su_co_gan_nhat` | | Sự cố gần nhất, chữ do máy chủ bản địa hoá |
| `sensor.*_co2_giam` / `_than_giam` / `_tuong_duong_cay` | t / kg / cây | CO₂, than giảm được và số cây tương đương từ trước tới nay |
| `sensor.*_ma_firmware_inverter` | | Mã firmware, ví dụ `CHAA-000303` |
| `sensor.*_firmware_moi_nhat` | | Phiên bản mới nhất trong danh mục cho loại thiết bị này |
| `sensor.*_chuoi_cong_suat_hom_nay` | | Số điểm trong ngày (đường cong nằm trong attributes) |
| `sensor.*_tong_theo_nam` | kWh | Tổng PV năm hiện tại (mọi năm nằm trong attributes); về 0 mỗi tháng Một |
| `sensor.*_bit_cau_hinh_hr_179_dang_bat` | | Số bit HR[179] đang bật (bảng bit trong attributes) |
| `sensor.*_trang_thai_quick_charge_discharge` | | Trạng thái quick charge/discharge phía cloud |
| `sensor.*_tong_san_luong_plant` | kWh | Tổng sản lượng của plant từ trước tới nay (đổi sang kWh khi cloud báo `MWh`) |
| `sensor.*_{pv,mua_luoi,sac_pin,xa_pin,eps,tieu_thu}_thang` | kWh | PV / mua lưới / sạc / xả / EPS / tiêu thụ trong **kỳ hoá đơn** hiện tại (`start`/`end` trong attributes); `state_class: total` với `last_reset` = ngày đầu kỳ |
| `sensor.*_{pv,mua_luoi,sac_pin,xa_pin,eps,tieu_thu}_nam` | kWh | Cùng sáu chỉ số, năm dương lịch hiện tại; `last_reset` = 1 tháng Một |
| `sensor.*_tiet_kiem_thang` / `_tiet_kiem_nam` | VND | Tiền tiết kiệm: biểu giá bậc thang EVN (QĐ 4495/QĐ-BCT, 6 bậc) + 8 % VAT trên tổng tiêu thụ **trừ đi** phần tương tự trên điện mua lưới |
| `sensor.*_tieu_thu_hom_qua` | kWh | Điện tiêu thụ hôm qua do cloud chốt (các chỉ số khác + ngày trong attributes); ngày mùng 1 thì đọc tháng trước |
| `sensor.*_dien_ap_luoi` / `_tan_so_luoi` | V / Hz | Điện áp / tần số lưới ở ngõ vào inverter (`vacr`/10, `fac`/100) — `0` khi mất điện là một số đo, không phải unknown |
| `sensor.*_ma_trang_thai_inverter` | | Bitmask `runtime.status` thô (`0x40`/`0x80` = không lưới), `status_text` trong attributes |
| `sensor.*_du_lieu_inverter_luc` | | Giờ đồng hồ inverter gắn trên bản runtime cloud đang giữ — dùng `now − giá trị này` làm tuổi **thật** của số đo lưới (nó ngừng chạy khi dongle offline) |
| `switch.*_grid_peak_shaving` | | `FUNC_GRID_PEAK_SHAVING` — **có ghi** (xem bên dưới) |
| `switch.*_gen_peak_shaving` | | `FUNC_GEN_PEAK_SHAVING` — **có ghi** |
| `switch.*_active_power_limit_mode` | | `FUNC_ACTIVE_POWER_LIMIT_MODE` — **có ghi** |
| `button.*_quick_charge_start` / `_quick_charge_stop` | | Buộc sạc pin (phía cloud) — **có ghi** |
| `button.*_quick_discharge_start` / `_quick_discharge_stop` | | Buộc xả pin (phía cloud) — **có ghi** |
| `binary_sensor.*_su_co_dang_hieu_luc` | | Đang có sự cố |
| `binary_sensor.*_dang_chay_quick_charge_discharge` | | Đang chạy tác vụ quick charge/discharge |
| `binary_sensor.*_co_firmware_moi` | | Có firmware mới hơn bản đang cài |
| `binary_sensor.*_dang_chay_khong_luoi_eps` | | Đang chạy không lưới — suy ra từ `runtime.status & 0xC0` (bit `0x40`/`0x80`), **không** phải từ khoá `isOffGrid` vốn không tồn tại (sửa ngày 2026-09-30). Hiển thị `unknown` — không phải `on` — khi cloud không trả về số đo lưới (từ `v1.2.3`). Trên các hệ thống đã có entity này từ trước, registry giữ entity_id cũ `..._isoffgrid`. |
| `binary_sensor.*_cloud_co_du_lieu` | | Cloud đã trả về dữ liệu runtime dùng được |

### Thiết bị 2 — datalogger (liên kết bằng `via_device`)

| Entity | Ghi chú |
|---|---|
| `sensor.*_dongle_firmware` | Firmware datalogger, ví dụ `V2.11` |
| `sensor.*_dongle_bao_cloud_lan_cuoi` | Thời điểm lần gửi lên cloud gần nhất |
| `sensor.*_dongle_kieu_ket_noi` | Loại datalogger, ví dụ `E Wi-Fi` |
| `binary_sensor.*_dongle_mat_ket_noi` | `on` = datalogger offline; hiển thị là **Problem** / **OK** |

> Entity ID dùng tên thiết bị (`LuxCloud`) làm tiền tố, nên id có dạng
> `sensor.luxcloud_chu_ky_pin`. Cứ thoải mái đổi tên thiết bị trong Home Assistant — entity id
> sẽ đổi theo.

## Ghi xuống inverter

Mọi thứ dưới đây là **ghi thật** — cloud → datalogger → inverter, đúng như app điện thoại làm khi
bạn bật/tắt một trong các mục này ở màn hình cài đặt. Không có mục nào ghi register cục bộ.

| Gì | Bằng cách nào |
|---|---|
| `FUNC_GRID_PEAK_SHAVING`, `FUNC_GEN_PEAK_SHAVING`, `FUNC_ACTIVE_POWER_LIMIT_MODE` | 3 entity `switch` |
| Quick charge / quick discharge | 4 entity `button` (mỗi loại `start`/`stop`) |
| Bất kỳ bit HR[179] nào khác | Dịch vụ `luxcloud_ha.set_bit` |

```yaml
service: luxcloud_ha.set_bit
target:
  device_id: 1a2b3c...        # không bắt buộc khi chỉ cấu hình một inverter
data:
  function: FUNC_RSD_DISABLE
  enable: true
```

### Vì sao chỉ có ba switch

`FUNC_GRID_PEAK_SHAVING`, `FUNC_GEN_PEAK_SHAVING` và `FUNC_ACTIVE_POWER_LIMIT_MODE` thuộc khối
HR[179], mà integration Modbus cục bộ **không** có — nên không có cách thứ hai để đổi chúng.

Các bit khác mà integration này đọc được trùng với những thiết lập integration Modbus cục bộ đã
quản lý. Những bit đó cố ý **không** có entity `switch`, vì hai integration cùng ghi một thiết lập
của inverter chính là cách để chúng giành giật nhau. Hãy dùng dịch vụ `set_bit` nếu thật sự cần, và
chọn một nguồn sự thật duy nhất cho mỗi thiết lập.

Switch báo `unavailable` khi cloud chưa trả về bảng bit, thay vì đoán trạng thái — nên một `off`
cũ không bao giờ bị nhầm là `off` thật.

## Xử lý sự cố

| Triệu chứng | Kiểm tra |
|---|---|
| Không kết nối được khi thiết lập | Region (thử region app của bạn đang dùng), rồi xác nhận inverter đang online trong app |
| Invalid auth | Mật khẩu phân biệt hoa thường; tài khoản đăng nhập bằng Google/Apple cần đặt mật khẩu trước |
| Entity unavailable | Dongle offline — mất điện, mất mạng hoặc bị rút |
| "Re-authentication required" | Đã đổi mật khẩu trong app — nhập mật khẩu mới vào thông báo; integration tự nạp lại |
| Giá trị đứng yên | So sánh `binary_sensor.*_dongle_mat_ket_noi` với thời điểm báo cloud gần nhất |
| Không tìm thấy firmware | Loại thiết bị được suy ra từ tiền tố mã firmware; mở issue kèm `fwCode` của bạn |

### Ghi chú và giới hạn

- **API không chính thức.** Mọi thứ ở đây được reverse engineer từ app LuxCloud Android (4.9.8)
  và kiểm chứng trên một tài khoản thật. LuxPower có thể thay đổi hoặc hạn chế nó bất cứ lúc nào
  mà không báo trước. Khoá AES dùng cho một lệnh làm mới là hằng số giao thức lấy từ app;
  integration không liên kết hay được LuxPower bảo trợ.
- **Chỉ qua cloud.** Không có Modbus/RS485 cục bộ. Nếu không kết nối được cloud của hãng, entity
  chuyển sang `unavailable` thay vì giữ số đo cuối; `binary_sensor.*_dongle_mat_ket_noi` và thời
  điểm báo gần nhất cho biết dữ liệu trên cloud thực sự mới tới đâu.
- **Độ trễ gửi lên giống app.** Dongle đẩy lên cloud theo lịch riêng, nên `scan_interval` nhanh
  không làm dữ liệu mới hơn.
- **Kiểm tra firmware là gợi ý, không phải chỉ dẫn.** Danh mục liệt kê gói mới nhất theo loại
  thiết bị (ví dụ `08`) trong khi inverter báo `fwVersion` riêng (ví dụ `3`). Hãy đối chiếu mã
  (`CHAA-000303`) trong app trước khi nạp bất cứ thứ gì — attribute `caveat` ghi lại cảnh báo này
  trên entity.
- **Dùng chung tài khoản.** Giống app điện thoại, integration đăng nhập vào tài khoản cloud của
  bạn. Khi phiên cloud hết hạn, lần poll sau tự đăng nhập lại — không cần reload. Nếu mật khẩu đã
  đổi, Home Assistant yêu cầu nhập lại và nạp lại integration ngay khi bạn nhập. Nếu thấy lỗi xác
  thực lúc có lúc không khi đang mở app, hãy tăng scan interval.
- **Lệnh ghi đi qua cloud của hãng.** Lệnh ghi chỉ tin cậy bằng đường cloud→datalogger: cần dongle
  online, và mất vài giây mới thấy trong số đọc. Lệnh ghi bị từ chối sẽ báo lỗi trong Home
  Assistant thay vì lặng lẽ giả vờ đã thành công.
- **Lệnh ghi mới chỉ được thử trên một model inverter.** Đường đọc đã được kiểm chứng rộng; các
  endpoint ghi (`remoteSet/functionControl`) mới được xác nhận trên một máy `CHAA` 6.5 kW. Lần ghi
  đầu tiên trên model khác thì nên theo dõi kỹ.

## Cách hoạt động

### Vì sao dùng cloud khi đã có Modbus cục bộ?

Cả hai đường đều tới cùng một inverter, nhưng mang dữ liệu khác nhau. Integration này **không**
thay thế integration cục bộ — nó lấp những chỗ trống mà integration cục bộ không truy cập được.

| Dữ liệu | Modbus cục bộ (ví dụ `lxp_modbus`) | Integration này (cloud) |
|---|---|---|
| Công suất / điện áp / SOC trực tiếp | ✅ thời gian thực | ✅ nhưng trễ theo chu kỳ gửi của dongle |
| Đọc/ghi toàn bộ register, thiết lập | ✅ | ⛔ chỉ những gì app cho phép |
| Kết nối dongle + lần báo cloud gần nhất | ⛔ | ✅ `lost`, `lastUpdateTime` |
| Lịch sử sự cố có chữ đã bản địa hoá | ⛔ | ✅ (máy chủ trả chữ theo ngôn ngữ app của bạn) |
| Danh mục firmware + kiểm tra phiên bản | ⛔ | ✅ theo từng loại thiết bị |
| Đường cong công suất trong ngày, tổng theo năm | ⛔ | ✅ |
| Điện năng theo kỳ hoá đơn / năm + tiền tiết kiệm, tổng chốt của hôm qua | ⛔ (chỉ có bộ đếm tự dựng) | ✅ từ chính bảng ngày/tháng của cloud |
| Điện áp & nhiệt độ cell min/max của BMS, số chu kỳ | một phần | ✅ |
| Hoạt động khi inverter ở mạng khác | ⛔ | ✅ |

**Không** cần truy cập mạng cục bộ tới inverter. Chỉ cần kết nối internet và tài khoản cloud
LuxPower.

## Lộ trình

| Giai đoạn | Nội dung | Trạng thái |
|---|---|---|
| 1 | Chỉ đọc: tình trạng, sự cố, BMS, công suất, điện năng, firmware, đường cong ngày, tổng, bit cấu hình | ✅ phát hành ở `v1.0.0` |
| 2 | `switch` cho bit cấu hình HR[179], `button` cho quick charge/discharge, dịch vụ `set_bit` | ✅ phát hành ở `v1.1.0` |
| 2.1 | Gia cố: lệnh ghi xếp tuần tự để hai lệnh không chen nhau, trạng thái coordinator trong diagnostics, mẫu issue | ✅ phát hành ở `v1.2.0` |
| 2.2 | Sửa cờ `off_grid`: suy ra từ `runtime.status & 0xC0` — khoá `isOffGrid` mà code cũ đọc không tồn tại trong API, nên cờ bị kẹt `off` kể cả khi mất lưới thật | ✅ phát hành ở `v1.2.1` |
| 2.3 | Sửa độ tin cậy: tự đăng nhập lại khi phiên cloud hết hạn (trước đây poll lỗi cho tới khi reload tay); cookie jar riêng cho mỗi entry; chọn đúng plant/dongle chứa số serial đã cấu hình trên tài khoản nhiều plant; reauth nạp lại entry; tôn trọng scan interval chọn lúc thiết lập; `dongle_mat_ket_noi` hiển thị "Problem" thay vì "Connected" bị đảo ngược; tổng theo năm không còn ghi điện năng âm lúc sang năm mới; tổng plant hiểu `MWh`; lỗi 401 đăng nhập lại trước khi hỏi mật khẩu; các lệnh đọc chạy song song (tối đa 4 cùng lúc) và không còn lấy dữ liệu firmware/series đã tắt | ✅ `v1.2.2` |
| 2.4 | Thiếu dữ liệu thì là `unknown`, không phải giá trị giả: cờ không lưới không còn bật `on` khi chỉ request runtime lỗi; "firmware mới" không còn bật `on` khi thiếu `fwVersion` của inverter; `pinv`/`prec` và các sensor BMS (chu kỳ, điện áp cell, độ lệch cell, nhiệt độ cell) không còn ghi `0` khi cloud bỏ trống — một số 0 giả trên bộ đếm chu kỳ `TOTAL_INCREASING` bị hiểu là công tơ reset và làm hỏng thống kê dài hạn | ✅ `v1.2.3` |
| 2.5 | Lệnh ghi vượt qua được phiên cloud hết hạn: switch, button và `set_bit` đăng nhập lại và gửi lại một lần thay vì lỗi tới lần poll sau, và sai mật khẩu khi ghi sẽ báo lỗi dễ đọc và mở luồng reauth (trước đây hiện thành "Unknown error"); thiết lập và reauth từ chối số serial mà tài khoản không có (trước đây vẫn nhận và để mọi entity inverter trống); sau nửa đêm đường cong công suất "hôm nay" không còn hiện dữ liệu hôm qua; thêm nhiều trường hợp thiếu dữ liệu thành `unknown` thay vì giá trị giả — mất dongle, trạng thái/cờ quick task, số bit cấu hình, và firmware mới nhất trong danh mục (trước là `-1`) | ✅ `v1.2.4` |
| 2.6 | Điện năng theo kỳ hoá đơn và theo năm (PV, mua lưới, sạc, xả, EPS, tiêu thụ), tiền tiết kiệm bằng VND, điện tiêu thụ chốt hôm qua, và sensor điện áp / tần số / trạng thái / thời điểm runtime của lưới — đủ để bỏ trình lấy dữ liệu `command_line`; tuỳ chọn mới `billing_day` | ✅ `v1.3.0` |
| 3 | Hoàn thiện options, thêm bản dịch | ⏳ dự kiến |

Việc đưa lên kho mặc định của HACS cố ý **không** nằm trong kế hoạch: integration này nói chuyện
với một cloud API không chính thức, được reverse engineer, nên có mặt trong kho mặc định sẽ ngầm
hứa một sự ổn định mà nó không giữ được, và nó là bạn đồng hành của integration Modbus cục bộ chứ
không thay thế, nên đối tượng dùng hẹp hơn những gì một mục trong kho mặc định gợi ý. Bạn không mất
gì cả — cài và cập nhật qua HACS custom repository dùng cùng một đường code.

Lệnh ghi được cố ý giữ hẹp: chỉ những thiết lập do cloud quản lý, và chỉ những bit mà integration
Modbus cục bộ chưa điều khiển.

## Phát triển

Mọi công cụ chạy từ thư mục gốc của kho và không cần gói bên thứ ba nào ngoài `paramiko` (deploy
qua SSH) và Node 22+ (trợ giúp WebSocket):

| Lệnh | Mục đích |
|---|---|
| `python tools/deploy_to_ha.py --restart` | đẩy `custom_components/luxcloud_ha/` lên máy Home Assistant qua SSH, kiểm tra từng tệp bằng md5, rồi khởi động lại và chờ nó chạy lại |
| `python tools/verify_live.py` | kiểm tra nghiệm thu: config entry, đủ 55 entity, liên kết thiết bị inverter↔dongle, và số dòng deprecation/lỗi **chỉ tính sau lần khởi động gần nhất** |
| `python tools/hass.py cfgcheck` | chạy `check_config` bên trong container Home Assistant |
| `python tools/make_brand.py` | tạo lại `brand/{icon,icon@2x,logo}.png` bằng thư viện chuẩn |
| `python tools/setup_tests.py --run` | dựng virtualenv test và chạy bộ test |

### Test

`tests/` có 322 test. Ngoài đường đọc (chuẩn hoá phản hồi cloud — mV, ×10, 0.1 kWh, các boolean
dạng chuỗi `"False"` — hàm giá trị của mọi entity, cache khoá chậm của coordinator, luồng
config/reauth, và một lần thiết lập đầy đủ kiểm tra mọi entity id cùng liên kết thiết bị
dongle→inverter), đường ghi được kiểm tra bằng cách gọi **đúng các service của Home Assistant**
(`switch.turn_on`, `button.press`, `luxcloud_ha.set_bit`) và kiểm tra cả lệnh gửi lên cloud lẫn
trạng thái entity sau đó — gồm cả lệnh ghi bị từ chối, tên bit sai, và việc từ chối đoán inverter
nào để ghi khi có nhiều inverter được cấu hình.

Ba vùng có tệp riêng vì dễ sai một cách khó thấy:

- **`test_diagnostics.py`** tuần tự hoá payload diagnostics rồi quét tìm mật khẩu, e-mail tài
  khoản, số serial và tên plant, để một trường mới sau này không thể lặng lẽ làm lộ chúng. Nó cũng
  kiểm tra bản dump vẫn mang các số đo cần để gỡ lỗi.
- **`test_options_flow.py`** chạy options flow thật và kiểm tra entry thật sự nạp lại và
  coordinator nhận chu kỳ mới — không chỉ là schema chấp nhận một con số.
- **`test_availability.py`** kiểm tra entity chuyển sang `unavailable` khi cloud lỗi (thay vì lặng
  lẽ giữ số đo cuối), phục hồi sau đó, và lỗi xác thực mở luồng reauth.

Manifest và các chuỗi config/service được kiểm tra qua chính loader và trình trợ giúp bản dịch
của Home Assistant — kể cả quy tắc bronze `config-flow` rằng mọi trường phải có
`data_description`, đối chiếu với schema thật của flow thay vì một danh sách gán cứng.

```bash
python tools/setup_tests.py --run     # dựng .venv, cài dependency, chạy pytest
```

`requirements_test.txt` ghim `pytest-homeassistant-custom-component`, gói này lại ghim
`homeassistant` vào một phiên bản chính xác (0.13.367 → 2026.9.4) — chỉ cần nâng dòng đó để chuyển
bộ test sang bản HA mới.

> **Windows.** Bộ khung test của Home Assistant import các module chỉ có trên POSIX là `fcntl` và
> `resource`, và chặn socket theo cách mà event loop asyncio của Windows không lách được.
> `tools/setup_tests.py` thả vài stub nhỏ vào `.venv` (từ `tools/win32_stubs/`) và
> `tests/conftest.py` nới lỏng chốt chặn socket — **cả hai chỉ khi chạy trên Windows**. Trên Linux
> không có gì bị nới và test vẫn không mở được socket thật.

Chép `.env.example` thành `.env` rồi điền host, mật khẩu SSH và một long-lived access token.
`.env` đã được git bỏ qua.

Hai deprecation của Home Assistant đã được xử lý ở đây và sẽ ngừng hoạt động từ **2027.8** nếu bị
thoái lui: `via_device_id` thay cho `via_device`, và `async_get_device_id_by_identifier` thay cho
`DeviceRegistry.async_get_device`.

### Quality scale

`manifest.json` khai báo `quality_scale: bronze`, và các [quy tắc Bronze][qs-checklist] đã được
rà soát với code thay vì mặc định là đạt:

| Quy tắc | Ở đâu |
|---|---|
| `action-setup` | service đăng ký trong `async_setup` |
| `appropriate-polling` | scan interval cấu hình được 60–3600 giây |
| `brands` | `custom_components/luxcloud_ha/brand/` |
| `config-flow` (+ `data_description`) | mọi trường đều có mô tả; được một test kiểm tra theo schema thật của flow |
| `config-flow-test-coverage` | `tests/test_config_flow.py` |
| `dependency-transparency` | `requirements: []` — chỉ thư viện chuẩn và HA |
| `docs-*` | README này (actions, mô tả, cài đặt, gỡ bỏ, giới hạn) |
| `entity-unique-id`, `has-entity-name` | kiểm tra trong `tests/test_setup.py` |
| `runtime-data` | `entry.runtime_data` |
| `test-before-configure`, `test-before-setup` | thử đăng nhập trong config flow; `ConfigEntryNotReady`/`ConfigEntryAuthFailed` khi thiết lập |
| `unique-config-entry` | `async_set_unique_id` + `_abort_if_unique_id_configured` |

`docs-triggers` và `docs-conditions` không áp dụng — integration này không đăng ký cái nào. Home
Assistant báo `quality_scale: custom` cho mọi integration không thuộc core, nên giá trị trong
manifest là tài liệu cho người đọc và HACS, không phải thứ HA bắt buộc.

[qs-checklist]: https://developers.home-assistant.io/docs/core/integration-quality-scale/checklist/

<!-- support:start -->
## Ủng hộ dự án

<p align="center">
  <img src="https://raw.githubusercontent.com/ngoviet/.github/main/assets/support/banner.svg" width="720" alt="Built and maintained by one person in Việt Nam">
</p>

<p align="center">
  <a href="https://buymeacoffee.com/ngoviet"><img src="https://raw.githubusercontent.com/ngoviet/.github/main/assets/support/btn-coffee.svg" height="56" alt="Buy me a coffee"></a>
  &nbsp;
  <a href="https://github.com/sponsors/ngoviet"><img src="https://raw.githubusercontent.com/ngoviet/.github/main/assets/support/btn-sponsors.svg" height="56" alt="GitHub Sponsors"></a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/ngoviet/.github/main/assets/support/vietqr-card.svg" width="300" alt="VietQR — MB Bank — NGO DUC VIET — 911051212">
  &nbsp;
  <img src="https://raw.githubusercontent.com/ngoviet/.github/main/assets/support/crypto-card.svg" width="300" alt="Crypto — BNB Smart Chain (BEP20) — 0xcbf0402b232cb24b4d998f09a4884f87b5f74750">
</p>

<p align="center"><b>Ví tiền mã hoá, chỉ gửi qua mạng BNB Smart Chain (BEP20):</b><br><code>0xcbf0402b232cb24b4d998f09a4884f87b5f74750</code></p>

<p align="center"><sub>🇻🇳 VietQR: quét bằng app ngân hàng bất kỳ, nội dung <code>Ung ho luxcloud_ha</code>. Cảm ơn bạn đã giúp dự án tiếp tục phát triển!</sub></p>
<!-- support:end -->

## Giấy phép

[MIT](LICENSE) © Ngô Đức Việt. Không liên kết hay được LuxPower bảo trợ.
