import machine
import time
import os
import gc
import dht
import json
import sys
import ubinascii

# ========== تنظیمات ==========
SSID = "Mehrbod"
PASSWORD = "357913802"
PORT = 80
MAX_MSGS = 2000
DISPLAY_MSGS = 15
MIN_FREE_MEM = 45000
ADMIN_PASS = "nigga"
DHT_PIN = 0
MAX_MSG_CHARS = 400

messages = []
next_id = 1
TEMP_LOG_FILE = "temp_log.txt"
TEMP_LOG_INTERVAL_MS = 60000
PINNED_FILE = "pinned.txt"
pinned_msg_id = 0
pinned_msg_data = None

last_dht_read = 0
last_dht_temp = None
last_dht_hum = None
dht_error_printed = False
system_error_logged = {}
VERSION = "1.8.4"
ALPHA_BETA = "Alpha"
cached_network_info = "Not connected"

try:
    wdt = machine.WDT(timeout=300000)
    print("Watchdog activated (5 min)")
except:
    wdt = None

# ========== توابع کمکی ==========
def simple_hash(s):
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h

def sanitize_string(s):
    s = s.replace('|', '¦').replace('\r', ' ').replace('\n', ' ')
    s = ''.join(ch for ch in s if ch >= ' ' or ch == '\t')
    return s.strip()

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

# ========== مدیریت پین شده ==========
def load_pinned():
    global pinned_msg_id, pinned_msg_data
    try:
        with open(PINNED_FILE, "r") as f:
            line = f.read().strip()
        pinned_msg_id = int(line) if line.isdigit() else 0
    except:
        pinned_msg_id = 0
    pinned_msg_data = None
    if pinned_msg_id != 0:
        for m in messages:
            parts = m.split(b'|')
            if len(parts) >= 6 and int(parts[0]) == pinned_msg_id:
                pinned_msg_data = {
                    "id": pinned_msg_id,
                    "user": parts[2].decode('utf-8', 'replace'),
                    "text": parts[3].decode('utf-8', 'replace'),
                    "time": parts[1].decode('utf-8', 'replace'),
                    "timestamp": int(parts[5])
                }
                break
        else:
            pinned_msg_id = 0
            save_pinned(0)

def save_pinned(msg_id):
    global pinned_msg_id, pinned_msg_data
    pinned_msg_id = msg_id
    if msg_id == 0:
        pinned_msg_data = None
        try:
            os.remove(PINNED_FILE)
        except:
            pass
    else:
        with open(PINNED_FILE, "w") as f:
            f.write(str(msg_id))
        for m in messages:
            parts = m.split(b'|')
            if len(parts) >= 6 and int(parts[0]) == msg_id:
                pinned_msg_data = {
                    "id": msg_id,
                    "user": parts[2].decode('utf-8', 'replace'),
                    "text": parts[3].decode('utf-8', 'replace'),
                    "time": parts[1].decode('utf-8', 'replace'),
                    "timestamp": int(parts[5])
                }
                break

def get_pinned_message():
    global pinned_msg_data
    if pinned_msg_id != 0 and pinned_msg_data is None:
        for m in messages:
            parts = m.split(b'|')
            if len(parts) >= 6 and int(parts[0]) == pinned_msg_id:
                pinned_msg_data = {
                    "id": pinned_msg_id,
                    "user": parts[2].decode('utf-8', 'replace'),
                    "text": parts[3].decode('utf-8', 'replace'),
                    "time": parts[1].decode('utf-8', 'replace'),
                    "timestamp": int(parts[5])
                }
                break
    return pinned_msg_data

# ========== توابع پیام ==========
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
                if len(parts) == 6:
                    try:
                        mid = int(parts[0])
                        if mid > max_id:
                            max_id = mid
                        messages.append(line)
                    except:
                        pass
                elif len(parts) == 5:
                    try:
                        mid = int(parts[0])
                        if mid > max_id:
                            max_id = mid
                        new_line = parts[0] + b'|' + parts[1] + b'|' + parts[2] + b'|' + parts[3] + b'|' + parts[4] + b'|0'
                        messages.append(new_line)
                    except:
                        pass
                elif len(parts) == 2:
                    time_str, txt = parts
                    new_line = b'0|' + time_str + b'|Legacy|' + txt + b'|0|0'
                    messages.append(new_line)
        next_id = max_id + 1
        print(f"Loaded {len(messages)} messages, next_id={next_id}")
    except:
        print("No messages file, starting fresh")
        messages = []
        next_id = 1
    load_pinned()

def save_messages():
    try:
        to_save = messages[-MAX_MSGS:] if len(messages) > MAX_MSGS else messages
        with open("messages.txt", "wb") as f:
            for msg in to_save:
                f.write(msg + b'\n')
        print(f"Saved {len(to_save)} messages")
    except Exception as e:
        print(f"Save error: {e}")
        system_error(f"Save messages failed: {e}")

def add_message(username, text, reply_to=0):
    global messages, next_id
    if not text or len(text.strip()) == 0:
        return None
    text_sanitized = sanitize_string(text)
    if not text_sanitized:
        return None
    if len(text_sanitized) > MAX_MSG_CHARS:
        text_sanitized = text_sanitized[:MAX_MSG_CHARS]
    username_sanitized = sanitize_string(username)[:20]
    if not username_sanitized:
        username_sanitized = "Anonymous"
    t = time.localtime()
    time_str = "%02d:%02d:%02d" % (t[3], t[4], t[5])
    timestamp_unix = time.mktime(t)
    msg_id = next_id
    next_id += 1
    line = b"%d|%s|%s|%s|%d|%d" % (
        msg_id,
        time_str.encode(),
        username_sanitized.encode('utf-8'),
        text_sanitized.encode('utf-8'),
        reply_to,
        timestamp_unix
    )
    messages.append(line)
    if len(messages) > MAX_MSGS:
        messages.pop(0)
    save_messages()
    print(f"Message added: id={msg_id}, user={username_sanitized}")
    return msg_id, time_str

def system_error(err_msg, exc=None):
    global system_error_logged
    key = err_msg[:50]
    now = time.time()
    t = time.localtime()
    ts = f"{t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
    if exc:
        sys.print_exception(exc)
        print(f"[SYSTEM ERROR] {ts}: {err_msg} | Exception: {exc}")
        exc_type = type(exc).__name__
        exc_msg = str(exc)
        if len(exc_msg) > 60:
            exc_msg = exc_msg[:57] + "..."
        full_msg = f"⚠️ {err_msg} | {exc_type}: {exc_msg}".replace('|', '¦')
    else:
        print(f"[SYSTEM ERROR] {ts}: {err_msg}")
        full_msg = f"⚠️ {err_msg}".replace('|', '¦')
    if key in system_error_logged:
        if now - system_error_logged[key] < 30:
            return
    system_error_logged[key] = now
    short_msg = full_msg[:190]
    add_message("System", short_msg)
    if len(system_error_logged) > 10:
        system_error_logged.clear()

def get_message_by_id(mid):
    for m in messages:
        parts = m.split(b'|')
        if len(parts) >= 5 and int(parts[0]) == mid:
            return parts[2].decode('utf-8', 'replace')
    return None

def read_cpu_temp():
    try:
        sensor = machine.ADC(4)
        v = sensor.read_u16() * 3.3 / 65535
        return 27 - (v - 0.706) / 0.001721
    except:
        return None

def read_dht11():
    global last_dht_read, last_dht_temp, last_dht_hum, dht_error_printed
    now_ms = time.ticks_ms()
    if time.ticks_diff(now_ms, last_dht_read) < 2000:
        return last_dht_temp, last_dht_hum
    try:
        sensor = dht.DHT11(machine.Pin(DHT_PIN, machine.Pin.IN, machine.Pin.PULL_UP))
        sensor.measure()
        last_dht_temp = sensor.temperature()
        last_dht_hum = sensor.humidity()
        last_dht_read = now_ms
        dht_error_printed = False
        return last_dht_temp, last_dht_hum
    except Exception as e:
        if not dht_error_printed:
            system_error("DHT11 sensor error", e)
            dht_error_printed = True
        return None, None

def log_all_temps():
    try:
        cpu_temp = read_cpu_temp()
        dht_temp, dht_hum = read_dht11()
        now = time.localtime()
        time_str = "%02d:%02d:%02d" % (now[3], now[4], now[5])
        cpu_str = f"{cpu_temp:.1f}" if cpu_temp is not None else "---"
        dht_temp_str = f"{dht_temp:.1f}" if dht_temp is not None else "---"
        dht_hum_str = f"{dht_hum:.1f}" if dht_hum is not None else "---"
        line = f"{time_str}|{cpu_str}|{dht_temp_str}|{dht_hum_str}\n"
        with open(TEMP_LOG_FILE, "a") as f:
            f.write(line)
        print(f"Temp logged: {line.strip()}")
    except Exception as e:
        system_error("Temperature log failed", e)

def get_system_stats():
    dht_temp, dht_hum = read_dht11()
    temp_str = f"{dht_temp}°C" if dht_temp is not None else "N/A"
    hum_str = f"{dht_hum}%" if dht_hum is not None else "N/A"
    uptime_sec = time.ticks_ms() // 1000
    uptime = f"{uptime_sec//3600}h {(uptime_sec%3600)//60}m"
    return temp_str, hum_str, uptime, len(messages)

# ========== API‌های وب ==========
def api_stats_handler():
    temp_str, hum_str, uptime, msg_count = get_system_stats()
    return json.dumps({"temp": temp_str, "hum": hum_str, "uptime": uptime, "msg_count": msg_count}).encode()

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

def handle_admin_command(username, text):
    global next_id, pinned_msg_id
    if not text.startswith("admin:"):
        return False, None
    parts = text[6:].strip().split()
    if not parts:
        return True, ("Error", "Usage: admin:<command> [args]")
    cmd = parts[0].lower()
    args = parts[1:]
    if cmd == "help":
        return True, ("System", "Commands: restart [pass], info, network, ping, clearlogs [pass], clear [pass], pin <id> [pass], unpin [pass]")
    if cmd == "info":
        temp, hum, uptime, cnt = get_system_stats()
        free = gc.mem_free()
        return True, ("System", f"Temp:{temp} Hum:{hum} Up:{uptime} Msgs:{cnt} FreeMem:{free}")
    if cmd == "network":
        global cached_network_info
        return True, ("System", f"📡 WiFi: {cached_network_info}")
    if cmd == "ping":
        return True, ("System", "Pong! System is alive.")
    if cmd == "pin" and len(args) >= 1:
        if len(args) < 2 or args[1] != ADMIN_PASS:
            return True, ("System", "Pin command requires admin password: admin: pin <id> <password>")
        try:
            pin_id = int(args[0])
            found = any(int(m.split(b'|')[0]) == pin_id for m in messages)
            if not found:
                return True, ("System", f"Message with ID {pin_id} not found")
            save_pinned(pin_id)
            return True, ("System", f"Message {pin_id} pinned successfully!")
        except ValueError:
            return True, ("System", "Invalid ID format")
    if cmd == "unpin":
        if len(args) < 1 or args[0] != ADMIN_PASS:
            return True, ("System", "Unpin requires admin password: admin: unpin <password>")
        save_pinned(0)
        return True, ("System", "Pinned message removed")
    if not args or args[0] != ADMIN_PASS:
        return True, ("System", "Admin command denied. Wrong or missing password.")
    if cmd == "restart":
        add_message("System", "Admin restart requested. Restarting in 2 seconds...")
        time.sleep(2)
        machine.reset()
    elif cmd == "clearlogs":
        try:
            os.remove(TEMP_LOG_FILE)
            return True, ("System", "Temperature logs cleared.")
        except:
            return True, ("System", "No temperature log to clear.")
    elif cmd == "clear":
        try:
            os.remove("messages.txt")
        except:
            pass
        messages.clear()
        next_id = 1
        add_message("System", "Chat cleared by admin command.")
        return True, None
    else:
        return True, ("System", f"Unknown admin command: {cmd}")
    return True, None

# ========== ارتباط با ESP و سرور ==========
uart = None
try:
    uart = machine.UART(1, 115200, tx=machine.Pin(4), rx=machine.Pin(5))
    print("UART1 initialized (TX=GP4, RX=GP5)")
except Exception as e:
    system_error("UART init error", e)

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
    if uart is None:
        return False
    start = time.ticks_ms()
    while time.ticks_ms() - start < timeout_ms:
        if uart.any():
            ch = uart.read(1)
            if ch == b'>':
                return True
    return False

def send_small_response(conn_id, data):
    if uart is None:
        return False
    uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(data)).encode() + b'\r\n')
    if not wait_for_prompt(2000):
        return False
    uart.write(data)
    time.sleep(0.05)
    start = time.ticks_ms()
    while time.ticks_ms() - start < 2000:
        if uart.any():
            line = uart.readline()
            if line and b'OK' in line:
                return True
    return False

def send_large_response(conn_id, data):
    if uart is None:
        return False
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

def init_wifi():
    global cached_network_info
    if uart is None:
        return False
    print("Resetting ESP...")
    send_cmd(b'AT+RST', b'ready', 5000)
    time.sleep(2)
    send_cmd(b'AT+CWMODE=1', b'OK')
    print("Connecting to WiFi...")
    if not send_cmd(b'AT+CWJAP="' + SSID.encode() + b'","' + PASSWORD.encode() + b'"', b'OK', 20000):
        system_error("WiFi connection failed! Server offline.")
        return False
    print("WiFi connected")
    send_cmd(b'AT+CIFSR', b'OK', 3000)
    time.sleep(0.5)
    resp = b''
    while uart.any():
        resp += uart.readline()
    ip = "N/A"
    mac = "N/A"
    for line in resp.split(b'\r\n'):
        if b'+CIFSR:STAIP,' in line:
            ip = line.split(b',')[1].decode()
        elif b'+CIFSR:STAMAC,' in line:
            mac = line.split(b',')[1].decode()
    cached_network_info = f"SSID: {SSID} | IP: {ip} | MAC: {mac}"
    print("Cached network info:", cached_network_info)
    send_cmd(b'AT+CIPMUX=1', b'OK')
    send_cmd(b'AT+CIPSERVER=1,' + str(PORT).encode(), b'OK')
    print(f"Server ready on port {PORT}")
    return True

# ========== صفحه آپدیت ==========
UPDATE_PAGE = '''<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>Update chat.html</title>
<style>
body{background:#0b0f19;font-family:system-ui;color:white;display:flex;justify-content:center;align-items:center;min-height:100vh}
.container{background:rgba(21,28,44,0.8);padding:2rem;border-radius:28px;text-align:center}
input,button{padding:0.8rem;margin:1rem;border-radius:40px}
button{background:#7c3aed;border:none;color:white;cursor:pointer}
</style>
</head>
<body>
<div class="container">
<h2>Upload chat.html</h2>
<input type="file" id="fileInput" accept=".html">
<input type="password" id="pass" placeholder="Admin Password">
<button onclick="doUpdate()">Upload</button>
<div id="status"></div>
</div>
<script>
async function doUpdate(){
    let pass = document.getElementById('pass').value;
    let file = document.getElementById('fileInput').files[0];
    if(!pass || !file){ document.getElementById('status').innerText='Please fill all fields'; return; }
    let reader = new FileReader();
    reader.onload = async function(e){
        let base64 = e.target.result.split(',')[1];
        let data = {password:pass, filename:file.name, content_base64:base64};
        let resp = await fetch('/api/update', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
        let result = await resp.json();
        document.getElementById('status').innerText = result.success ? '✅ Success! Refresh page.' : '❌ '+result.message;
    };
    reader.readAsDataURL(file);
}
</script>
</body>
</html>'''

def handle_update(post_data):
    try:
        data = json.loads(post_data.decode())
        if data.get('password') != ADMIN_PASS:
            return json.dumps({"success":False,"message":"Invalid password"})
        filename = data.get('filename','')
        if not filename.endswith('.html'):
            return json.dumps({"success":False,"message":"Only .html files"})
        b64 = data.get('content_base64','')
        if not b64:
            return json.dumps({"success":False,"message":"No content"})
        content = ubinascii.a2b_base64(b64)
        with open('chat.html', 'wb') as f:
            f.write(content)
        return json.dumps({"success":True,"message":"OK"})
    except Exception as e:
        return json.dumps({"success":False,"message":str(e)})

# ========== خواندن فایل chat.html (در صورت وجود) ==========
def get_chat_html():
    try:
        with open('chat.html', 'rb') as f:
            return f.read()
    except:
        # اگر فایل نبود، یک صفحه خطا برگردان
        return b'<html><body><h1>chat.html not found</h1><p>Please upload via /update</p></body></html>'

# ========== حلقه اصلی ==========
def run():
    load_messages()
    if len(messages) == 0:
        add_message("System", f"Welcome to HIVE {VERSION} (Alpha)! 🚀", 0)
    if not init_wifi():
        print("Cannot start server without WiFi")
        return
    last_temp_log = time.ticks_ms()
    print("Main server running...")
    while True:
        if wdt:
            wdt.feed()
        if time.ticks_diff(time.ticks_ms(), last_temp_log) >= TEMP_LOG_INTERVAL_MS:
            log_all_temps()
            last_temp_log = time.ticks_ms()
        if uart and uart.any():
            line = uart.readline()
            if line and line.startswith(b'+IPD'):
                conn_id = None
                try:
                    # پاک کردن بافر
                    while uart.any():
                        uart.read()
                    parts = line.split(b',', 2)
                    if len(parts) < 3:
                        continue
                    try:
                        conn_id = int(parts[1].strip())
                    except ValueError:
                        continue
                    remaining = parts[2]
                    colon = remaining.find(b':')
                    if colon == -1:
                        continue
                    len_str = remaining[:colon].strip()
                    try:
                        data_len = int(len_str)
                    except ValueError:
                        if conn_id is not None:
                            uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        continue
                    data = remaining[colon+1:]
                    if len(data) < data_len:
                        need = min(data_len - len(data), 2048)
                        if need > 0:
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

                    # ---------- مسیرهای API ----------
                    if method == b'GET' and path == b'/api/stats':
                        resp_body = api_stats_handler()
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                        full_resp = headers + resp_body
                        send_small_response(conn_id, full_resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue
                    if method == b'GET' and path == b'/api/msg_count':
                        resp = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n' + str(len(messages)).encode()
                        send_small_response(conn_id, resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue
                    elif method == b'GET' and path == b'/':
                        # سرویس فایل chat.html
                        content = get_chat_html()
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: ' + str(len(content)).encode() + b'\r\nConnection: close\r\n\r\n'
                        full_response = headers + content
                        send_large_response(conn_id, full_response)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                    elif method == b'GET' and path == b'/update':
                        resp_body = UPDATE_PAGE.encode()
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                        full_resp = headers + resp_body
                        send_large_response(conn_id, full_resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue
                    elif method == b'POST' and path == b'/api/update':
                        body_start = req.find(b'\r\n\r\n')
                        if body_start == -1:
                            resp = json.dumps({"success":False,"message":"Bad request"}).encode()
                            headers = b'HTTP/1.1 400 Bad Request\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                            full_resp = headers + resp
                            send_small_response(conn_id, full_resp)
                        else:
                            body = req[body_start+4:]
                            resp = handle_update(body)
                            headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                            full_resp = headers + resp
                            send_small_response(conn_id, full_resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue
                    elif method == b'GET' and path == b'/send':
                        params = {}
                        if query:
                            for pair in query.split(b'&'):
                                if b'=' in pair:
                                    k, v = pair.split(b'=', 1)
                                    key = k.decode()
                                    v = v.replace(b'+', b' ')
                                    val = percent_decode(v).decode('utf-8', 'ignore')
                                    params[key] = val
                        msg = params.get('msg', '')
                        name = params.get('name', 'Anonymous')
                        try:
                            reply = int(params.get('reply', '0'))
                        except:
                            reply = 0
                        is_ajax = params.get('ajax', '').lower() == '1'
                        if len(msg) > MAX_MSG_CHARS:
                            msg = msg[:MAX_MSG_CHARS]
                        if msg.startswith("admin:"):
                            handled, response_tuple = handle_admin_command(name, msg)
                            if handled:
                                if response_tuple:
                                    sys_user, sys_text = response_tuple
                                    add_message(sys_user, sys_text)
                                json_str = '{"success":true,"id":0,"time":"","total":%d}' % len(messages)
                                resp_body = json_str.encode()
                                headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                                full_resp = headers + resp_body
                                send_small_response(conn_id, full_resp)
                                uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                                conn_id = None
                                gc.collect()
                                continue
                        if msg:
                            msg_id, msg_time = add_message(name, msg, reply)
                        else:
                            msg_id, msg_time = None, ""
                        if is_ajax and msg_id is not None:
                            json_str = '{"success":true,"id":%d,"time":"%s","total":%d}' % (msg_id, msg_time, len(messages))
                            resp_body = json_str.encode()
                            headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                            full_resp = headers + resp_body
                            send_small_response(conn_id, full_resp)
                        else:
                            redirect = b'HTTP/1.1 302 Found\r\nLocation: /\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                            send_small_response(conn_id, redirect)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                    elif method == b'GET' and path == b'/download_msgs':
                        content = download_messages()
                        resp = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename="messages.txt"\r\nContent-Length: ' + str(len(content)).encode() + b'\r\nConnection: close\r\n\r\n' + content
                        send_large_response(conn_id, resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                    elif method == b'GET' and path == b'/download_temps':
                        content = download_temp_log()
                        resp = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename="temp_log.txt"\r\nContent-Length: ' + str(len(content)).encode() + b'\r\nConnection: close\r\n\r\n' + content
                        send_large_response(conn_id, resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                    elif method == b'GET' and path == b'/api/msg_poll':
                        params = {}
                        if query:
                            for pair in query.split(b'&'):
                                if b'=' in pair:
                                    k, v = pair.split(b'=', 1)
                                    params[k.decode()] = v.decode()
                        since_str = params.get('since', '0')
                        try:
                            since_id = int(since_str)
                        except:
                            since_id = 0
                        new_msgs = []
                        for m in messages:
                            parts = m.split(b'|')
                            if len(parts) < 6:
                                continue
                            mid = int(parts[0])
                            if mid <= since_id:
                                continue
                            time_str = parts[1].decode('utf-8', 'replace')
                            user = parts[2].decode('utf-8', 'replace')
                            text = parts[3].decode('utf-8', 'replace')
                            reply = int(parts[4])
                            timestamp = int(parts[5])
                            reply_user = ""
                            if reply != 0:
                                reply_user = get_message_by_id(reply) or ""
                            new_msgs.append({
                                "id": mid,
                                "time": time_str,
                                "user": user,
                                "text": text,
                                "reply": reply,
                                "reply_user": reply_user,
                                "timestamp": timestamp
                            })
                        response_obj = {"total": len(messages), "messages": new_msgs}
                        json_str = json.dumps(response_obj)
                        resp_body = json_str.encode()
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                        full_resp = headers + resp_body
                        send_small_response(conn_id, full_resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue
                    elif method == b'GET' and path == b'/api/clear_msgs':
                        params = {}
                        if query:
                            for pair in query.split(b'&'):
                                if b'=' in pair:
                                    k, v = pair.split(b'=', 1)
                                    params[k.decode()] = v.decode()
                        user_pass = params.get('pass', '')
                        if user_pass == ADMIN_PASS:
                            try:
                                os.remove("messages.txt")
                            except:
                                pass
                            messages.clear()
                            next_id = 1
                            add_message("System", "Chat cleared by admin.")
                            resp = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{"success":true}'
                        else:
                            resp = b'HTTP/1.1 403 Forbidden\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{"success":false}'
                        send_small_response(conn_id, resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue
                    elif path == b'/favicon.ico':
                        noicon = b'HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, noicon)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                    else:
                        resp404 = b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, resp404)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                except Exception as e:
                    system_error("Request handling error", e)
                    if conn_id is not None:
                        try:
                            uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        except:
                            pass
                    gc.collect()
                finally:
                    if conn_id is not None:
                        try:
                            uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        except:
                            pass
        time.sleep(0.05)
        gc.collect()

if __name__ == "__main__":
    run()