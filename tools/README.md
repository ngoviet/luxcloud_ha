# Tools — công cụ làm việc với integration này

Tất cả chạy được **độc lập từ repo này** (không cần `HA-Config`), miễn là có `.env` ở thư mục gốc
repo (gitignored) hoặc biến môi trường. Nếu thiếu, script tự lùi về `..\HA-Config\.env`.

| File | Việc | Lệnh |
|---|---|---|
| `deploy_to_ha.py` | Deploy `custom_components/luxcloud_ha/` lên HA qua SSH + base64, verify md5 từng file; `--restart` để restart HA và chờ nó trở lại | `python tools/deploy_to_ha.py --restart` |
| `hass.py` | Helper chung: `run` (shell), `cfgcheck` (`check_config`), `restart`, `deploy`, `deploydir`, `state`, `states` | `python tools/hass.py cfgcheck` |
| `verify_live.py` | Nghiệm thu sau deploy: config entry, 36 entity, quan hệ device (`via_device_id`), đếm cảnh báo deprecate/ERROR **chỉ sau lần boot cuối** | `python tools/verify_live.py` |
| `probe_write_live.py` | Nghiệm thu **đường GHI** trên HA thật: gọi `luxcloud_ha.set_bit` với giá trị **TRÙNG trạng thái hiện tại** (nên không đổi hành vi inverter), rồi xác nhận không bit nào đổi. KHÔNG đụng quick charge/discharge | `python tools/probe_write_live.py` |
| `ws.js` | WebSocket client chung (device/entity registry, lovelace…) — Node ≥ 22, không cần `node_modules` | `node tools/ws.js cmds.json luxcloud` |
| `make_brand.py` | Sinh `brand/{icon,icon@2x,logo}.png` bằng stdlib (máy không có PIL) | `python tools/make_brand.py` |
| `setup_tests.py` | Dựng `.venv` để chạy `tests/` (cài `requirements_test.txt`, đặt stub POSIX trên Windows); `--run` để chạy pytest luôn | `python tools/setup_tests.py --run` |
| `win32_stubs/` | Stub `fcntl.py` + `resource.py` cho Windows — `setup_tests.py` copy vào `site-packages` của `.venv`, **không** dùng trên Linux | (tự động) |

## `.env` cần gì

```ini
HA_HOST=192.168.10.15
HA_URL=http://192.168.10.15:8123
HA_PASS=<mật khẩu SSH user vokupt>
HA_TOKEN=<long-lived access token của HA>
```

Xem `.env.example`. `.env` **đã gitignored** — không commit.

## Vài điều đã trả giá (đừng lặp lại)

- Host HA **không có `sftp-server`** → phải shell + base64, không dùng SFTP.
- `base64 -d > file` **không tự tạo thư mục cha** ⇒ `deploy_to_ha.py`/`deploydir` phải `mkdir -p` trước,
  nếu không md5 trả `?` mà chẳng có thông báo lỗi rõ ràng.
- Console Windows mặc định **cp1252** ⇒ script in tiếng Việt sẽ chết bằng `UnicodeEncodeError`
  **sau khi deploy xong**; các script ở đây đã `sys.stdout.reconfigure(encoding="utf-8")`.
- Gọi service `homeassistant.restart` sẽ luôn ném lỗi kết nối (`HTTPError 503/504`, `URLError`, hoặc
  `http.client.RemoteDisconnected`) — **đó là dấu hiệu thành công**, không phải lỗi. `RemoteDisconnected`
  không phải `URLError` nên phải `except Exception`.
- `/tmp` của **host** và `/tmp` **trong container HA** là hai chỗ khác nhau — file do integration/command_line
  ghi nằm trong container (`docker exec homeassistant ...`).
