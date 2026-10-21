import machine
import time
import os
import dht

# ========== تنظیمات ==========
SSID = "YOUR_WIFI_SSID"
PASSWORD = "YOUR_WIFI_PASSWORD"
PORT = 80
MAX_MSGS = 100
DISPLAY_MSGS = 20

DHT_PIN = 15

messages = []          # هر عنصر: بایت "id|time|username|text|reply_id"
next_id = 1

TEMP_LOG_FILE = "temp_log.txt"
TEMP_LOG_INTERVAL_MS = 10000

last_dht_read = 0
last_dht_temp = None
last_dht_hum = None

# ========== عملیات فایل پیام‌ها ==========
def load_messages():
    global messages, next_id
    messages = []
    max_id = 0
    try:
        with open("messages.txt", "rb") as f:
            data = f.read()
        if data:
            for line in data.split(b'\n'):
                if not line:
                    continue
                parts = line.split(b'|')
                # فرمت جدید: id|time|username|text|reply_id
                if len(parts) == 5:
                    try:
                        mid = int(parts[0])
                        if mid > max_id:
                            max_id = mid
                        messages.append(line)
                    except:
                        pass
                else:
                    # فرمت قدیمی: time|text  -> تبدیل
                    if len(parts) == 2:
                        time_str, txt = parts
                        new_line = b'0|' + time_str + b'|Legacy|' + txt + b'|0'
                        messages.append(new_line)
        next_id = max_id + 1
        print(f"Loaded {len(messages)} messages, next_id={next_id}")
    except:
        print("No messages file, starting fresh")
        messages = []
        next_id = 1

def save_messages():
    try:
        to_save = messages[-MAX_MSGS:] if len(messages) > MAX_MSGS else messages
        with open("messages.txt", "wb") as f:
            for msg in to_save:
                f.write(msg + b'\n')
        print(f"Saved {len(to_save)} messages")
    except Exception as e:
        print(f"Save error: {e}")

def add_message(username, text, reply_to=0):
    global messages, next_id
    if not text or len(text.strip()) == 0:
        print("Empty message, ignored")
        return
    text_sanitized = sanitize(text.encode()).strip()
    if not text_sanitized:
        print("Message after sanitize is empty")
        return
    username_sanitized = sanitize(username.encode())[:20]
    if not username_sanitized:
        username_sanitized = b"Anonymous"
    t = time.localtime()
    time_str = "%02d:%02d:%02d" % (t[3], t[4], t[5])
    msg_id = next_id
    next_id += 1
    line = b"%d|%s|%s|%s|%d" % (msg_id, time_str.encode(), username_sanitized, text_sanitized[:100], reply_to)
    messages.append(line)
    if len(messages) > MAX_MSGS:
        messages.pop(0)
    save_messages()
    print(f"Message added: id={msg_id}, user={username_sanitized}, reply={reply_to}")

def get_message_by_id(mid):
    for m in messages:
        parts = m.split(b'|')
        if len(parts) == 5 and int(parts[0]) == mid:
            return parts[2].decode()
    return None

# ========== سنسورها و لاگ ==========
def read_cpu_temp():
    try:
        sensor = machine.ADC(4)
        v = sensor.read_u16() * 3.3 / 65535
        return 27 - (v - 0.706) / 0.001721
    except:
        return None

def read_dht11():
    global last_dht_read, last_dht_temp, last_dht_hum
    now_ms = time.ticks_ms()
    if time.ticks_diff(now_ms, last_dht_read) < 2000:
        return last_dht_temp, last_dht_hum
    try:
        sensor = dht.DHT11(machine.Pin(DHT_PIN, machine.Pin.IN, machine.Pin.PULL_UP))
        sensor.measure()
        last_dht_temp = sensor.temperature()
        last_dht_hum = sensor.humidity()
        last_dht_read = now_ms
        return last_dht_temp, last_dht_hum
    except Exception as e:
        print(f"DHT11 error: {e}")
        return None, None

def log_all_temps():
    cpu_temp = read_cpu_temp()
    dht_temp, dht_hum = read_dht11()
    now = time.localtime()
    time_str = "%02d:%02d:%02d" % (now[3], now[4], now[5])
    cpu_str = f"{cpu_temp:.1f}" if cpu_temp is not None else "---"
    dht_temp_str = f"{dht_temp:.1f}" if dht_temp is not None else "---"
    dht_hum_str = f"{dht_hum:.1f}" if dht_hum is not None else "---"
    line = f"{time_str}|{cpu_str}|{dht_temp_str}|{dht_hum_str}\n"
    try:
        with open(TEMP_LOG_FILE, "a") as f:
            f.write(line)
        print(f"Temp logged: {line.strip()}")
    except Exception as e:
        print(f"Temp log error: {e}")

# ========== ابزارهای عمومی ==========
def sanitize(bs):
    bs = bs.replace(b'\r\n', b' ').replace(b'\r', b' ').replace(b'\n', b' ')
    out = bytearray()
    for b in bs:
        if b == 0x09 or 0x20 <= b <= 0x7E or b >= 0x80:
            out.append(b)
    return bytes(out)

def percent_decode(bs):
    out = bytearray()
    i = 0
    while i < len(bs):
        if bs[i] == ord('%') and i+2 < len(bs):
            try:
                out.append(int(bs[i+1:i+3], 16))
                i += 3
                continue
            except:
                pass
        out.append(bs[i])
        i += 1
    return bytes(out)

def get_system_stats():
    dht_temp, dht_hum = read_dht11()
    temp_str = f"{dht_temp}°C" if dht_temp is not None else "N/A"
    hum_str = f"{dht_hum}%" if dht_hum is not None else "N/A"
    uptime_sec = time.ticks_ms() // 1000
    uptime = f"{uptime_sec//3600}h {(uptime_sec%3600)//60}m"
    return temp_str, hum_str, uptime, len(messages)

# ========== تولید صفحه HTML ==========
def html_page():
    temp_str, hum_str, uptime, msg_count = get_system_stats()
    msg_html = b''
    for m in messages[-DISPLAY_MSGS:]:
        parts = m.split(b'|')
        if len(parts) != 5:
            continue
        mid, t, username, txt, reply_to = parts
        mid = int(mid)
        reply_to = int(reply_to)
        reply_html = b''
        if reply_to != 0:
            replied_name = get_message_by_id(reply_to)
            if replied_name:
                reply_html = b'<span class=reply-info>↩️ to ' + replied_name.encode() + b'</span>'
        msg_html += b'<div class=m data-id="%d">' % mid
        msg_html += b'<span class=t>' + t + b'</span>'
        msg_html += b'<span class=name>' + username + b'</span>'
        if reply_html:
            msg_html += reply_html
        msg_html += b'<span class=msg-txt>' + txt + b'</span>'
        msg_html += b'<button class=reply-btn data-id="%d" data-name="%s">↩️ Reply</button>' % (mid, username)
        msg_html += b'</div>'

    html = b'''<!DOCTYPE html><html><head><meta charset=UTF-8><meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no"><title>HIVE ChatRoom 1.5 · Alpha</title><style>
html,body{height:100%;margin:0;font-family:system-ui,sans-serif;color:#eef2ff;overflow:hidden}
body{background:#0a0f1a;display:flex;justify-content:center;align-items:center}
.c{width:100%;max-width:700px;height:100%;display:flex;flex-direction:column;background:#111827;overflow:hidden}
.h{background:#0f172a;padding:12px 16px;text-align:center;border-bottom:1px solid #1e2a3e}
.h h2{font-size:1.4rem;background:linear-gradient(135deg,#d8b4fe,#a855f7);-webkit-background-clip:text;background-clip:text;color:transparent}
.msgs{flex:1;overflow-y:auto;margin:10px;background:#0f172a;border-radius:20px;padding:6px}
.m{display:flex;flex-wrap:wrap;align-items:baseline;gap:6px;padding:8px 12px;margin-bottom:6px;background:#1e293b;border-radius:18px}
.t{background:#0f172a;padding:2px 8px;border-radius:30px;font-family:monospace;font-size:0.7rem;color:#d8b4fe}
.name{font-weight:bold;color:#c084fc;font-size:0.85rem}
.reply-info{font-size:0.7rem;color:#94a3b8;margin-left:5px}
.msg-txt{word-break:break-word;font-size:0.9rem;flex:1}
.reply-btn{background:#334155;border:none;border-radius:30px;padding:4px 10px;font-size:0.7rem;color:#fff;cursor:pointer}
form{display:flex;flex-direction:column;gap:8px;margin:0 10px 10px 10px}
.name-row{display:flex;gap:8px}
.name-row input{flex:2;background:#0f172a;border:1px solid #334155;padding:10px;border-radius:40px;color:#fff}
.message-row{display:flex;gap:8px}
.message-row input{flex:1;background:#0f172a;border:1px solid #334155;padding:10px;border-radius:40px;color:#fff}
button{background:#7e22ce;border:none;padding:10px 16px;border-radius:40px;font-weight:bold;color:#fff;cursor:pointer}
.menu{display:flex;gap:12px;justify-content:center;margin:0 10px 10px 10px}
.menu a,.menu .re{background:#1e293b;padding:8px 18px;border-radius:40px;text-decoration:none;font-size:0.8rem;color:#e9d5ff;border:1px solid #334155;cursor:pointer}
.stats{background:#0f172a;padding:10px;font-size:0.75rem;text-align:center;display:flex;justify-content:center;gap:12px;border-top:1px solid #1e2a3e}
.stats span{background:#1e293b;padding:4px 12px;border-radius:30px}
.replying-info{background:#334155;color:#ddd;padding:5px 12px;border-radius:20px;font-size:0.8rem;text-align:center}
</style>
<script>
let currentReplyTo = 0;
let currentReplyName = '';
let lastMsgCount = ''' + str(msg_count).encode() + b''';
let autoRefreshInterval = null;

function checkForNewMessages() {
    fetch('/api/msg_count')
        .then(response => response.text())
        .then(count => {
            let newCount = parseInt(count);
            if (newCount > lastMsgCount) {
                let isTyping = (document.activeElement === document.getElementById('msg_input') ||
                                document.activeElement === document.getElementById('username'));
                if (!isTyping) {
                    location.reload();
                } else {
                    lastMsgCount = newCount;
                }
            } else {
                lastMsgCount = newCount;
            }
        })
        .catch(err => console.log('Poll error:', err));
}

window.onload = function() {
    let msgsDiv = document.querySelector('.msgs');
    if(msgsDiv) msgsDiv.scrollTop = msgsDiv.scrollHeight;
    let savedName = localStorage.getItem('chat_username');
    if(savedName) document.getElementById('username').value = savedName;
    
    document.querySelectorAll('.reply-btn').forEach(btn => {
        btn.onclick = function() {
            currentReplyTo = parseInt(this.dataset.id);
            currentReplyName = this.dataset.name;
            document.getElementById('reply_to').value = currentReplyTo;
            document.getElementById('replyingInfo').innerHTML = '↩️ Replying to ' + currentReplyName + ' <button type="button" onclick="clearReply()">Cancel</button>';
            document.getElementById('msg_input').focus();
        };
    });
    
    if (autoRefreshInterval === null) {
        autoRefreshInterval = setInterval(checkForNewMessages, 3000);
    }
};

function clearReply() {
    currentReplyTo = 0;
    currentReplyName = '';
    document.getElementById('reply_to').value = '0';
    document.getElementById('replyingInfo').innerHTML = '';
}

function saveUsername() {
    let nameInput = document.getElementById('username');
    localStorage.setItem('chat_username', nameInput.value);
}
</script>
</head><body>
<div class=c>
<div class=h><h2>💬 HIVE ChatRoom 1.5 · Alpha</h2></div>
<div class=msgs>''' + msg_html + b'''</div>
<form action=/send method=GET onsubmit="saveUsername()">
<div class=name-row>
<input type=text id=username name=name placeholder="Your name" maxlength=20 required>
</div>
<div class=message-row>
<input type=text id=msg_input name=msg placeholder="Message..." required>
<input type=hidden id=reply_to name=reply value="0">
<button>Send</button>
</div>
<div id=replyingInfo class=replying-info></div>
</form>
<div class=menu><button class=re onclick="location.reload()">🔄 Refresh</button><a href=/download_msgs target=_blank>⬇️ Download</a><a href=/download_temps target=_blank>🌡️ Log</a></div>
<div class=stats><span>🌡️ ''' + temp_str.encode() + b'''</span><span>💧 ''' + hum_str.encode() + b'''</span><span>⏱️ ''' + uptime.encode() + b'''</span><span>💬 ''' + str(msg_count).encode() + b'''</span></div>
</div>
</body></html>'''
    return html.replace(b'\n', b'\r\n')

def download_messages():
    try:
        with open("messages.txt", "rb") as f:
            return f.read()
    except:
        return b"No messages file yet."

def download_temp_log():
    try:
        with open(TEMP_LOG_FILE, "rb") as f:
            return f.read()
    except:
        return b"No temperature log yet."

# ========== توابع ارتباط با ESP ==========
def send_cmd(cmd_bytes, expected_bytes, timeout_ms=5000):
    if uart is None:
        return False
    while uart.any():
        uart.read()
    uart.write(cmd_bytes + b'\r\n')
    start = time.ticks_ms()
    while time.ticks_ms() - start < timeout_ms:
        if uart.any():
            line = uart.readline()
            if line and expected_bytes in line:
                return True
    return False

def wait_for_prompt(timeout_ms=2000):
    start = time.ticks_ms()
    while time.ticks_ms() - start < timeout_ms:
        if uart.any():
            ch = uart.read(1)
            if ch == b'>':
                return True
    return False

def send_large_response(conn_id, data):
    chunk_size = 1400
    offset = 0
    while offset < len(data):
        chunk = data[offset:offset+chunk_size]
        uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(chunk)).encode() + b'\r\n')
        if not wait_for_prompt(2000):
            return False
        uart.write(chunk)
        time.sleep(0.05)
        start = time.ticks_ms()
        ok = False
        while time.ticks_ms() - start < 2000:
            if uart.any():
                line = uart.readline()
                if line and b'OK' in line:
                    ok = True
                    break
        if not ok:
            return False
        offset += chunk_size
    return True

# ========== راه‌اندازی UART و ESP01s ==========
print("System starting")
load_messages()
if len(messages) == 0:
    add_message("System", "Welcome to HIVE ChatRoom 1.5 Alpha! 😊", 0)

try:
    uart = machine.UART(1, 115200)
    print("UART1 initialized")
except Exception as e:
    print(f"UART init error: {e}")
    uart = None

if uart:
    print("Resetting ESP...")
    send_cmd(b'AT+RST', b'ready', 5000)
    time.sleep(2)
    send_cmd(b'AT+CWMODE=1', b'OK')
    print("Connecting to WiFi...")
    if not send_cmd(b'AT+CWJAP="' + SSID.encode() + b'","' + PASSWORD.encode() + b'"', b'OK', 20000):
        print("WiFi connection failed!")
        uart = None
    else:
        print("WiFi connected")
        send_cmd(b'AT+CIFSR', b'OK')
        send_cmd(b'AT+CIPMUX=1', b'OK')
        send_cmd(b'AT+CIPSERVER=1,' + str(PORT).encode(), b'OK')
        print(f"Server ready on port {PORT}")

last_temp_log = time.ticks_ms()

# ========== حلقه اصلی ==========
while True:
    if time.ticks_diff(time.ticks_ms(), last_temp_log) >= TEMP_LOG_INTERVAL_MS:
        log_all_temps()
        last_temp_log = time.ticks_ms()

    if uart and uart.any():
        line = uart.readline()
        if line and line.startswith(b'+IPD'):
            conn_id = None
            try:
                parts = line.split(b',', 2)
                if len(parts) < 3:
                    continue
                conn_id = int(parts[1])
                remaining = parts[2]
                colon = remaining.find(b':')
                if colon == -1:
                    continue
                data_len = int(remaining[:colon])
                data = remaining[colon+1:]
                if len(data) < data_len:
                    need = data_len - len(data)
                    extra = uart.read(need)
                    if extra:
                        data += extra

                req = data
                req_lines = req.split(b'\r\n')
                if not req_lines:
                    continue
                first = req_lines[0].split(b' ')
                if len(first) < 2:
                    continue
                method = first[0]
                full_path = first[1]
                path = full_path.split(b'?')[0]
                query = b''
                if b'?' in full_path:
                    query = full_path.split(b'?', 1)[1]

                # API شمارش پیام‌ها
                if method == b'GET' and path == b'/api/msg_count':
                    resp = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n' + str(len(messages)).encode()
                    uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(resp)).encode() + b'\r\n')
                    wait_for_prompt()
                    uart.write(resp)
                    time.sleep(0.1)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    continue

                elif method == b'GET' and path == b'/':
                    html = html_page()
                    headers = b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: ' + str(len(html)).encode() + b'\r\nConnection: close\r\n\r\n'
                    full_response = headers + html
                    send_large_response(conn_id, full_response)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None

                elif method == b'GET' and path == b'/send':
                    params = {}
                    for pair in query.split(b'&'):
                        if b'=' in pair:
                            k, v = pair.split(b'=', 1)
                            key = k.decode()
                            v = v.replace(b'+', b' ')          # تبدیل + به فاصله
                            val = percent_decode(v).decode('utf-8', 'ignore')
                            params[key] = val
                    msg = params.get('msg', '')
                    name = params.get('name', 'Anonymous')
                    try:
                        reply = int(params.get('reply', '0'))
                    except:
                        reply = 0
                    if msg:
                        add_message(name, msg, reply)
                    redirect = b'HTTP/1.1 302 Found\r\nLocation: /\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                    uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(redirect)).encode() + b'\r\n')
                    wait_for_prompt()
                    uart.write(redirect)
                    time.sleep(0.1)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None

                elif method == b'GET' and path == b'/download_msgs':
                    content = download_messages()
                    resp = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename="messages.txt"\r\nContent-Length: ' + str(len(content)).encode() + b'\r\nConnection: close\r\n\r\n' + content
                    send_large_response(conn_id, resp)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None

                elif method == b'GET' and path == b'/download_temps':
                    content = download_temp_log()
                    resp = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename="temp_log.txt"\r\nContent-Length: ' + str(len(content)).encode() + b'\r\nConnection: close\r\n\r\n' + content
                    send_large_response(conn_id, resp)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None

                elif path == b'/favicon.ico':
                    noicon = b'HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n'
                    uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(noicon)).encode() + b'\r\n')
                    wait_for_prompt()
                    uart.write(noicon)
                    time.sleep(0.1)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None

                else:
                    resp404 = b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                    uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(resp404)).encode() + b'\r\n')
                    wait_for_prompt()
                    uart.write(resp404)
                    time.sleep(0.1)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None

            except Exception as e:
                print(f"Handler error: {e}")
            finally:
                if conn_id is not None:
                    try:
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        time.sleep(0.1)
                    except:
                        pass

    time.sleep(0.05)