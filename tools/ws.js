// WS client chung cho HA (entity/device registry, lovelace, ...).
//
//   node tools/ws.js <cmds.json> [filter]
//
// cmds.json = mảng lệnh WS, ví dụ: [{"type":"config/device_registry/list"}]
// filter    = nếu kết quả là mảng, chỉ in phần tử có JSON chứa chuỗi này.
//
// Token lấy từ env HA_TOKEN (tools/hass.py tự nạp .env; nếu chạy trực tiếp thì:
//   PowerShell:  $env:HA_TOKEN = (Select-String .env '^HA_TOKEN=').Line.Split('=',2)[1]
// Dùng WebSocket có sẵn của Node >= 22, KHÔNG cần node_modules.
const fs = require('fs');

const file = process.argv[2];
const filter = process.argv[3] || null;
const token = process.env.HA_TOKEN;
const host = process.env.HA_HOST || '192.168.10.15';

if (!file) { console.error('thiếu cmds.json'); process.exit(2); }
if (!token) { console.error('thiếu HA_TOKEN'); process.exit(2); }

(async () => {
  const cmds = JSON.parse(fs.readFileSync(file, 'utf-8'));
  const ws = new WebSocket(`ws://${host}:8123/api/websocket`);
  let id = 0;
  const pending = new Map();
  const call = (p) => new Promise((res, rej) => {
    const i = ++id; p.id = i; pending.set(i, res); ws.send(JSON.stringify(p));
    setTimeout(() => { if (pending.has(i)) { pending.delete(i); rej(new Error('timeout ' + p.type)); } }, 120000);
  });
  await new Promise((res, rej) => {
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      if (m.type === 'auth_required') ws.send(JSON.stringify({ type: 'auth', access_token: token }));
      else if (m.type === 'auth_ok') { console.log('auth ok', m.ha_version); res(); }
      else if (m.type === 'auth_invalid') rej(new Error('auth invalid'));
      else if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
    };
    ws.onerror = () => rej(new Error('ws error'));
  });
  for (const c of cmds) {
    try {
      const r = await call(c);
      const res = r.result === undefined ? r : r.result;
      console.log('=== ' + c.type);
      if (filter && Array.isArray(res)) {
        const hit = res.filter((x) => JSON.stringify(x).includes(filter));
        console.log(`khớp ${hit.length}/${res.length}`);
        for (const x of hit) console.log('  ' + JSON.stringify(x));
      } else {
        console.log(JSON.stringify(res).slice(0, 3000));
      }
    } catch (e) { console.log('=== ' + c.type + ' FAILED: ' + e.message); }
  }
  ws.close();
})();
