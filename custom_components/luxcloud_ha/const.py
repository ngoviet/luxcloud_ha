"""Hằng số cho integration LuxCloud (LuxPower Cloud API — WManage).

Toàn bộ endpoint/field/đơn vị dưới đây lấy từ APK LuxCloud 4.9.8 (jadx) và
đã được ĐO THẬT trên tài khoản (2026-09-27) — xem:
  luxpower/luxcloud-4.9.8-diff.md
  luxpower/luxcloud-4.9.8-ha-integration-plan.md (§9/§10 AS-BUILT)
  _local_archive/luxcloud_apk/cloud_api_fields_498.md
"""

# Tên domain: HA chỉ cho chữ thường + số + gạch dưới — đo bằng
# `homeassistant.core.valid_domain()` trên HA 2026.9.3:
#   luxcloud -> True · luxcloud_ha -> True · luxcloud-ha -> False · LuxCloud -> False
# KHÔNG dùng "luxcloud" vì domain đó đã bị integration khác chiếm
# (BeardedTech0o/ha-luxcloud — có trong HACS default). Hai integration trùng domain
# không thể cùng tồn tại trên một máy HA.
DOMAIN = "luxcloud_ha"

# ── Cấu hình ───────────────────────────────────────────────────
CONF_ACCOUNT = "account"
CONF_PASSWORD = "password"
CONF_SERIAL = "serial"
CONF_REGION = "region"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_ENABLE_SERIES = "enable_series"
CONF_ENABLE_FIRMWARE = "enable_firmware"

DEFAULT_REGION = "vn"
DEFAULT_SCAN_INTERVAL = 300          # 5 phút (giống scan_interval cũ của command_line)
MIN_SCAN_INTERVAL = 60
MAX_SCAN_INTERVAL = 3600
SLOW_EVERY = 6                       # firmware + chuỗi ngày/năm: mỗi 6 lần poll (~30 phút)
FORCE_REFRESH_WAIT = 3               # giây đợi cloud→dongle sau refreshInputData

# Base URL theo khu vực (Version.java của APK)
REGIONS: dict[str, str] = {
    "as": "https://as.luxpowertek.com/WManage",
    "vn": "https://vn.luxpowertek.com/WManage",
    "na": "https://na.luxpowertek.com/WManage",
    "eu2": "https://eu2.luxpowertek.com/WManage",
    "ind": "https://ind.luxpowertek.com/WManage",
    "af": "https://af.luxpowertek.com/WManage",
    "phi": "https://phi.luxpowertek.com/WManage",
    "us": "https://us.luxpowertek.com/WManage",
}
# Host riêng cho danh mục firmware (host khu vực trả 0 dòng — đo 2026-09-27)
MAJOR_URL = "https://as.luxpowertek.com/WManage"

# AES cho refreshInputData (AESUtil.java — không đổi qua các bản APK)
AES_KEY = b"1238e4bc30c247fe987f2ce4d221427f"

# ── Endpoint ───────────────────────────────────────────────────
EP_LOGIN = "/api/login"
EP_REFRESH = "/web/maintain/remoteTransfer/refreshInputData"
EP_RUNTIME = "/api/inverter/getInverterRuntime"
EP_ENERGY = "/api/inverter/getInverterEnergyInfo"
EP_PLANT = "/api/plant/getPlantList"
EP_DATALOG = "/web/config/datalog/list"
EP_EVENT = "/api/analyze/event/list"
EP_BATTERY = "/api/battery/getBatteryInfo"
EP_QUICK_STATUS = "/web/config/quickCharge/getStatusInfo"
EP_FIRMWARE_BY_TYPE = "/web/maintain/appLocalUpdate/listForAppByType"
EP_DAY_CURVE = "/api/analyze/chart/dayMultiLine"
EP_TOTAL_COLUMN = "/api/inverterChart/totalColumn"
EP_REMOTE_READ = "/web/maintain/remoteRead/read"

# ── Đường GHI (Phase 2) ────────────────────────────────────────
# Bằng chứng APK 4.9.8 + đã đo thật:
#   • remoteSet/functionControl  (Lv112KRemoteSetFragment.java:2809-2815)
#         body {inverterSn, functionParam, enable, clientType=APP, remoteSetType=NORMAL}
#   • web/config/quickCharge|quickDischarge/{start|stop}  (Lv1OverviewFragment.java:3166-3176)
#         body {inverterSn, clientType=APP}
EP_FUNCTION_CONTROL = "/web/maintain/remoteSet/functionControl"
EP_QUICK_ACTION = "/web/config/{action}/{op}"   # action ∈ QUICK_ACTIONS, op ∈ QUICK_OPS

REMOTE_SET_TYPE = "NORMAL"           # InvTool.STATUS_NORMAL

QUICK_CHARGE = "quickCharge"
QUICK_DISCHARGE = "quickDischarge"
QUICK_ACTIONS = (QUICK_CHARGE, QUICK_DISCHARGE)
QUICK_OPS = ("start", "stop")

# Danh mục firmware theo loại thiết bị (tham số CHÍNH XÁC học từ APK:
# platform = Custom.APP_PLATFORM = LUX_POWER; versionCode = "V"+versionName)
FIRMWARE_BASE = {
    "platform": "LUX_POWER",
    "versionCode": "V4.9.8",
    "clientType": "ANDROID",
    "supportEncryptedFirmware": "true",
}
FIRMWARE_TYPES = ("SNA3_6K_EU", "SNA_3000_6000", "LXP_LB_8_12K")

# Bit nhóm HR[179] đọc qua remoteRead; ghi qua remoteSet/functionControl.
CONFIG_BIT_BLOCK = 160
CONFIG_BIT_KEYS = (
    "FUNC_GRID_PEAK_SHAVING",
    "FUNC_GEN_PEAK_SHAVING",
    "FUNC_ACTIVE_POWER_LIMIT_MODE",
    "FUNC_SMART_LOAD_ENABLE",
    "FUNC_AC_COUPLING_FUNCTION",
    "FUNC_ON_GRID_ALWAYS_ON",
    "FUNC_BAT_CHARGE_CONTROL",
    "FUNC_BAT_DISCHARGE_CONTROL",
    "FUNC_PV_SELL_TO_GRID_EN",
    "FUNC_CT_DIRECTION_REVERSED",
    "FUNC_TOTAL_LOAD_COMPENSATION_EN",
    "FUNC_RSD_DISABLE",
)

# ⚠️ CHỈ 3 bit này được tạo entity `switch`. Cả 3 đều thuộc HR[179] — nhóm mà
# `lxp_modbus` (Modbus local) KHÔNG expose. Các bit còn lại trong CONFIG_BIT_KEYS
# trùng chức năng với entity local đã có (charge_last, green_mode, smart_load,
# CT direction…) nên CỐ Ý không tạo switch: hai nguồn ghi cùng một cấu hình sẽ
# đá nhau. Vẫn đặt được bằng service `luxcloud_ha.set_bit` khi thật cần.
SWITCH_BIT_KEYS = (
    "FUNC_GRID_PEAK_SHAVING",
    "FUNC_GEN_PEAK_SHAVING",
    "FUNC_ACTIVE_POWER_LIMIT_MODE",
)

# Giây đợi cloud→dongle sau khi ghi bit, trước khi đọc lại (giống `delay: 3s`
# của script cũ). Đặt 0 trong test để khỏi chờ thật.
CONFIG_WRITE_SETTLE = 2.0

DAY_CURVE_MAX_POINTS = 72            # attribute `points` gọn (giới hạn 16 KB/entity của HA)

# ── Tên/định danh device ───────────────────────────────────────
DEVICE_NAME = "LuxCloud"             # ngắn để entity_id ra `sensor.luxcloud_*`
DEVICE_NAME_DONGLE = "LuxCloud Dongle"
MANUFACTURER = "Luxpower"

ATTR_DONGLE_SN = "dongle_sn"
ATTR_PLANT_ID = "plant_id"
