import machine
import time
import os
import gc
import dht
import json
import sys
import ubinascii

# ============================== تنظیمات اصلی ==============================
SSID = "YOUR_WIFI_SSID"
PASSWORD = "YOUR_WIFI_PASSWORD"
PORT = 80
MAX_MSGS = 5000
DISPLAY_MSGS = 30
MIN_FREE_MEM = 45000
ADMIN_PASS = "CHANGE_ME_TO_A_LONG_UNIQUE_PASSWORD"
CHUNK_SIZE = 4096

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
upload_session = None

try:
    wdt = machine.WDT(timeout=300000)
    print("Watchdog activated (5 min)")
except:
    wdt = None

# ============================== توابع کمکی ==============================
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

# ======================== مدیریت پیام پین شده ========================
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

# ============================== توابع پیام‌ها ==============================
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
    print(f"Message added: id={msg_id}, user={username_sanitized}, reply={reply_to}, chars={len(text_sanitized)}")
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

# ============================== توابع وب ==============================
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

# ============================== صفحه HTML اصلی ==============================
def html_page():
    gc.collect()
    free_mem = gc.mem_free()
    print(f"Free memory before page gen: {free_mem}")
    
    if free_mem < MIN_FREE_MEM:
        display_count = 6
        system_error("Low memory: showing only last 6 messages")
    else:
        display_count = DISPLAY_MSGS
    
    try:
        temp_str, hum_str, uptime, msg_count = get_system_stats()
    except:
        temp_str = hum_str = "N/A"
        uptime = "?"
        msg_count = len(messages)
    
    msgs_to_show = messages[-display_count:] if len(messages) > display_count else messages
    
    max_msg_id = 0
    for m in messages:
        parts = m.split(b'|')
        if parts and parts[0].isdigit():
            mid = int(parts[0])
            if mid > max_msg_id:
                max_msg_id = mid
    
    pinned_html = b''
    pinned_msg = get_pinned_message()
    if pinned_msg and free_mem > MIN_FREE_MEM + 10000:
        hue = simple_hash(pinned_msg['user']) % 360
        avatar_style = f"background:hsl({hue},70%,55%);"
        pinned_html = b'<div class="msg pinned" style="border-left:4px solid #f472b6; background:rgba(244,114,182,0.1);">'
        pinned_html += b'<div class="av" style="' + avatar_style.encode() + b'">' + pinned_msg['user'][:2].upper().encode('utf-8', 'replace') + b'</div>'
        pinned_html += b'<div class="mc"><div class="mh"><span class="un">📌 ' + pinned_msg['user'].encode('utf-8', 'replace') + b'</span>'
        pinned_html += b'<span class="tm" data-timestamp="%d"></span>' % pinned_msg['timestamp']
        pinned_html += b'<span class="reply-badge">🔒 Pinned</span>'
        pinned_html += b'</div><div class="mt" onclick="copyText(this)">' + pinned_msg['text'].encode('utf-8', 'replace') + b'</div>'
        pinned_html += b'<div class="ma"></div></div></div>'
    
    msg_html = b''
    for m in msgs_to_show:
        parts = m.split(b'|')
        if len(parts) < 5:
            continue
        mid = int(parts[0])
        username = parts[2].decode('utf-8', 'replace')
        txt = parts[3].decode('utf-8', 'replace')
        reply_to = int(parts[4])
        timestamp_unix = int(parts[5]) if len(parts) > 5 else 0
        hue = simple_hash(username) % 360
        avatar_style = f"background:hsl({hue},70%,55%);"
        reply_html = b''
        if reply_to != 0:
            replied_name = get_message_by_id(reply_to)
            if replied_name:
                reply_html = b'<span class="reply-badge">↩️ ' + replied_name.encode('utf-8', 'replace') + b'</span>'
        msg_html += b'<div class="msg" data-id="%d" data-username="%s" data-time="%d">' % (mid, username.encode('utf-8', 'replace'), timestamp_unix)
        msg_html += b'<div class="av" style="' + avatar_style.encode() + b'">' + username[:2].upper().encode('utf-8', 'replace') + b'</div>'
        msg_html += b'<div class="mc"><div class="mh"><span class="un">' + username.encode('utf-8', 'replace') + b'</span>'
        msg_html += b'<span class="tm" data-timestamp="%d"></span>' % timestamp_unix
        if reply_html:
            msg_html += reply_html
        msg_html += b'</div><div class="mt" onclick="copyText(this)">' + txt.encode('utf-8', 'replace') + b'</div>'
        msg_html += b'<div class="ma"><button class="rb" data-id="%d" data-name="%s">💬 Reply</button></div></div></div>' % (mid, username.encode('utf-8', 'replace'))
    
    version_bytes = VERSION.encode()
    html = b'''<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=yes,viewport-fit=cover"><title>HIVE ''' + version_bytes + b'''</title><style>
    :root{--bf:16px;--bg:#0b0f19;--s:#151c2c;--sl:#1e293b;--p:#a78bfa;--a:#f472b6;--t:#e2e8f0;--tm:#94a3b8;--b:rgba(255,255,255,0.08);--r:18px;--rl:24px}
    *{margin:0;padding:0;box-sizing:border-box}html{font-size:var(--bf)}body{background:var(--bg);font-family:'Segoe UI',system-ui,-apple-system,sans-serif;color:var(--t);height:100dvh;overflow:hidden;display:flex;justify-content:center;align-items:center}
    .app{width:100%;height:100%;max-width:600px;background:rgba(21,28,44,0.6);backdrop-filter:blur(20px);display:flex;flex-direction:column;overflow:hidden;box-shadow:0 0 60px rgba(168,85,247,0.08)}
    @media(min-width:640px){.app{border-radius:var(--rl);margin:16px;height:calc(100% - 32px);border:1px solid var(--b)}}
    .login-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(11,15,25,0.95);backdrop-filter:blur(20px);display:flex;justify-content:center;align-items:center;z-index:200;transition:opacity .4s}
    .login-box{background:rgba(21,28,44,0.8);backdrop-filter:blur(20px);border:1px solid var(--b);border-radius:var(--rl);padding:2rem;width:90%;max-width:360px;text-align:center;animation:fadeInScale .5s ease}
    @keyframes fadeInScale{from{opacity:0;transform:scale(0.9)}to{opacity:1;transform:scale(1)}}
    .login-box h2{font-size:1.8rem;margin-bottom:1.5rem;background:linear-gradient(to right,#a78bfa,#f472b6);-webkit-background-clip:text;background-clip:text;color:transparent}
    .login-box input{width:100%;padding:0.8rem 1rem;border-radius:25px;background:#0f172a;border:1px solid #334155;color:#f1f5f9;font-size:0.9rem;margin-bottom:1rem;outline:none}
    .login-box input:focus{border-color:var(--p);box-shadow:0 0 0 2px rgba(167,139,250,0.3)}
    .login-box button{width:100%;padding:0.8rem;border-radius:25px;background:linear-gradient(135deg,#7c3aed,#ec4899);border:none;color:white;font-weight:bold;font-size:1rem;cursor:pointer}
    .header{background:linear-gradient(135deg,rgba(124,58,237,0.15),rgba(236,72,153,0.1));padding:1.2rem 1.5rem;border-bottom:1px solid var(--b);text-align:center;flex-shrink:0}
    .header h1{font-size:1.6rem;font-weight:800;background:linear-gradient(to right,#a78bfa,#f472b6);-webkit-background-clip:text;background-clip:text;color:transparent;animation:titlePulse 3s ease-in-out infinite alternate}
    @keyframes titlePulse{from{filter:brightness(1)}to{filter:brightness(1.3)}}
    .badge{font-size:0.7rem;background:rgba(45,55,72,0.8);display:inline-block;padding:0.3rem 1rem;border-radius:20px;margin-top:0.3rem;color:#cbd5e0;letter-spacing:0.5px;border:1px solid var(--b);backdrop-filter:blur(4px)}
    .stats-bar{display:flex;background:rgba(0,0,0,0.3);backdrop-filter:blur(12px);padding:0.6rem 1rem;gap:0.6rem;border-bottom:1px solid var(--b);overflow-x:auto;white-space:nowrap;flex-shrink:0}
    .stat{background:linear-gradient(135deg,#1e293b,#0f172a);padding:0.4rem 1rem;border-radius:30px;font-size:0.75rem;font-weight:500;display:flex;align-items:center;gap:0.4rem;border:1px solid var(--b);box-shadow:0 2px 8px rgba(0,0,0,0.3)}
    .stat-icon{font-size:0.9rem}
    .messages-container{flex:1;overflow-y:auto;padding:1rem;padding-bottom:100px;display:flex;flex-direction:column;gap:0.8rem;scroll-behavior:smooth;-webkit-overflow-scrolling:touch}
    .msg{display:flex;gap:0.7rem;background:rgba(30,41,59,0.5);backdrop-filter:blur(8px);border-radius:var(--r);padding:0.8rem;border:1px solid var(--b);animation:fadeInUp .3s ease}
    .msg.pinned{background:rgba(244,114,182,0.15); border-left:3px solid #f472b6;}
    @keyframes fadeInUp{from{opacity:0;transform:translateY(0.6rem)}to{opacity:1;transform:translateY(0)}}
    .msg:hover{background:rgba(51,65,85,0.6);border-color:rgba(255,255,255,0.1)}
    .av{width:2.4rem;height:2.4rem;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:0.85rem;color:white;flex-shrink:0;border:2px solid rgba(255,255,255,0.2)}
    .mc{flex:1}
    .mh{display:flex;align-items:baseline;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.3rem}
    .un{font-weight:700;color:var(--p);font-size:0.85rem}
    .tm{font-size:0.65rem;color:var(--tm)}
    .reply-badge{font-size:0.65rem;background:rgba(71,85,105,0.7);padding:0.2rem 0.6rem;border-radius:20px;color:#e2e8f0;border:1px solid rgba(255,255,255,0.1)}
    .mt{font-size:0.9rem;line-height:1.45;margin:0.4rem 0;word-break:break-word;cursor:pointer;padding:0.2rem 0}
    .rb{background:none;border:1px solid #475569;color:#cbd5e0;font-size:0.7rem;padding:0.3rem 0.8rem;border-radius:20px;cursor:pointer;transition:0.2s}
    .rb:hover{background:var(--p);border-color:var(--p);color:white}
    #inputArea{position:fixed;bottom:0;left:0;right:0;max-width:600px;margin:0 auto;background:rgba(15,23,42,0.9);backdrop-filter:blur(12px);border-top:1px solid var(--b);padding:0.8rem 1rem;padding-bottom:calc(0.8rem + env(safe-area-inset-bottom,0px));z-index:10}
    .reply-indicator{background:#4c1d95;border-radius:25px;padding:0.5rem 1rem;margin-bottom:0.6rem;font-size:0.75rem;display:flex;justify-content:space-between;align-items:center;animation:slideDown .2s ease}
    @keyframes slideDown{from{opacity:0;transform:translateY(-0.5rem)}to{opacity:1;transform:translateY(0)}}
    .cancel-reply{background:#ef4444;border:none;color:white;padding:0.2rem 1rem;border-radius:20px;cursor:pointer;font-size:0.7rem;font-weight:600}
    .input-row{display:flex;gap:0.5rem;margin-bottom:0.5rem;flex-wrap:wrap}
    .input-row input#msg_input{flex:1 1 auto;background:#0f172a;border:1px solid #334155;padding:0.7rem 1rem;border-radius:25px;color:#f1f5f9;font-size:0.85rem;outline:none;transition:border .2s,box-shadow .2s;min-width:0}
    .input-row input#msg_input:focus{border-color:var(--p);box-shadow:0 0 0 2px rgba(167,139,250,0.3)}
    .send-button{background:linear-gradient(135deg,#7c3aed,#ec4899);border:none;border-radius:25px;padding:0 1.4rem;font-weight:700;color:white;cursor:pointer;white-space:nowrap;font-size:0.85rem;transition:transform .1s}
    .send-button:disabled{opacity:0.6;cursor:not-allowed}
    .send-button:active:not(:disabled){transform:scale(0.95)}
    .menu-buttons{display:flex;gap:0.4rem;justify-content:center;flex-wrap:wrap;margin-top:0.4rem}
    .menu-buttons a,.menu-buttons button{background:rgba(51,65,85,0.7);backdrop-filter:blur(4px);padding:0.35rem 0.9rem;border-radius:20px;font-size:0.7rem;color:#cbd5e0;text-decoration:none;border:1px solid rgba(255,255,255,0.1);cursor:pointer}
    .toast{position:fixed;bottom:5rem;left:50%;transform:translateX(-50%);background:#334155;color:white;padding:0.5rem 1.2rem;border-radius:20px;font-size:0.8rem;opacity:0;transition:opacity .3s;z-index:1000;backdrop-filter:blur(8px);border:1px solid rgba(255,255,255,0.2)}
    #systemLogPanel{background:rgba(30,41,59,0.9);padding:0.6rem 1rem;border-bottom:1px solid var(--b);max-height:8rem;overflow-y:auto;display:none}
    .system-log-item{font-size:0.75rem;padding:0.3rem 0;border-bottom:1px solid rgba(255,255,255,0.05);color:#f87171}
    .char-counter{font-size:0.7rem;margin-left:0.5rem;color:#94a3b8}
    .char-counter.warning{color:#f97316}
    .char-counter.danger{color:#ef4444}
    .notification-toggle{background:rgba(167,139,250,0.3) !important;border-color:#a78bfa !important}
    @media(max-width:400px){:root{--bf:14px}.header h1{font-size:1.4rem}.stat{padding:0.3rem 0.8rem;font-size:0.7rem}.av{width:2rem;height:2rem;font-size:0.75rem}.msg{padding:0.7rem}.input-row{flex-wrap:wrap}.input-row input#msg_input{padding:0.6rem 0.8rem}.send-button{padding:0.6rem 1.2rem;width:100%}}
    </style></head><body><div id="loginOverlay" class="login-overlay"><div class="login-box"><h2>💬 Welcome to HIVE</h2><input type="text" id="loginName" placeholder="Choose your username" maxlength="20"><button onclick="doLogin()">Enter Chat</button></div></div><div class="app" id="appMain" style="display:none"><div class="header"><h1>💬 HIVE ChatRoom ''' + version_bytes + b'''</h1><div class="badge">⚡ ''' + ALPHA_BETA.encode() + b''' · v''' + version_bytes + b'''</div></div><div class="stats-bar" id="statsBar"><div class="stat" id="tempStat"><span class="stat-icon">🌡️</span> ''' + temp_str.encode() + b'''</div><div class="stat" id="humStat"><span class="stat-icon">💧</span> ''' + hum_str.encode() + b'''</div><div class="stat" id="uptimeStat"><span class="stat-icon">⏱️</span> ''' + uptime.encode() + b'''</div><div class="stat" id="msgCountStat"><span class="stat-icon">💬</span> ''' + str(msg_count).encode() + b'''</div></div><div id="systemLogPanel"><div style="display:flex;justify-content:space-between;align-items:center"><span style="font-size:0.8rem;color:#94a3b8">⚙️ System Issues</span><button onclick="document.getElementById('systemLogPanel').style.display='none'" style="background:none;border:none;color:#94a3b8;cursor:pointer;font-size:1.2rem">✖</button></div><div id="systemLogContent"></div></div><div class="messages-container" id="msgContainer">''' + pinned_html + msg_html + b'''</div><div id="inputArea"><div id="replyIndicator" style="display:none" class="reply-indicator"><span id="replyInfoText"></span><button class="cancel-reply" onclick="clearReply()">Cancel</button></div><form id="msgForm"><div class="input-row"><input type="text" id="msg_input" name="msg" placeholder="Type a message (max 400 chars)..." maxlength="400" required><span id="charCounter" class="char-counter">0/400</span><input type="hidden" id="reply_to" name="reply" value="0"><button class="send-button" type="submit" id="sendBtn">Send</button></div></form><div class="menu-buttons"><button onclick="location.reload()">🔄 Refresh</button><a href="/download_msgs" target="_blank">⬇️ Msgs</a><a href="/download_temps" target="_blank">🌡️ Log</a><button onclick="toggleScroll()">📌 Scroll</button><button onclick="changeName()">🔄 Change name</button><button id="notifyBtn" class="notification-toggle">🔔 Enable Notifications</button></div></div></div><div id="toast" class="toast"></div><script>
    let lastMsgId=''' + str(max_msg_id).encode() + b''';let currentReplyTo=0;let currentReplyName='';let scrollAuto=true;let sending=false;let currentUser='';let notificationsEnabled=false;let notificationPermissionGranted=false;const MAX_MSG_LEN=400;
    function fixMessagePadding(){let i=document.getElementById('inputArea');let m=document.getElementById('msgContainer');if(i&&m){m.style.paddingBottom=(i.offsetHeight+8)+'px'}}
    function doLogin(){let n=document.getElementById('loginName').value.trim();if(!n){showToast('Please enter a name');return}currentUser=n;localStorage.setItem('chat_username',n);document.getElementById('loginOverlay').style.display='none';document.getElementById('appMain').style.display='flex';fixMessagePadding();initApp()}
    function changeName(){localStorage.removeItem('chat_username');document.getElementById('loginOverlay').style.display='flex';document.getElementById('appMain').style.display='none';document.getElementById('loginName').value='';currentUser='';notificationsEnabled=false;updateNotifyButton()}
    function initApp(){updateAllTimes();setInterval(updateAllTimes,60000);attachReplyHandlers();document.querySelectorAll('.msg').forEach(el=>{let u=el.dataset.username;let t=el.querySelector('.mt')?.innerText;if(u==='System'&&t&&t.startsWith('⚠️')){appendSystemLog(t)}});setInterval(pollNewMessages,3000);setInterval(updateStats,5000);updateStats();setupNotifications();setupCharCounter();}
    function setupCharCounter(){let input=document.getElementById('msg_input');let counter=document.getElementById('charCounter');if(!input||!counter)return;input.addEventListener('input',function(){let len=this.value.length;counter.innerText=len+'/'+MAX_MSG_LEN;counter.classList.remove('warning','danger');if(len>MAX_MSG_LEN*0.9){counter.classList.add('danger');}else if(len>MAX_MSG_LEN*0.7){counter.classList.add('warning');}});input.dispatchEvent(new Event('input'));}
    function setupNotifications(){if(!('Notification' in window)){console.log('Browser does not support notifications');document.getElementById('notifyBtn').style.display='none';return;}let btn=document.getElementById('notifyBtn');let storedPref=localStorage.getItem('notifications_enabled');if(storedPref==='true'){if(Notification.permission==='granted'){notificationsEnabled=true;notificationPermissionGranted=true;btn.innerText='🔕 Notifications ON';btn.classList.add('notification-toggle');}else if(Notification.permission==='default'){Notification.requestPermission().then(perm=>{if(perm==='granted'){notificationsEnabled=true;notificationPermissionGranted=true;localStorage.setItem('notifications_enabled','true');btn.innerText='🔕 Notifications ON';showToast('Notifications enabled');}else{btn.innerText='🔔 Enable Notifications';}});}else{btn.innerText='🔔 Enable Notifications';notificationsEnabled=false;}}else{btn.innerText='🔔 Enable Notifications';notificationsEnabled=false;}btn.onclick=function(){if(!('Notification' in window)){showToast('Notifications not supported');return;}if(Notification.permission==='granted'){notificationsEnabled=!notificationsEnabled;localStorage.setItem('notifications_enabled',notificationsEnabled);if(notificationsEnabled){btn.innerText='🔕 Notifications ON';showToast('Notifications ON');}else{btn.innerText='🔔 Enable Notifications';showToast('Notifications OFF');}}else if(Notification.permission==='default'){Notification.requestPermission().then(perm=>{if(perm==='granted'){notificationsEnabled=true;notificationPermissionGranted=true;localStorage.setItem('notifications_enabled','true');btn.innerText='🔕 Notifications ON';showToast('Notifications enabled');}else{showToast('Notification permission denied');btn.innerText='🔔 Enable Notifications';}});}else{showToast('Notifications blocked by browser');}};}
    function showNotification(msgUser,msgText,msgId){if(!notificationsEnabled)return;if(Notification.permission!=='granted')return;if(msgUser===currentUser)return;let title=`💬 New message from ${msgUser}`;let body=msgText.length>60?msgText.substring(0,57)+'...':msgText;let options={body:body,icon:'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23a78bfa"%3E%3Cpath d="M20 2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h4l4 4 4-4h4c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"%3E%3C/path%3E%3C/svg%3E',silent:false};let notification=new Notification(title,options);notification.onclick=function(){window.focus();let msgDiv=document.querySelector(`.msg[data-id='${msgId}']`);if(msgDiv){msgDiv.scrollIntoView({behavior:'smooth',block:'center'});msgDiv.style.backgroundColor='rgba(167,139,250,0.2)';setTimeout(()=>{msgDiv.style.backgroundColor='';},1000);}};setTimeout(()=>{notification.close();},5000);}
    window.onload=function(){let n=localStorage.getItem('chat_username');if(n){currentUser=n;document.getElementById('loginOverlay').style.display='none';document.getElementById('appMain').style.display='flex';fixMessagePadding();initApp();}else{document.getElementById('loginOverlay').style.display='flex';document.getElementById('appMain').style.display='none';document.getElementById('loginName').focus();}window.addEventListener('resize',fixMessagePadding)};
    function simpleHash(s){let h=0;for(let i=0;i<s.length;i++){h=(h*31+s.charCodeAt(i))&0xFFFFFFFF}return h}
    function formatRelativeTime(ts){if(!ts||ts==0)return'';let n=Math.floor(Date.now()/1000);let d=n-ts;if(d<60)return'just now';if(d<3600)return Math.floor(d/60)+' min ago';if(d<86400)return Math.floor(d/3600)+' h ago';return Math.floor(d/86400)+' d ago'}
    function updateAllTimes(){document.querySelectorAll('.tm').forEach(el=>{let ts=parseInt(el.dataset.timestamp);if(ts&&ts!=0)el.innerText=formatRelativeTime(ts);else el.innerText=''})}
    function copyText(el){navigator.clipboard.writeText(el.innerText);showToast('📋 Copied!')}
    function showToast(msg){let t=document.getElementById('toast');if(!t){t=document.createElement('div');t.id='toast';t.className='toast';document.body.appendChild(t)}t.innerText=msg;t.style.opacity='1';setTimeout(()=>t.style.opacity='0',1800)}
    function toggleScroll(){scrollAuto=!scrollAuto;showToast(scrollAuto?'Auto-scroll ON':'Auto-scroll OFF')}
    function clearReply(){currentReplyTo=0;currentReplyName='';document.getElementById('reply_to').value='0';document.getElementById('replyIndicator').style.display='none'}
    function appendSystemLog(text){let c=document.getElementById('systemLogContent');let p=document.getElementById('systemLogPanel');let d=document.createElement('div');d.className='system-log-item';d.textContent=text;c.appendChild(d);p.style.display='block';while(c.children.length>12){c.removeChild(c.firstChild)}}
    function appendServerMessage(msg){let c=document.getElementById('msgContainer');if(document.querySelector(`.msg[data-id='${msg.id}']`))return;let hue=Math.abs(simpleHash(msg.user))%360;let avStyle=`background:hsl(${hue},70%,55%);`;let replyBadge='';if(msg.reply!==0&&msg.reply_user){replyBadge=`<span class="reply-badge">↩️ ${escapeHtml(msg.reply_user)}</span>`}let div=document.createElement('div');div.className='msg';div.dataset.id=msg.id;div.dataset.username=msg.user;div.dataset.time=msg.timestamp;div.innerHTML=`<div class="av" style="${avStyle}">${escapeHtml(msg.user.substring(0,2).toUpperCase())}</div><div class="mc"><div class="mh"><span class="un">${escapeHtml(msg.user)}</span><span class="tm" data-timestamp="${msg.timestamp}">${formatRelativeTime(msg.timestamp)}</span>${replyBadge}</div><div class="mt" onclick="copyText(this)">${escapeHtml(msg.text)}</div><div class="ma"><button class="rb" data-id="${msg.id}" data-name="${escapeHtml(msg.user)}">💬 Reply</button></div></div>`;div.querySelector('.rb').onclick=function(e){e.stopPropagation();currentReplyTo=msg.id;currentReplyName=msg.user;document.getElementById('reply_to').value=currentReplyTo;document.getElementById('replyIndicator').style.display='flex';document.getElementById('replyInfoText').innerText='Replying to '+currentReplyName;document.getElementById('msg_input').focus()};c.appendChild(div);if(scrollAuto)c.scrollTop=c.scrollHeight;if(msg.user==='System'&&msg.text.startsWith('⚠️')){appendSystemLog(msg.text)}showNotification(msg.user,msg.text,msg.id);}
    function escapeHtml(str){return str.replace(/[&<>]/g,function(m){if(m==='&')return'&amp;';if(m==='<')return'&lt;';if(m==='>')return'&gt;';return m;});}
    async function pollNewMessages(){if(sending)return;try{let r=await fetch(`/api/msg_poll?since=${lastMsgId}`);if(!r.ok)return;let d=await r.json();if(!d.messages||!Array.isArray(d.messages)||d.messages.length===0)return;for(let msg of d.messages){appendServerMessage(msg)}let ids=d.messages.map(m=>m.id);let maxId=Math.max(...ids);if(!isNaN(maxId))lastMsgId=maxId;if(d.total!==undefined){document.getElementById('msgCountStat').innerHTML='<span class="stat-icon">💬</span> '+d.total}}catch(e){console.error('Poll error:',e)}}
    async function updateStats(){try{let r=await fetch('/api/stats');if(!r.ok)return;let s=await r.json();document.getElementById('tempStat').innerHTML='<span class="stat-icon">🌡️</span> '+s.temp;document.getElementById('humStat').innerHTML='<span class="stat-icon">💧</span> '+s.hum;document.getElementById('uptimeStat').innerHTML='<span class="stat-icon">⏱️</span> '+s.uptime;document.getElementById('msgCountStat').innerHTML='<span class="stat-icon">💬</span> '+s.msg_count}catch(e){console.error('Stats error:',e)}}
    document.getElementById('msgForm').addEventListener('submit',async(e)=>{e.preventDefault();if(sending||!currentUser)return;let msg=document.getElementById('msg_input').value.trim();if(!msg){showToast('Message cannot be empty');return;}if(msg.length>MAX_MSG_LEN){showToast(`Message too long (max ${MAX_MSG_LEN} chars)`);return;}let reply=document.getElementById('reply_to').value;sending=true;let btn=document.getElementById('sendBtn');btn.disabled=true;btn.textContent='⏳';let params=new URLSearchParams({name:currentUser,msg,reply,ajax:'1'});try{let r=await fetch('/send?'+params.toString());let d=await r.json();if(d.success){let msgObj={id:d.id,time:d.time,user:currentUser,text:msg,reply:parseInt(reply),reply_user:currentReplyName,timestamp:Math.floor(Date.now()/1000)};appendServerMessage(msgObj);lastMsgId=d.id;document.getElementById('msgCountStat').innerHTML='<span class="stat-icon">💬</span> '+d.total;document.getElementById('msg_input').value='';clearReply();let counter=document.getElementById('charCounter');if(counter)counter.innerText='0/'+MAX_MSG_LEN;}else{showToast('Error sending message')}}catch(err){showToast('Network error - retry')}finally{sending=false;btn.disabled=false;btn.textContent='Send';document.getElementById('msg_input').focus()}});
    function attachReplyHandlers(){document.querySelectorAll('.rb').forEach(btn=>{btn.onclick=function(e){e.stopPropagation();currentReplyTo=parseInt(this.dataset.id);currentReplyName=this.dataset.name;document.getElementById('reply_to').value=currentReplyTo;document.getElementById('replyIndicator').style.display='flex';document.getElementById('replyInfoText').innerText='Replying to '+currentReplyName;document.getElementById('msg_input').focus()}})}
    function updateNotifyButton(){let btn=document.getElementById('notifyBtn');if(btn){if(notificationsEnabled){btn.innerText='🔕 Notifications ON';}else{btn.innerText='🔔 Enable Notifications';}}}
    </script></body></html>'''
    gc.collect()
    return html.replace(b'\n', b'\r\n')

# ======================== صفحه آپدیت و API تکه‌تکه ========================
def update_page_html():
    return b'''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>HIVE Update - Wireless BIOS</title><style>
    *{margin:0;padding:0;box-sizing:border-box}body{background:#0b0f19;font-family:'Segoe UI',system-ui;color:#e2e8f0;display:flex;justify-content:center;align-items:center;min-height:100vh;padding:20px}
    .container{max-width:500px;width:100%;background:rgba(21,28,44,0.8);backdrop-filter:blur(10px);border-radius:28px;border:1px solid rgba(255,255,255,0.08);padding:2rem;box-shadow:0 25px 50px -12px rgba(0,0,0,0.5)}
    h1{font-size:1.8rem;margin-bottom:0.5rem;background:linear-gradient(to right,#a78bfa,#f472b6);-webkit-background-clip:text;background-clip:text;color:transparent}
    .desc{margin-bottom:1.5rem;color:#94a3b8;font-size:0.9rem}
    input,button{width:100%;padding:0.8rem;border-radius:40px;background:#0f172a;border:1px solid #334155;color:#f1f5f9;font-size:1rem;margin-bottom:1rem;outline:none}
    input:focus{border-color:#a78bfa;box-shadow:0 0 0 2px rgba(167,139,250,0.3)}
    button{background:linear-gradient(135deg,#7c3aed,#ec4899);border:none;font-weight:bold;cursor:pointer;transition:transform 0.1s}
    button:active{transform:scale(0.97)}
    #progressBar{height:6px;background:#1e293b;border-radius:3px;margin:1rem 0;overflow:hidden;display:none}
    #progressFill{width:0%;height:100%;background:linear-gradient(90deg,#a78bfa,#f472b6);transition:width 0.3s}
    #status{padding:0.8rem;border-radius:20px;margin-top:1rem;text-align:center;font-size:0.9rem}
    .success{background:#064e3b;color:#a7f3d0}
    .error{background:#7f1d1d;color:#fecaca}
    .info{background:#1e293b;color:#cbd5e0}
    </style></head><body><div class="container"><h1>⚙️ Firmware Update</h1><div class="desc">Upload main.py (chunked upload, max 100KB). Backup will be created.</div>
    <input type="password" id="updatePass" placeholder="Admin Password">
    <input type="file" id="fileInput" accept=".py">
    <button onclick="doUpdate()">Upload & Update</button>
    <div id="progressBar"><div id="progressFill"></div></div>
    <div id="status"></div>
    <button onclick="location.reload()" style="background:#334155; margin-top:0.5rem">↻ Refresh</button>
    </div><script>
    const CHUNK_SIZE = 4096;
    async function doUpdate(){let pass=document.getElementById('updatePass').value;let file=document.getElementById('fileInput').files[0];if(!pass||!file){showStatus('Please enter password and select a file','error');return;}if(!file.name.endsWith('.py')){showStatus('Only .py files allowed','error');return;}let totalChunks=Math.ceil(file.size/CHUNK_SIZE);showStatus('Initializing...','info');document.getElementById('progressBar').style.display='block';let uploaded=0;let success=true;for(let i=0;i<totalChunks;i++){let start=i*CHUNK_SIZE;let end=Math.min(start+CHUNK_SIZE,file.size);let chunk=file.slice(start,end);let base64=await new Promise(resolve=>{let r=new FileReader();r.onload=()=>resolve(r.result.split(',')[1]);r.readAsDataURL(chunk);});let data={password:pass,filename:file.name,chunkIndex:i,totalChunks:totalChunks,dataBase64:base64};try{let resp=await fetch('/api/upload_chunk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});let result=await resp.json();if(!result.success){showStatus('Upload failed at chunk '+(i+1)+': '+result.message,'error');success=false;break;}uploaded=i+1;let percent=Math.floor((uploaded/totalChunks)*100);document.getElementById('progressFill').style.width=percent+'%';showStatus('Uploading: '+percent+'%','info');}catch(err){showStatus('Network error at chunk '+(i+1),'error');success=false;break;}}if(success){showStatus('✅ Update successful! Rebooting...','success');setTimeout(()=>{window.location.href='/';},2000);}else{document.getElementById('progressBar').style.display='none';}}
    function showStatus(msg,type){let st=document.getElementById('status');st.textContent=msg;st.className='';st.classList.add(type);}
    </script></body></html>'''

def handle_upload_chunk(post_data):
    global upload_session
    try:
        data = json.loads(post_data.decode('utf-8'))
        password = data.get('password', '')
        if ADMIN_PASS == "CHANGE_ME_TO_A_LONG_UNIQUE_PASSWORD" or password != ADMIN_PASS:
            return json.dumps({"success": False, "message": "Invalid password"}).encode()
        filename = data.get('filename', '')
        if not filename.endswith('.py'):
            return json.dumps({"success": False, "message": "Only .py files allowed"}).encode()
        chunk_idx = data.get('chunkIndex', 0)
        total = data.get('totalChunks', 0)
        chunk_b64 = data.get('dataBase64', '')
        if not chunk_b64:
            return json.dumps({"success": False, "message": "No chunk data"}).encode()
        try:
            chunk_data = ubinascii.a2b_base64(chunk_b64)
        except:
            return json.dumps({"success": False, "message": "Base64 decode failed"}).encode()
        
        if chunk_idx == 0:
            if upload_session is not None:
                try:
                    upload_session['file'].close()
                except:
                    pass
                try:
                    os.remove('upload_temp.tmp')
                except:
                    pass
            try:
                temp_file = open('upload_temp.tmp', 'wb')
                upload_session = {'filename': filename, 'total': total, 'received': 0, 'file': temp_file}
            except Exception as e:
                return json.dumps({"success": False, "message": f"Cannot create temp file: {e}"}).encode()
        
        if upload_session is None:
            return json.dumps({"success": False, "message": "No active upload session"}).encode()
        
        try:
            upload_session['file'].write(chunk_data)
            upload_session['received'] += 1
        except Exception as e:
            return json.dumps({"success": False, "message": f"Write error: {e}"}).encode()
        
        if upload_session['received'] == total:
            upload_session['file'].close()
            try:
                if "main.py" in os.listdir():
                    with open("main.py", "rb") as f:
                        old = f.read()
                    with open("main.bak", "wb") as f:
                        f.write(old)
            except:
                pass
            try:
                os.rename('upload_temp.tmp', 'main.py')
            except:
                with open('upload_temp.tmp', 'rb') as src:
                    with open('main.py', 'wb') as dst:
                        dst.write(src.read())
                os.remove('upload_temp.tmp')
            upload_session = None
            return json.dumps({"success": True, "message": "File uploaded successfully. Rebooting..."}).encode()
        else:
            return json.dumps({"success": True, "message": f"Chunk {chunk_idx+1}/{total} received"}).encode()
    except Exception as e:
        system_error("Upload chunk error", e)
        if upload_session:
            try:
                upload_session['file'].close()
            except:
                pass
            upload_session = None
        return json.dumps({"success": False, "message": str(e)}).encode()

# ============================== هندلر دستورات ادمین ==============================
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
        if ADMIN_PASS == "CHANGE_ME_TO_A_LONG_UNIQUE_PASSWORD" or len(args) < 2 or args[1] != ADMIN_PASS:
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
        if ADMIN_PASS == "CHANGE_ME_TO_A_LONG_UNIQUE_PASSWORD" or len(args) < 1 or args[0] != ADMIN_PASS:
            return True, ("System", "Unpin requires admin password: admin: unpin <password>")
        save_pinned(0)
        return True, ("System", "Pinned message removed")
    if ADMIN_PASS == "CHANGE_ME_TO_A_LONG_UNIQUE_PASSWORD" or not args or args[0] != ADMIN_PASS:
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

# ============================== راه‌اندازی اولیه ==============================
print("System starting")
load_messages()
if len(messages) == 0:
    add_message("System", f"Welcome to HIVE {VERSION} (Alpha)! 🚀", 0)

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

if uart:
    print("Resetting ESP...")
    send_cmd(b'AT+RST', b'ready', 5000)
    time.sleep(2)
    send_cmd(b'AT+CWMODE=1', b'OK')
    print("Connecting to WiFi...")
    if not send_cmd(b'AT+CWJAP="' + SSID.encode() + b'","' + PASSWORD.encode() + b'"', b'OK', 20000):
        system_error("WiFi connection failed! Server offline.")
        uart = None
    else:
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

last_temp_log = time.ticks_ms()

# ============================== حلقه اصلی ==============================
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

                # ---------- صفحه آپدیت ----------
                if method == b'GET' and path == b'/update':
                    resp_body = update_page_html()
                    headers = b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                    full_resp = headers + resp_body
                    send_large_response(conn_id, full_resp)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()
                    continue

                if method == b'POST' and path == b'/api/upload_chunk':
                    body_start = req.find(b'\r\n\r\n')
                    if body_start == -1:
                        resp = json.dumps({"success": False, "message": "Bad request"}).encode()
                        headers = b'HTTP/1.1 400 Bad Request\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        full_resp = headers + resp
                        send_small_response(conn_id, full_resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue
                    body = req[body_start+4:]
                    resp_body = handle_upload_chunk(body)
                    headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                    full_resp = headers + resp_body
                    send_small_response(conn_id, full_resp)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()
                    try:
                        if json.loads(resp_body)["success"] and "Rebooting" in json.loads(resp_body)["message"]:
                            time.sleep(1)
                            machine.reset()
                    except:
                        pass
                    continue

                # ---------- مسیرهای اصلی چت ----------
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
                    try:
                        html = html_page()
                    except MemoryError:
                        gc.collect()
                        html = b'HTTP/1.1 500 Memory Error\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nServer out of memory. Please try again.'
                        send_small_response(conn_id, html)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue
                    headers = b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: ' + str(len(html)).encode() + b'\r\nConnection: close\r\n\r\n'
                    full_response = headers + html
                    send_large_response(conn_id, full_response)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()

                elif method == b'GET' and path == b'/send':
                    params = {}
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
                    if ADMIN_PASS != "CHANGE_ME_TO_A_LONG_UNIQUE_PASSWORD" and user_pass == ADMIN_PASS:
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