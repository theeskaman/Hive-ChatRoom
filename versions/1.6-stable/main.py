import machine
import time
import os
import gc
import dht

# ========== تنظیمات ==========
SSID = "YOUR_WIFI_SSID"
PASSWORD = "YOUR_WIFI_PASSWORD"
PORT = 80
MAX_MSGS = 100
DISPLAY_MSGS = 20          # کاهش برای پایداری بیشتر
MIN_FREE_MEM = 40000       # حداقل رم آزاد (بایت) برای نمایش کامل

DHT_PIN = 0

messages = []
next_id = 1

TEMP_LOG_FILE = "temp_log.txt"
TEMP_LOG_INTERVAL_MS = 10000

last_dht_read = 0
last_dht_temp = None
last_dht_hum = None
dht_error_printed = False
system_error_logged = {}

VERSION = "1.6-Stable"

# ========== تابع هش ساده ==========
def simple_hash(s):
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h

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
    return msg_id

def system_error(err_msg):
    global system_error_logged
    key = err_msg[:50]
    now = time.time()
    if key in system_error_logged:
        if now - system_error_logged[key] < 30:
            return
    system_error_logged[key] = now
    short_msg = f"⚠️ {err_msg}"[:190]
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
            print(f"DHT11 error (will not repeat): {e}")
            system_error(f"DHT11 sensor error: {e}")
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
        print(f"Temp log error: {e}")
        system_error(f"Temperature log failed: {e}")

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
    gc.collect()  # آزادسازی حافظه قبل از ساخت صفحه
    free_mem = gc.mem_free()
    print(f"Free memory before page gen: {free_mem}")

    # اگر حافظه کم است، تعداد پیام‌ها را کاهش بده
    if free_mem < MIN_FREE_MEM:
        display_count = 10
        system_error("Low memory: showing only last 10 messages")
    else:
        display_count = DISPLAY_MSGS

    temp_str, hum_str, uptime, msg_count = get_system_stats()
    msgs_to_show = messages[-display_count:] if len(messages) > display_count else messages

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
    <title>HIVE ChatRoom ''' + version_bytes + b''' · Stable</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body {
            background: linear-gradient(135deg, #0B0C10, #1F2833);
            font-family: 'Inter', system-ui, -apple-system, sans-serif;
            color: #E5E9F0; height:100vh; overflow:hidden; -webkit-overflow-scrolling:touch;
        }
        .app { max-width:900px; margin:0 auto; height:100%; display:flex; flex-direction:column; backdrop-filter:blur(2px); }
        .header { background:rgba(31,40,51,0.85); padding:16px 20px; border-bottom:1px solid rgba(255,255,255,0.1); text-align:center; position:sticky; top:0; z-index:10; }
        .header h1 { font-size:1.7rem; font-weight:700; background:linear-gradient(120deg,#A78BFA,#EC4899); -webkit-background-clip:text; color:transparent; }
        .header .badge { font-size:0.7rem; background:#2D3748; display:inline-block; padding:4px 10px; border-radius:30px; margin-top:6px; color:#CBD5E0; }
        .stats-bar { display:flex; background:rgba(0,0,0,0.4); padding:8px 20px; gap:12px; border-bottom:1px solid rgba(255,255,255,0.05); overflow-x:auto; white-space:nowrap; }
        .stat { background:#2D3748; padding:4px 12px; border-radius:40px; font-size:0.75rem; }
        .messages-container { flex:1; overflow-y:auto; padding:16px; display:flex; flex-direction:column; gap:12px; scroll-behavior:smooth; -webkit-overflow-scrolling:touch; }
        .message { display:flex; gap:12px; background:rgba(30,41,59,0.7); border-radius:24px; padding:12px 16px; border:1px solid rgba(255,255,255,0.05); transition:0.2s; }
        .message:hover { background:rgba(51,65,85,0.8); transform:translateX(4px); }
        .avatar { width:44px; height:44px; border-radius:40px; display:flex; align-items:center; justify-content:center; font-weight:bold; color:white; flex-shrink:0; }
        .message-content { flex:1; }
        .message-header { display:flex; align-items:baseline; gap:8px; flex-wrap:wrap; margin-bottom:6px; }
        .username { font-weight:700; color:#C084FC; font-size:0.95rem; }
        .time { font-size:0.7rem; color:#94A3B8; }
        .reply-badge { font-size:0.7rem; background:#334155; padding:2px 8px; border-radius:20px; color:#CBD5E0; }
        .message-text { font-size:0.95rem; line-height:1.45; margin:6px 0; word-break:break-word; cursor:pointer; }
        .message-text:active { background:rgba(255,255,255,0.1); border-radius:12px; }
        .message-actions { margin-top:6px; }
        .reply-button { background:none; border:none; color:#94A3B8; font-size:0.75rem; padding:4px 8px; border-radius:30px; cursor:pointer; }
        .reply-button:hover { background:#475569; color:white; }
        .input-area { background:rgba(15,23,42,0.9); padding:12px 16px; border-top:1px solid rgba(255,255,255,0.1); }
        .reply-indicator { background:#334155; border-radius:30px; padding:6px 12px; margin-bottom:8px; font-size:0.8rem; display:flex; justify-content:space-between; align-items:center; }
        .cancel-reply { background:#EF4444; border:none; color:white; padding:2px 12px; border-radius:30px; cursor:pointer; font-size:0.7rem; }
        .input-row { display:flex; gap:10px; margin-bottom:8px; flex-wrap:wrap; }
        .input-row input { flex:1 1 auto; background:#0F172A; border:1px solid #334155; padding:12px 16px; border-radius:40px; color:#F1F5F9; font-size:0.9rem; outline:none; min-width:100px; }
        .input-row input:focus { border-color:#A78BFA; box-shadow:0 0 0 2px rgba(167,139,250,0.3); }
        .send-button { background:linear-gradient(95deg,#7C3AED,#EC4899); border:none; border-radius:40px; padding:0 24px; font-weight:bold; color:white; cursor:pointer; white-space:nowrap; }
        .send-button:disabled { opacity:0.6; cursor:not-allowed; }
        .menu-buttons { display:flex; gap:12px; justify-content:center; margin-top:6px; flex-wrap:wrap; }
        .menu-buttons a, .menu-buttons button { background:rgba(51,65,85,0.6); padding:6px 14px; border-radius:40px; font-size:0.7rem; color:#CBD5E0; text-decoration:none; border:none; cursor:pointer; white-space:nowrap; }
        .toast { position:fixed; bottom:80px; left:50%; transform:translateX(-50%); background:#2D3748; color:white; padding:8px 16px; border-radius:40px; font-size:0.8rem; opacity:0; transition:0.3s; z-index:1000; }
        @media (max-width:600px) {
            .header h1 { font-size:1.3rem; }
            .avatar { width:36px; height:36px; font-size:0.8rem; }
            .message { padding:10px 12px; gap:8px; }
            .input-row { flex-direction:column; }
            .input-row input, .send-button { width:100%; flex:none; }
            .send-button { padding:12px; text-align:center; }
        }
    </style>
</head>
<body>
<div class="app">
    <div class="header">
        <h1>💬 HIVE ChatRoom ''' + version_bytes + b'''</h1>
        <div class="badge">Stable · Memory optimized</div>
    </div>
    <div class="stats-bar">
        <div class="stat">🌡️ ''' + temp_str.encode() + b'''</div>
        <div class="stat">💧 ''' + hum_str.encode() + b'''</div>
        <div class="stat">⏱️ ''' + uptime.encode() + b'''</div>
        <div class="stat" id="msgCount">💬 ''' + str(msg_count).encode() + b'''</div>
    </div>
    <div class="messages-container" id="msgContainer">
        ''' + msg_html + b'''
    </div>
    <div class="input-area">
        <div id="replyIndicator" style="display:none;" class="reply-indicator">
            <span id="replyInfoText"></span>
            <button class="cancel-reply" onclick="clearReply()">Cancel</button>
        </div>
        <form id="msgForm">
            <div class="input-row">
                <input type="text" id="username" name="name" placeholder="Your name" maxlength="20" required>
                <input type="text" id="msg_input" name="msg" placeholder="Type your message..." required>
                <input type="hidden" id="reply_to" name="reply" value="0">
                <button class="send-button" type="submit" id="sendBtn">Send</button>
            </div>
        </form>
        <div class="menu-buttons">
            <button onclick="location.reload()">🔄 Refresh</button>
            <a href="/download_msgs" target="_blank">⬇️ Download msgs</a>
            <a href="/download_temps" target="_blank">🌡️ Download logs</a>
            <button onclick="toggleScroll()">📌 Auto-scroll</button>
        </div>
    </div>
</div>
<div id="toast" class="toast"></div>
<script>
    let currentReplyTo = 0;
    let currentReplyName = '';
    let scrollAuto = true;
    let lastKnownMsgCount = ''' + str(msg_count).encode() + b''';
    let sending = false;

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
        showToast('Copied!');
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
        setTimeout(() => toast.style.opacity = '0', 1500);
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

    function appendLocalMessage(username, text, replyTo, replyName) {
        const container = document.getElementById('msgContainer');
        const msgId = 'local_' + Date.now();
        const timestamp = Math.floor(Date.now() / 1000);

        let hash = 0;
        for (let i = 0; i < username.length; i++) hash = (hash * 31 + username.charCodeAt(i)) & 0xFFFFFFFF;
        const hue = Math.abs(hash) % 360;
        const avatarStyle = `background: hsl(${hue}, 70%, 55%);`;

        let replyBadge = '';
        if (replyTo != 0 && replyName) {
            replyBadge = `<span class="reply-badge">↩️ ${replyName}</span>`;
        }

        const div = document.createElement('div');
        div.className = 'message';
        div.dataset.id = msgId;
        div.dataset.username = username;
        div.dataset.time = timestamp;
        div.innerHTML = `
            <div class="avatar" style="${avatarStyle}">${username.substring(0,2).toUpperCase()}</div>
            <div class="message-content">
                <div class="message-header">
                    <span class="username">${username}</span>
                    <span class="time" data-timestamp="${timestamp}">${formatRelativeTime(timestamp)}</span>
                    ${replyBadge}
                </div>
                <div class="message-text" onclick="copyText(this)">${text}</div>
                <div class="message-actions">
                    <button class="reply-button" data-id="${msgId}" data-name="${username}">💬 Reply</button>
                </div>
            </div>
        `;
        div.querySelector('.reply-button').onclick = function(e) {
            e.stopPropagation();
            currentReplyTo = parseInt(this.dataset.id);
            currentReplyName = this.dataset.name;
            document.getElementById('reply_to').value = currentReplyTo;
            document.getElementById('replyIndicator').style.display = 'flex';
            document.getElementById('replyInfoText').innerText = 'Replying to ' + currentReplyName;
            document.getElementById('msg_input').focus();
        };
        container.appendChild(div);
        if (scrollAuto) container.scrollTop = container.scrollHeight;
    }

    document.getElementById('msgForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        if (sending) return;

        const username = document.getElementById('username').value.trim();
        const msg = document.getElementById('msg_input').value.trim();
        const reply = document.getElementById('reply_to').value;

        if (!username || !msg) return;

        sending = true;
        const sendBtn = document.getElementById('sendBtn');
        sendBtn.disabled = true;
        sendBtn.textContent = '⏳';

        localStorage.setItem('chat_username', username);

        const params = new URLSearchParams({ name: username, msg, reply, ajax: '1' });
        try {
            const res = await fetch('/send?' + params.toString());
            const data = await res.json();
            if (data.success) {
                appendLocalMessage(username, msg, parseInt(reply), currentReplyName);
                lastKnownMsgCount = data.total;
                document.getElementById('msgCount').innerText = '💬 ' + data.total;
                document.getElementById('msg_input').value = '';
                clearReply();
            } else {
                showToast('Error sending message');
            }
        } catch (err) {
            showToast('Network error - retry');
            console.error(err);
        } finally {
            sending = false;
            sendBtn.disabled = false;
            sendBtn.textContent = 'Send';
            document.getElementById('msg_input').focus();
        }
    });

    window.onload = function() {
        updateAllTimes();
        setInterval(updateAllTimes, 60000);
        const savedName = localStorage.getItem('chat_username');
        if (savedName) document.getElementById('username').value = savedName;

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

        setInterval(async () => {
            if (sending) return;
            try {
                const resp = await fetch('/api/msg_count');
                const newCount = parseInt(await resp.text());
                const typing = document.activeElement === document.getElementById('msg_input') ||
                               document.activeElement === document.getElementById('username');
                if (newCount > lastKnownMsgCount && !typing) {
                    location.reload();
                } else {
                    lastKnownMsgCount = newCount;
                }
            } catch(e) {}
        }, 3000);
    };
</script>
</body>
</html>'''
    gc.collect()  # پاکسازی مجدد
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

# ========== راه‌اندازی UART و ESP01s ==========
print("System starting")
load_messages()
if len(messages) == 0:
    add_message("System", f"Welcome to HIVE {VERSION}! 🚀", 0)

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
        system_error("WiFi connection failed! Server offline.")
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
                        msg_id = add_message(name, msg, reply)
                    else:
                        msg_id = None

                    if is_ajax and msg_id is not None:
                        json_str = '{"success":true,"id":%d,"total":%d}' % (msg_id, len(messages))
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
                print(f"Handler error: {e}")
                system_error(f"Request handling error: {e}")
                gc.collect()
            finally:
                if conn_id is not None:
                    try:
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        time.sleep(0.05)
                    except:
                        pass

    time.sleep(0.05)
    gc.collect()  # جمع‌آوری منظم زباله در بیکاری