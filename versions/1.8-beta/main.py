import machine
import time
import os
import gc
import dht
import json
import sys

SSID = "YOUR_WIFI_SSID"
PASSWORD = "YOUR_WIFI_PASSWORD"
PORT = 80
MAX_MSGS = 100
DISPLAY_MSGS = 20
MIN_FREE_MEM = 40000

DHT_PIN = 0

messages = []
next_id = 1

TEMP_LOG_FILE = "temp_log.txt"
TEMP_LOG_INTERVAL_MS = 60000        # هر دقیقه

last_dht_read = 0
last_dht_temp = None
last_dht_hum = None
dht_error_printed = False
system_error_logged = {}

VERSION = "1.8 - Beta"

# ===== Watchdog (reset after 5 min hang) =====
try:
    wdt = machine.WDT(timeout=300000)  # 5 دقیقه
    print("Watchdog activated (5 min)")
except Exception as e:
    print("Watchdog not available:", e)
    wdt = None

def simple_hash(s):
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h

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
    text_sanitized = sanitize(text.encode()).strip()
    if not text_sanitized:
        return None
    username_sanitized = sanitize(username.encode())[:20]
    if not username_sanitized:
        username_sanitized = b"Anonymous"
    t = time.localtime()
    time_str = "%02d:%02d:%02d" % (t[3], t[4], t[5])
    timestamp_unix = time.mktime(t)
    msg_id = next_id
    next_id += 1
    line = b"%d|%s|%s|%s|%d|%d" % (msg_id, time_str.encode(), username_sanitized, text_sanitized[:200], reply_to, timestamp_unix)
    messages.append(line)
    if len(messages) > MAX_MSGS:
        messages.pop(0)
    save_messages()
    print(f"Message added: id={msg_id}, user={username_sanitized}, reply={reply_to}")
    return msg_id, time_str

def system_error(err_msg, exc=None):
    global system_error_logged
    key = err_msg[:50]
    now = time.time()
    t = time.localtime()
    ts = f"{t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
    if exc:
        # نمایش نوع و پیام خطا در کنسول
        sys.print_exception(exc)
        print(f"[SYSTEM ERROR] {ts}: {err_msg} | Exception: {exc}")
        # ساخت پیام کامل برای نمایش در چت
        exc_type = type(exc).__name__
        exc_msg = str(exc)
        # محدود کردن طول برای جلوگیری از اندازه بیش از حد
        if len(exc_msg) > 60:
            exc_msg = exc_msg[:57] + "..."
        full_msg = f"⚠️ {err_msg} | {exc_type}: {exc_msg}"
    else:
        print(f"[SYSTEM ERROR] {ts}: {err_msg}")
        full_msg = f"⚠️ {err_msg}"

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

def html_page():
    gc.collect()
    free_mem = gc.mem_free()
    print(f"Free memory before page gen: {free_mem}")

    if free_mem < MIN_FREE_MEM:
        display_count = 10
        system_error("Low memory: showing only last 10 messages")
    else:
        display_count = DISPLAY_MSGS

    temp_str, hum_str, uptime, msg_count = get_system_stats()
    msgs_to_show = messages[-display_count:] if len(messages) > display_count else messages

    max_msg_id = 0
    for m in messages:
        parts = m.split(b'|')
        if parts and parts[0].isdigit():
            mid = int(parts[0])
            if mid > max_msg_id:
                max_msg_id = mid

    msg_html = b''
    for m in msgs_to_show:
        parts = m.split(b'|')
        if len(parts) < 5:
            continue
        mid = int(parts[0])
        username = parts[2].decode()
        txt = parts[3].decode()
        reply_to = int(parts[4])
        timestamp_unix = int(parts[5]) if len(parts) > 5 else 0

        h = simple_hash(username)
        hue = h % 360
        avatar_style = f"background: hsl({hue}, 70%, 55%);"

        reply_html = b''
        if reply_to != 0:
            replied_name = get_message_by_id(reply_to)
            if replied_name:
                reply_html = b'<span class="reply-badge">↩️ ' + replied_name.encode() + b'</span>'

        msg_html += b'<div class="message" data-id="%d" data-username="%s" data-time="%d">' % (mid, username.encode(), timestamp_unix)
        msg_html += b'<div class="avatar" style="' + avatar_style.encode() + b'">' + username[:2].upper().encode() + b'</div>'
        msg_html += b'<div class="message-content">'
        msg_html += b'<div class="message-header"><span class="username">' + username.encode() + b'</span>'
        msg_html += b'<span class="time" data-timestamp="%d"></span>' % timestamp_unix
        if reply_html:
            msg_html += reply_html
        msg_html += b'</div>'
        msg_html += b'<div class="message-text" onclick="copyText(this)">' + txt.encode() + b'</div>'
        msg_html += b'<div class="message-actions"><button class="reply-button" data-id="%d" data-name="%s">💬 Reply</button></div>' % (mid, username.encode())
        msg_html += b'</div></div>'

    version_bytes = VERSION.encode()
    html = b'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=yes, viewport-fit=cover">
    <title>HIVE ChatRoom ''' + version_bytes + b'''</title>
    <style>
        :root {
            --base-font-size: 16px;
            --bg: #0b0f19;
            --surface: #151c2c;
            --surface-light: #1e293b;
            --primary: #a78bfa;
            --accent: #f472b6;
            --text: #e2e8f0;
            --text-muted: #94a3b8;
            --border: rgba(255,255,255,0.08);
            --radius: 18px;
            --radius-lg: 24px;
        }
        * { margin:0; padding:0; box-sizing:border-box; }
        html { font-size: var(--base-font-size); }
        body {
            background: var(--bg);
            font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
            color: var(--text);
            height: 100dvh;
            overflow: hidden;
            -webkit-overflow-scrolling: touch;
            display: flex;
            justify-content: center;
            align-items: center;
        }
        .app {
            width: 100%;
            height: 100%;
            max-width: 600px;
            background: rgba(21,28,44,0.6);
            backdrop-filter: blur(20px);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            box-shadow: 0 0 60px rgba(168,85,247,0.08);
        }
        @media (min-width: 640px) {
            .app {
                border-radius: var(--radius-lg);
                margin: 16px;
                height: calc(100% - 32px);
                border: 1px solid var(--border);
            }
        }

        /* Login Modal */
        .login-overlay {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: rgba(11,15,25,0.95);
            backdrop-filter: blur(20px);
            display: flex;
            justify-content: center;
            align-items: center;
            z-index: 200;
            transition: opacity 0.4s;
        }
        .login-box {
            background: rgba(21,28,44,0.8);
            backdrop-filter: blur(20px);
            border: 1px solid var(--border);
            border-radius: var(--radius-lg);
            padding: 2rem;
            width: 90%;
            max-width: 360px;
            text-align: center;
            animation: fadeInScale 0.5s ease;
        }
        @keyframes fadeInScale {
            from { opacity:0; transform:scale(0.9); }
            to { opacity:1; transform:scale(1); }
        }
        .login-box h2 {
            font-size: 1.8rem;
            margin-bottom: 1.5rem;
            background: linear-gradient(to right, #a78bfa, #f472b6);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
        }
        .login-box input {
            width: 100%;
            padding: 0.8rem 1rem;
            border-radius: 25px;
            background: #0f172a;
            border: 1px solid #334155;
            color: #f1f5f9;
            font-size: 0.9rem;
            margin-bottom: 1rem;
            outline: none;
        }
        .login-box input:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 2px rgba(167,139,250,0.3);
        }
        .login-box button {
            width: 100%;
            padding: 0.8rem;
            border-radius: 25px;
            background: linear-gradient(135deg, #7c3aed, #ec4899);
            border: none;
            color: white;
            font-weight: bold;
            font-size: 1rem;
            cursor: pointer;
        }

        .header {
            background: linear-gradient(135deg, rgba(124,58,237,0.15), rgba(236,72,153,0.1));
            padding: 1.2rem 1.5rem;
            border-bottom: 1px solid var(--border);
            text-align: center;
            position: relative;
            flex-shrink: 0;
        }
        .header h1 {
            font-size: 1.6rem;
            font-weight: 800;
            background: linear-gradient(to right, #a78bfa, #f472b6);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            animation: titlePulse 3s ease-in-out infinite alternate;
        }
        @keyframes titlePulse {
            from { filter: brightness(1); }
            to { filter: brightness(1.3); }
        }
        .badge {
            font-size: 0.7rem;
            background: rgba(45,55,72,0.8);
            display: inline-block;
            padding: 0.3rem 1rem;
            border-radius: 20px;
            margin-top: 0.3rem;
            color: #cbd5e0;
            letter-spacing: 0.5px;
            border: 1px solid var(--border);
            backdrop-filter: blur(4px);
        }

        .stats-bar {
            display: flex;
            background: rgba(0,0,0,0.3);
            backdrop-filter: blur(12px);
            padding: 0.6rem 1rem;
            gap: 0.6rem;
            border-bottom: 1px solid var(--border);
            overflow-x: auto;
            white-space: nowrap;
            flex-shrink: 0;
        }
        .stat {
            background: linear-gradient(135deg, #1e293b, #0f172a);
            padding: 0.4rem 1rem;
            border-radius: 30px;
            font-size: 0.75rem;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 0.4rem;
            border: 1px solid var(--border);
            box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        }
        .stat-icon { font-size: 0.9rem; }

        .messages-container {
            flex: 1;
            overflow-y: auto;
            padding: 1rem;
            padding-bottom: 100px;
            display: flex;
            flex-direction: column;
            gap: 0.8rem;
            scroll-behavior: smooth;
            -webkit-overflow-scrolling: touch;
        }
        .message {
            display: flex;
            gap: 0.7rem;
            background: rgba(30,41,59,0.5);
            backdrop-filter: blur(8px);
            border-radius: var(--radius);
            padding: 0.8rem;
            border: 1px solid var(--border);
            animation: fadeInUp 0.3s ease;
        }
        @keyframes fadeInUp {
            from { opacity: 0; transform: translateY(0.6rem); }
            to { opacity: 1; transform: translateY(0); }
        }
        .message:hover {
            background: rgba(51,65,85,0.6);
            border-color: rgba(255,255,255,0.1);
        }
        .avatar {
            width: 2.4rem;
            height: 2.4rem;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: bold;
            font-size: 0.85rem;
            color: white;
            flex-shrink: 0;
            border: 2px solid rgba(255,255,255,0.2);
        }
        .message-content { flex: 1; }
        .message-header {
            display: flex;
            align-items: baseline;
            gap: 0.5rem;
            flex-wrap: wrap;
            margin-bottom: 0.3rem;
        }
        .username {
            font-weight: 700;
            color: var(--primary);
            font-size: 0.85rem;
        }
        .time {
            font-size: 0.65rem;
            color: var(--text-muted);
        }
        .reply-badge {
            font-size: 0.65rem;
            background: rgba(71,85,105,0.7);
            padding: 0.2rem 0.6rem;
            border-radius: 20px;
            color: #e2e8f0;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .message-text {
            font-size: 0.9rem;
            line-height: 1.45;
            margin: 0.4rem 0;
            word-break: break-word;
            cursor: pointer;
            padding: 0.2rem 0;
        }
        .reply-button {
            background: none;
            border: 1px solid #475569;
            color: #cbd5e0;
            font-size: 0.7rem;
            padding: 0.3rem 0.8rem;
            border-radius: 20px;
            cursor: pointer;
            transition: 0.2s;
        }
        .reply-button:hover {
            background: var(--primary);
            border-color: var(--primary);
            color: white;
        }

        #inputArea {
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            max-width: 600px;
            margin: 0 auto;
            background: rgba(15,23,42,0.9);
            backdrop-filter: blur(12px);
            border-top: 1px solid var(--border);
            padding: 0.8rem 1rem;
            padding-bottom: calc(0.8rem + env(safe-area-inset-bottom, 0px));
            z-index: 10;
        }
        .reply-indicator {
            background: #4c1d95;
            border-radius: 25px;
            padding: 0.5rem 1rem;
            margin-bottom: 0.6rem;
            font-size: 0.75rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            animation: slideDown 0.2s ease;
        }
        @keyframes slideDown {
            from { opacity: 0; transform: translateY(-0.5rem); }
            to { opacity: 1; transform: translateY(0); }
        }
        .cancel-reply {
            background: #ef4444;
            border: none;
            color: white;
            padding: 0.2rem 1rem;
            border-radius: 20px;
            cursor: pointer;
            font-size: 0.7rem;
            font-weight: 600;
        }
        .input-row {
            display: flex;
            gap: 0.5rem;
            margin-bottom: 0.5rem;
        }
        .input-row input#msg_input {
            flex: 1 1 auto;
            background: #0f172a;
            border: 1px solid #334155;
            padding: 0.7rem 1rem;
            border-radius: 25px;
            color: #f1f5f9;
            font-size: 0.85rem;
            outline: none;
            transition: border 0.2s, box-shadow 0.2s;
            min-width: 0;
        }
        .input-row input#msg_input:focus {
            border-color: var(--primary);
            box-shadow: 0 0 0 2px rgba(167,139,250,0.3);
        }
        .send-button {
            background: linear-gradient(135deg, #7c3aed, #ec4899);
            border: none;
            border-radius: 25px;
            padding: 0 1.4rem;
            font-weight: 700;
            color: white;
            cursor: pointer;
            white-space: nowrap;
            font-size: 0.85rem;
            transition: transform 0.1s;
        }
        .send-button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        .send-button:active:not(:disabled) {
            transform: scale(0.95);
        }
        .menu-buttons {
            display: flex;
            gap: 0.4rem;
            justify-content: center;
            flex-wrap: wrap;
            margin-top: 0.4rem;
        }
        .menu-buttons a, .menu-buttons button {
            background: rgba(51,65,85,0.7);
            backdrop-filter: blur(4px);
            padding: 0.35rem 0.9rem;
            border-radius: 20px;
            font-size: 0.7rem;
            color: #cbd5e0;
            text-decoration: none;
            border: 1px solid rgba(255,255,255,0.1);
            cursor: pointer;
        }
        .toast {
            position: fixed;
            bottom: 5rem;
            left: 50%;
            transform: translateX(-50%);
            background: #334155;
            color: white;
            padding: 0.5rem 1.2rem;
            border-radius: 20px;
            font-size: 0.8rem;
            opacity: 0;
            transition: opacity 0.3s;
            z-index: 1000;
            backdrop-filter: blur(8px);
            border: 1px solid rgba(255,255,255,0.2);
        }
        #systemLogPanel {
            background: rgba(30,41,59,0.9);
            padding: 0.6rem 1rem;
            border-bottom: 1px solid var(--border);
            max-height: 8rem;
            overflow-y: auto;
            display: none;
        }
        .system-log-item {
            font-size: 0.75rem;
            padding: 0.3rem 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            color: #f87171;
        }

        @media (max-width: 400px) {
            :root { --base-font-size: 14px; }
            .header h1 { font-size: 1.4rem; }
            .stat { padding: 0.3rem 0.8rem; font-size: 0.7rem; }
            .avatar { width: 2rem; height: 2rem; font-size: 0.75rem; }
            .message { padding: 0.7rem; }
            .input-row { flex-wrap: wrap; }
            .input-row input#msg_input { padding: 0.6rem 0.8rem; }
            .send-button { padding: 0.6rem 1.2rem; width: 100%; }
        }
    </style>
</head>
<body>
<!-- Login modal -->
<div id="loginOverlay" class="login-overlay">
    <div class="login-box">
        <h2>💬 Welcome to HIVE</h2>
        <input type="text" id="loginName" placeholder="Choose your username" maxlength="20">
        <button onclick="doLogin()">Enter Chat</button>
    </div>
</div>

<div class="app" id="appMain" style="display:none;">
    <div class="header">
        <h1>💬 HIVE ChatRoom ''' + version_bytes + b'''</h1>
        <div class="badge">⚡ Beta · v''' + version_bytes + b'''</div>
    </div>
    <div class="stats-bar" id="statsBar">
        <div class="stat" id="tempStat"><span class="stat-icon">🌡️</span> ''' + temp_str.encode() + b'''</div>
        <div class="stat" id="humStat"><span class="stat-icon">💧</span> ''' + hum_str.encode() + b'''</div>
        <div class="stat" id="uptimeStat"><span class="stat-icon">⏱️</span> ''' + uptime.encode() + b'''</div>
        <div class="stat" id="msgCountStat"><span class="stat-icon">💬</span> ''' + str(msg_count).encode() + b'''</div>
    </div>
    <div id="systemLogPanel">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:0.8rem; color:#94a3b8;">⚙️ System Issues</span>
            <button onclick="document.getElementById('systemLogPanel').style.display='none'" style="background:none; border:none; color:#94a3b8; cursor:pointer; font-size:1.2rem;">✖</button>
        </div>
        <div id="systemLogContent"></div>
    </div>
    <div class="messages-container" id="msgContainer">
        ''' + msg_html + b'''
    </div>
    <div id="inputArea">
        <div id="replyIndicator" style="display:none;" class="reply-indicator">
            <span id="replyInfoText"></span>
            <button class="cancel-reply" onclick="clearReply()">Cancel</button>
        </div>
        <form id="msgForm">
            <div class="input-row">
                <input type="text" id="msg_input" name="msg" placeholder="Type a message..." required>
                <input type="hidden" id="reply_to" name="reply" value="0">
                <button class="send-button" type="submit" id="sendBtn">Send</button>
            </div>
        </form>
        <div class="menu-buttons">
            <button onclick="location.reload()">🔄 Refresh</button>
            <a href="/download_msgs" target="_blank">⬇️ Msgs</a>
            <a href="/download_temps" target="_blank">🌡️ Log</a>
            <button onclick="toggleScroll()">📌 Scroll</button>
            <button onclick="clearChat()">🗑️ Clear</button>
            <button onclick="changeName()">🔄 Change name</button>
        </div>
    </div>
</div>
<div id="toast" class="toast"></div>
<script>
    let lastMsgId = ''' + str(max_msg_id).encode() + b''';
    let currentReplyTo = 0;
    let currentReplyName = '';
    let scrollAuto = true;
    let sending = false;
    let currentUser = '';

    function fixMessagePadding() {
        const input = document.getElementById('inputArea');
        const msgContainer = document.getElementById('msgContainer');
        if (input && msgContainer) {
            const height = input.offsetHeight;
            msgContainer.style.paddingBottom = (height + 8) + 'px';
        }
    }

    function doLogin() {
        const name = document.getElementById('loginName').value.trim();
        if (!name) {
            showToast('Please enter a name');
            return;
        }
        currentUser = name;
        localStorage.setItem('chat_username', name);
        document.getElementById('loginOverlay').style.display = 'none';
        document.getElementById('appMain').style.display = 'flex';
        fixMessagePadding();
        // راه‌اندازی کامل پس از ورود
        initApp();
    }

    function changeName() {
        localStorage.removeItem('chat_username');
        document.getElementById('loginOverlay').style.display = 'flex';
        document.getElementById('appMain').style.display = 'none';
        document.getElementById('loginName').value = '';
        currentUser = '';
    }

    function initApp() {
        updateAllTimes();
        setInterval(updateAllTimes, 60000);
        attachReplyHandlers();
        document.querySelectorAll('.message').forEach(el => {
            const user = el.dataset.username;
            const text = el.querySelector('.message-text')?.innerText;
            if (user === 'System' && text && text.startsWith('⚠️')) {
                appendSystemLog(text);
            }
        });
        setInterval(pollNewMessages, 3000);
        setInterval(updateStats, 5000);
        updateStats();
    }

    window.onload = function() {
        // بررسی وجود نام کاربری ذخیره شده
        const savedName = localStorage.getItem('chat_username');
        if (savedName) {
            currentUser = savedName;
            document.getElementById('loginOverlay').style.display = 'none';
            document.getElementById('appMain').style.display = 'flex';
            fixMessagePadding();
            initApp();
        } else {
            // اگر نام ذخیره نشده، صفحه ورود نشان داده شود
            document.getElementById('loginOverlay').style.display = 'flex';
            document.getElementById('appMain').style.display = 'none';
            document.getElementById('loginName').focus();
        }
        window.addEventListener('resize', fixMessagePadding);
    };

    function simpleHash(str) {
        let h = 0;
        for (let i = 0; i < str.length; i++) {
            h = (h * 31 + str.charCodeAt(i)) & 0xFFFFFFFF;
        }
        return h;
    }

    function formatRelativeTime(timestamp) {
        if (!timestamp || timestamp == 0) return '';
        const now = Math.floor(Date.now() / 1000);
        const diff = now - timestamp;
        if (diff < 60) return 'just now';
        if (diff < 3600) return Math.floor(diff/60) + ' min ago';
        if (diff < 86400) return Math.floor(diff/3600) + ' h ago';
        return Math.floor(diff/86400) + ' d ago';
    }

    function updateAllTimes() {
        document.querySelectorAll('.time').forEach(el => {
            const ts = parseInt(el.dataset.timestamp);
            if (ts && ts != 0) el.innerText = formatRelativeTime(ts);
            else el.innerText = '';
        });
    }

    function copyText(el) {
        navigator.clipboard.writeText(el.innerText);
        showToast('📋 Copied!');
    }

    function showToast(msg) {
        let toast = document.getElementById('toast');
        if (!toast) {
            toast = document.createElement('div');
            toast.id = 'toast';
            toast.className = 'toast';
            document.body.appendChild(toast);
        }
        toast.innerText = msg;
        toast.style.opacity = '1';
        setTimeout(() => toast.style.opacity = '0', 1800);
    }

    function toggleScroll() {
        scrollAuto = !scrollAuto;
        showToast(scrollAuto ? 'Auto-scroll ON' : 'Auto-scroll OFF');
    }

    function clearReply() {
        currentReplyTo = 0;
        currentReplyName = '';
        document.getElementById('reply_to').value = '0';
        document.getElementById('replyIndicator').style.display = 'none';
    }

    function appendSystemLog(text) {
        const logContent = document.getElementById('systemLogContent');
        const panel = document.getElementById('systemLogPanel');
        const div = document.createElement('div');
        div.className = 'system-log-item';
        div.textContent = text;
        logContent.appendChild(div);
        panel.style.display = 'block';
        while (logContent.children.length > 12) {
            logContent.removeChild(logContent.firstChild);
        }
    }

    function appendServerMessage(msg) {
        const container = document.getElementById('msgContainer');
        if (document.querySelector(`.message[data-id='${msg.id}']`)) return;

        const hue = Math.abs(simpleHash(msg.user)) % 360;
        const avatarStyle = `background: hsl(${hue}, 70%, 55%);`;

        let replyBadge = '';
        if (msg.reply !== 0 && msg.reply_user) {
            replyBadge = `<span class="reply-badge">↩️ ${msg.reply_user}</span>`;
        }

        const div = document.createElement('div');
        div.className = 'message';
        div.dataset.id = msg.id;
        div.dataset.username = msg.user;
        div.dataset.time = msg.timestamp;
        div.innerHTML = `
            <div class="avatar" style="${avatarStyle}">${msg.user.substring(0,2).toUpperCase()}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="username">${msg.user}</span>
                    <span class="time" data-timestamp="${msg.timestamp}">${formatRelativeTime(msg.timestamp)}</span>
                    ${replyBadge}
                </div>
                <div class="message-text" onclick="copyText(this)">${msg.text}</div>
                <div class="message-actions">
                    <button class="reply-button" data-id="${msg.id}" data-name="${msg.user}">💬 Reply</button>
                </div>
            </div>
        `;
        div.querySelector('.reply-button').onclick = function(e) {
            e.stopPropagation();
            currentReplyTo = msg.id;
            currentReplyName = msg.user;
            document.getElementById('reply_to').value = currentReplyTo;
            document.getElementById('replyIndicator').style.display = 'flex';
            document.getElementById('replyInfoText').innerText = 'Replying to ' + currentReplyName;
            document.getElementById('msg_input').focus();
        };
        container.appendChild(div);
        if (scrollAuto) container.scrollTop = container.scrollHeight;

        if (msg.user === 'System' && msg.text.startsWith('⚠️')) {
            appendSystemLog(msg.text);
        }
    }

    async function pollNewMessages() {
        if (sending) return;
        try {
            const resp = await fetch(`/api/msg_poll?since=${lastMsgId}`);
            if (!resp.ok) return;
            const data = await resp.json();
            if (!data.messages || !Array.isArray(data.messages) || data.messages.length === 0) return;

            for (const msg of data.messages) {
                appendServerMessage(msg);
            }
            const ids = data.messages.map(m => m.id);
            const maxId = Math.max(...ids);
            if (!isNaN(maxId)) lastMsgId = maxId;
            if (data.total !== undefined) {
                document.getElementById('msgCountStat').innerHTML = '<span class="stat-icon">💬</span> ' + data.total;
            }
        } catch (e) {
            console.error('Poll error:', e);
        }
    }

    async function updateStats() {
        try {
            const resp = await fetch('/api/stats');
            if (!resp.ok) return;
            const stats = await resp.json();
            document.getElementById('tempStat').innerHTML = '<span class="stat-icon">🌡️</span> ' + stats.temp;
            document.getElementById('humStat').innerHTML = '<span class="stat-icon">💧</span> ' + stats.hum;
            document.getElementById('uptimeStat').innerHTML = '<span class="stat-icon">⏱️</span> ' + stats.uptime;
            document.getElementById('msgCountStat').innerHTML = '<span class="stat-icon">💬</span> ' + stats.msg_count;
        } catch (e) {
            console.error('Stats error:', e);
        }
    }

    async function clearChat() {
        const pass = prompt('Enter admin password to clear chat:');
        if (!pass) return;
        try {
            const resp = await fetch(`/api/clear_msgs?pass=${encodeURIComponent(pass)}`);
            const data = await resp.json();
            if (data.success) {
                document.getElementById('msgContainer').innerHTML = '';
                document.getElementById('systemLogContent').innerHTML = '';
                document.getElementById('systemLogPanel').style.display = 'none';
                lastMsgId = 0;
                document.getElementById('msgCountStat').innerHTML = '<span class="stat-icon">💬</span> 0';
                await pollNewMessages();
            } else {
                showToast('Wrong password or error');
            }
        } catch (e) {
            showToast('Clear failed');
        }
    }

    document.getElementById('msgForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        if (sending || !currentUser) return;

        const msg = document.getElementById('msg_input').value.trim();
        const reply = document.getElementById('reply_to').value;

        if (!msg) return;

        sending = true;
        const sendBtn = document.getElementById('sendBtn');
        sendBtn.disabled = true;
        sendBtn.textContent = '⏳';

        const params = new URLSearchParams({ name: currentUser, msg, reply, ajax: '1' });
        try {
            const res = await fetch('/send?' + params.toString());
            const data = await res.json();
            if (data.success) {
                const msgObj = {
                    id: data.id,
                    time: data.time,
                    user: currentUser,
                    text: msg,
                    reply: parseInt(reply),
                    reply_user: currentReplyName,
                    timestamp: Math.floor(Date.now() / 1000)
                };
                appendServerMessage(msgObj);
                lastMsgId = data.id;
                document.getElementById('msgCountStat').innerHTML = '<span class="stat-icon">💬</span> ' + data.total;
                document.getElementById('msg_input').value = '';
                clearReply();
            } else {
                showToast('Error sending message');
            }
        } catch (err) {
            showToast('Network error - retry');
        } finally {
            sending = false;
            sendBtn.disabled = false;
            sendBtn.textContent = 'Send';
            document.getElementById('msg_input').focus();
        }
    });

    function attachReplyHandlers() {
        document.querySelectorAll('.reply-button').forEach(btn => {
            btn.onclick = function(e) {
                e.stopPropagation();
                currentReplyTo = parseInt(this.dataset.id);
                currentReplyName = this.dataset.name;
                document.getElementById('reply_to').value = currentReplyTo;
                document.getElementById('replyIndicator').style.display = 'flex';
                document.getElementById('replyInfoText').innerText = 'Replying to ' + currentReplyName;
                document.getElementById('msg_input').focus();
            };
        });
    }
</script>
</body>
</html>'''
    gc.collect()
    return html.replace(b'\n', b'\r\n')

def api_stats_handler():
    temp_str, hum_str, uptime, msg_count = get_system_stats()
    stats = {
        "temp": temp_str,
        "hum": hum_str,
        "uptime": uptime,
        "msg_count": msg_count
    }
    return json.dumps(stats).encode()

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

def send_small_response(conn_id, data):
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

print("System starting")
load_messages()
if len(messages) == 0:
    add_message("System", f"Welcome to HIVE {VERSION}! 🚀", 0)

try:
    uart = machine.UART(1, 115200)
    print("UART1 initialized")
except Exception as e:
    system_error("UART init error", e)
    uart = None

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
        send_cmd(b'AT+CIFSR', b'OK')
        send_cmd(b'AT+CIPMUX=1', b'OK')
        send_cmd(b'AT+CIPSERVER=1,' + str(PORT).encode(), b'OK')
        print(f"Server ready on port {PORT}")

last_temp_log = time.ticks_ms()

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
                conn_id = int(parts[1])
                remaining = parts[2]
                colon = remaining.find(b':')
                if colon == -1:
                    continue
                data_len = int(remaining[:colon])
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

                if method == b'GET' and path == b'/api/stats':
                    resp_body = api_stats_handler()
                    headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                    full_resp = headers + resp_body
                    send_small_response(conn_id, full_resp)
                    time.sleep(0.05)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()
                    continue

                if method == b'GET' and path == b'/api/msg_count':
                    resp = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\n' + str(len(messages)).encode()
                    send_small_response(conn_id, resp)
                    time.sleep(0.05)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()
                    continue

                elif method == b'GET' and path == b'/':
                    html = html_page()
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
                    time.sleep(0.05)
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
                        time_str = parts[1].decode()
                        user = parts[2].decode()
                        text = parts[3].decode()
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

                    response_obj = {
                        "total": len(messages),
                        "messages": new_msgs
                    }
                    json_str = json.dumps(response_obj)
                    resp_body = json_str.encode()
                    headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                    full_resp = headers + resp_body
                    send_small_response(conn_id, full_resp)
                    time.sleep(0.05)
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
                        add_message("System", "Chat cleared by user.")
                        resp = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{"success":true}'
                    else:
                        resp = b'HTTP/1.1 403 Forbidden\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{"success":false}'
                    send_small_response(conn_id, resp)
                    time.sleep(0.05)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()
                    continue

                elif path == b'/favicon.ico':
                    noicon = b'HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n'
                    send_small_response(conn_id, noicon)
                    time.sleep(0.05)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()

                else:
                    resp404 = b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                    send_small_response(conn_id, resp404)
                    time.sleep(0.05)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()

            except Exception as e:
                system_error("Request handling error", e)
                gc.collect()
            finally:
                if conn_id is not None:
                    try:
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        time.sleep(0.05)
                    except:
                        pass

    time.sleep(0.05)
    gc.collect()