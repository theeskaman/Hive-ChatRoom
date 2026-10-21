import machine
import time
import os
import gc
import dht
import json
import sys
import ubinascii

# ============================== تنظیمات اصلی ==============================
SSID = "Mehrbod"
PASSWORD = "357913802"
PORT = 80
MAX_MSGS = 5000
ADMIN_PASS = "nigga"
DHT_PIN = 0
MAX_MSG_CHARS = 400
VERSION = "1.9.2 Alpha"

messages = []
next_id = 1
TEMP_LOG_FILE = "temp_log.txt"
TEMP_LOG_INTERVAL_MS = 60000
PINNED_FILE = "pinned.txt"
pinned_msg_id = 0
pinned_msg_data = None
reactions = {}
CONFIG_FILE = "config.txt"
USERS_FILE = "users.txt"
MUTED_FILE = "muted.txt"

config = {"temp_log": True, "chat_log": True, "maintenance": False}

last_dht_read = 0
last_dht_temp = None
last_dht_hum = None
dht_error_printed = False
system_error_logged = {}
cached_network_info = "Not connected"

try:
    wdt = machine.WDT(timeout=300000)
    print("Watchdog activated (5 min)")
except:
    wdt = None

# ============================== توابع کمکی ==============================
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

# ============================== مدیریت تنظیمات ==============================
def load_config():
    global config
    try:
        with open(CONFIG_FILE, "r") as f:
            for line in f:
                line = line.strip()
                if '=' in line:
                    k, v = line.split('=', 1)
                    if k in config:
                        config[k] = v.lower() in ('true', '1', 'yes')
    except:
        save_config()

def save_config():
    with open(CONFIG_FILE, "w") as f:
        f.write(f"temp_log={config['temp_log']}\n")
        f.write(f"chat_log={config['chat_log']}\n")
        f.write(f"maintenance={config['maintenance']}\n")

def is_maintenance_mode():
    return config.get("maintenance", False)

# ============================== کاربران (متن ساده) ==============================
def init_users():
    try:
        with open(USERS_FILE, "r") as f:
            if f.read().strip():
                return
    except:
        pass
    with open(USERS_FILE, "w") as f:
        f.write("admin:nigga:admin\n")
        f.write("test:test123:user\n")
    print("Default users created: admin/nigga , test/test123")

def register_user(username, password):
    username = sanitize_string(username)[:20]
    if not username or len(username) < 2:
        return False, "Invalid username (min 2 chars)"
    if len(password) < 4:
        return False, "Password too short (min 4 chars)"
    try:
        with open(USERS_FILE, "r") as f:
            for line in f:
                if line.startswith(username + ":"):
                    return False, "Username already exists"
    except:
        pass
    with open(USERS_FILE, "a") as f:
        f.write(f"{username}:{password}:user\n")
    return True, "Registered successfully"

def login_user(username, password):
    try:
        with open(USERS_FILE, "r") as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) == 3 and parts[0] == username and parts[1] == password:
                    return True, parts[2]
    except:
        pass
    return False, None

def get_user_role(username):
    try:
        with open(USERS_FILE, "r") as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) == 3 and parts[0] == username:
                    return parts[2]
    except:
        pass
    return "user"

def is_muted(username):
    try:
        with open(MUTED_FILE, "r") as f:
            for line in f:
                if line.strip() == username:
                    return True
    except:
        pass
    return False

def mute_user(admin_user, target):
    if get_user_role(admin_user) != "admin":
        return False, "Not admin"
    with open(MUTED_FILE, "a") as f:
        f.write(target + "\n")
    return True, f"Muted {target}"

def unmute_user(admin_user, target):
    if get_user_role(admin_user) != "admin":
        return False, "Not admin"
    try:
        lines = []
        with open(MUTED_FILE, "r") as f:
            lines = f.readlines()
        with open(MUTED_FILE, "w") as f:
            for l in lines:
                if l.strip() != target:
                    f.write(l)
        return True, f"Unmuted {target}"
    except:
        return False, "Error"

# ============================== ری‌اکشن ==============================
def load_reactions():
    global reactions
    reactions.clear()
    try:
        with open("reactions.txt", "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split('|')
                if len(parts) == 3:
                    msg_id = int(parts[0])
                    emoji = parts[1]
                    username = parts[2]
                    if msg_id not in reactions:
                        reactions[msg_id] = {}
                    if emoji not in reactions[msg_id]:
                        reactions[msg_id][emoji] = set()
                    reactions[msg_id][emoji].add(username)
    except:
        pass

def save_reaction(msg_id, emoji, username):
    changed = False
    msg_id = int(msg_id)
    if msg_id in reactions and emoji in reactions[msg_id] and username in reactions[msg_id][emoji]:
        reactions[msg_id][emoji].remove(username)
        if not reactions[msg_id][emoji]:
            del reactions[msg_id][emoji]
        changed = True
    else:
        if msg_id not in reactions:
            reactions[msg_id] = {}
        if emoji not in reactions[msg_id]:
            reactions[msg_id][emoji] = set()
        reactions[msg_id][emoji].add(username)
        changed = True
    if changed:
        with open("reactions.txt", "w") as f:
            for mid, emojis in reactions.items():
                for em, users in emojis.items():
                    for u in users:
                        f.write(f"{mid}|{em}|{u}\n")
    return changed

def get_reactions_for_msg(msg_id):
    if msg_id in reactions:
        return {emoji: list(users) for emoji, users in reactions[msg_id].items()}
    return {}

# ============================== پیام پین شده ==============================
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

# ============================== پیام‌ها ==============================
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
                if len(parts) >= 6:
                    try:
                        mid = int(parts[0])
                        if mid > max_id:
                            max_id = mid
                        messages.append(line)
                    except:
                        pass
        next_id = max_id + 1
        print(f"Loaded {len(messages)} messages, next_id={next_id}")
    except:
        messages = []
        next_id = 1
    load_pinned()
    load_reactions()

def save_messages():
    if not config["chat_log"]:
        return
    try:
        to_save = messages[-MAX_MSGS:] if len(messages) > MAX_MSGS else messages
        with open("messages.txt", "wb") as f:
            for msg in to_save:
                f.write(msg + b'\n')
        print(f"Saved {len(to_save)} messages")
    except Exception as e:
        system_error(f"Save messages failed: {e}")

def add_message(username, text, reply_to=0):
    global messages, next_id
    if not text or len(text.strip()) == 0:
        return None
    if is_muted(username):
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

def get_message_by_id(mid):
    for m in messages:
        parts = m.split(b'|')
        if len(parts) >= 5 and int(parts[0]) == mid:
            return parts[2].decode('utf-8', 'replace')
    return None

# ============================== سنسورها و لاگ دما ==============================
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
    if not config["temp_log"]:
        return
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

# ============================== دستورات ادمین ==============================
def handle_admin_command(username, text):
    global config, next_id
    role = get_user_role(username)
    if role != "admin":
        return False, None
    if not text.startswith("admin:"):
        return False, None
    parts = text[6:].strip().split()
    if not parts:
        return True, ("System", "Commands: info, toggletemp, togglechatlog, maintenance on/off, mute <user>, unmute <user>, pin <id>, unpin, restart, clearlogs, clear")
    cmd = parts[0].lower()
    args = parts[1:]
    
    if cmd == "info":
        temp, hum, uptime, cnt = get_system_stats()
        free = gc.mem_free()
        return True, ("System", f"Temp:{temp} Hum:{hum} Up:{uptime} Msgs:{cnt} FreeMem:{free}")
    if cmd == "toggletemp":
        config["temp_log"] = not config["temp_log"]
        save_config()
        state = "enabled" if config["temp_log"] else "disabled"
        return True, ("System", f"Temperature logging {state}")
    if cmd == "togglechatlog":
        config["chat_log"] = not config["chat_log"]
        save_config()
        state = "enabled" if config["chat_log"] else "disabled"
        return True, ("System", f"Chat persistence {state}")
    if cmd == "maintenance" and len(args) >= 1:
        if args[0] == "on":
            config["maintenance"] = True
            save_config()
            return True, ("System", "Maintenance mode ENABLED")
        elif args[0] == "off":
            config["maintenance"] = False
            save_config()
            return True, ("System", "Maintenance mode DISABLED")
    if cmd == "mute" and len(args) >= 1:
        ok, msg = mute_user(username, args[0])
        return True, ("System", msg)
    if cmd == "unmute" and len(args) >= 1:
        ok, msg = unmute_user(username, args[0])
        return True, ("System", msg)
    if cmd == "pin" and len(args) >= 1:
        try:
            pin_id = int(args[0])
            found = any(int(m.split(b'|')[0]) == pin_id for m in messages)
            if not found:
                return True, ("System", f"Msg {pin_id} not found")
            save_pinned(pin_id)
            return True, ("System", f"Pinned {pin_id}")
        except:
            return True, ("System", "Invalid ID")
    if cmd == "unpin":
        save_pinned(0)
        return True, ("System", "Unpinned")
    if cmd == "clearlogs":
        try:
            os.remove(TEMP_LOG_FILE)
            return True, ("System", "Logs cleared")
        except:
            return True, ("System", "No log")
    if cmd == "clear":
        try:
            os.remove("messages.txt")
        except:
            pass
        messages.clear()
        next_id = 1
        add_message("System", "Chat cleared")
        return True, None
    if cmd == "restart":
        add_message("System", "Restarting...")
        time.sleep(2)
        machine.reset()
    return True, ("System", f"Unknown: {cmd}")

# ============================== توابع مدیریت فایل ==============================
def handle_list_files():
    try:
        files = []
        for item in os.listdir():
            try:
                size = os.stat(item)[6]
                files.append({"name": item, "size": size})
            except:
                files.append({"name": item, "size": 0})
        return json.dumps({"success": True, "files": files}).encode()
    except Exception as e:
        return json.dumps({"success": False, "message": str(e)}).encode()

def handle_delete_file(params):
    try:
        password = params.get('password', '')
        if password != ADMIN_PASS:
            return json.dumps({"success": False, "message": "Invalid password"}).encode()
        filename = params.get('filename', '')
        if not filename:
            return json.dumps({"success": False, "message": "No filename"}).encode()
        protected = ['main.py', 'boot.py', 'messages.txt', 'temp_log.txt', 'users.txt', 'reactions.txt', 'config.txt', 'update.html', 'maintenance.html', 'chat.html', 'pinned.txt']
        if filename in protected:
            return json.dumps({"success": False, "message": "Cannot delete system file"}).encode()
        if filename in os.listdir():
            os.remove(filename)
            return json.dumps({"success": True, "message": "Deleted"}).encode()
        else:
            return json.dumps({"success": False, "message": "File not found"}).encode()
    except Exception as e:
        return json.dumps({"success": False, "message": str(e)}).encode()

def handle_update_file(params):
    try:
        password = params.get('password', '')
        if password != ADMIN_PASS:
            return json.dumps({"success": False, "message": "Invalid password"}).encode()
        filename = params.get('filename', '')
        if not filename.endswith('.html'):
            return json.dumps({"success": False, "message": "Only .html files"}).encode()
        b64 = params.get('content_base64', '')
        if not b64:
            return json.dumps({"success": False, "message": "No content"}).encode()
        content = ubinascii.a2b_base64(b64)
        try:
            with open(filename, 'rb') as f:
                old = f.read()
            with open(filename + '.bak', 'wb') as f:
                f.write(old)
        except:
            pass
        with open(filename, 'wb') as f:
            f.write(content)
        return json.dumps({"success": True, "message": "Updated"}).encode()
    except Exception as e:
        return json.dumps({"success": False, "message": str(e)}).encode()

# ============================== توابع فایل HTML ==============================
def read_file_content(filename, default=b''):
    try:
        with open(filename, 'rb') as f:
            return f.read()
    except:
        return default

def serve_file(conn_id, filename, content_type="text/html", default_binary=b''):
    content = read_file_content(filename, default_binary)
    headers = f"HTTP/1.1 200 OK\r\nContent-Type: {content_type}; charset=utf-8\r\nContent-Length: {len(content)}\r\nConnection: close\r\n\r\n".encode()
    full_resp = headers + content
    send_large_response(conn_id, full_resp)

# ============================== ارتباط با ESP ==============================
uart = None
try:
    uart = machine.UART(1, 115200, tx=machine.Pin(4), rx=machine.Pin(5))
    print("UART1 initialized (TX=GP4, RX=GP5)")
except Exception as e:
    system_error("UART init error", e)

def send_cmd(cmd_bytes, expected_bytes, timeout_ms=5000):
    if uart is None: return False
    while uart.any(): uart.read()
    uart.write(cmd_bytes + b'\r\n')
    start = time.ticks_ms()
    while time.ticks_ms() - start < timeout_ms:
        if uart.any():
            line = uart.readline()
            if line and expected_bytes in line:
                return True
    return False

def wait_for_prompt(timeout_ms=2000):
    if uart is None: return False
    start = time.ticks_ms()
    while time.ticks_ms() - start < timeout_ms:
        if uart.any():
            if uart.read(1) == b'>':
                return True
    return False

def send_small_response(conn_id, data):
    if uart is None: return False
    uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(data)).encode() + b'\r\n')
    if not wait_for_prompt(2000): return False
    uart.write(data)
    time.sleep(0.05)
    start = time.ticks_ms()
    while time.ticks_ms() - start < 2000:
        if uart.any():
            if b'OK' in uart.readline():
                return True
    return False

def send_large_response(conn_id, data):
    if uart is None: return False
    chunk_size = 1400
    offset = 0
    while offset < len(data):
        chunk = data[offset:offset+chunk_size]
        uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(chunk)).encode() + b'\r\n')
        if not wait_for_prompt(2000): return False
        uart.write(chunk)
        time.sleep(0.05)
        start = time.ticks_ms()
        ok = False
        while time.ticks_ms() - start < 2000:
            if uart.any() and b'OK' in uart.readline():
                ok = True
                break
        if not ok: return False
        offset += chunk_size
    return True

def init_wifi():
    global cached_network_info
    if uart is None: return False
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
    ip = "N/A"; mac = "N/A"
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

# ============================== حلقه اصلی سرور ==============================
def run():
    load_config()
    init_users()
    load_messages()
    if len(messages) == 0:
        add_message("System", f"Welcome to HIVE {VERSION}! 🚀", 0)
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

                    # حالت تعمیرات
                    if is_maintenance_mode() and path not in [b'/api/stats', b'/update', b'/api/login', b'/api/register', b'/maintenance.html', b'/api/list_files', b'/api/delete_file', b'/api/update', b'/api/get_reactions', b'/api/reaction', b'/api/admin'] and not (method == b'GET' and path == b'/'):
                        err_resp = b'HTTP/1.1 503 Service Unavailable\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n<html><body><h1>Maintenance Mode</h1></body></html>'
                        send_small_response(conn_id, err_resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # ========== STATS ==========
                    if method == b'GET' and path == b'/api/stats':
                        stats = get_system_stats()
                        stats_dict = {
                            "temp": stats[0],
                            "hum": stats[1],
                            "uptime": stats[2],
                            "msg_count": stats[3],
                            "free_mem": gc.mem_free(),
                            "network": cached_network_info,
                            "maintenance": config["maintenance"],
                            "version": VERSION
                        }
                        resp_body = json.dumps(stats_dict).encode()
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp_body)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # ========== GET /api/get_reactions ==========
                    if method == b'GET' and path == b'/api/get_reactions':
                        params = {}
                        if query:
                            for pair in query.split(b'&'):
                                if b'=' in pair:
                                    k, v = pair.split(b'=', 1)
                                    params[k.decode()] = v.decode()
                        msg_id = int(params.get('msg_id', 0))
                        if msg_id == 0:
                            resp = json.dumps({"success": False, "message": "No msg_id"}).encode()
                        else:
                            msg_reactions = get_reactions_for_msg(msg_id)
                            resp = json.dumps({"success": True, "reactions": msg_reactions}).encode()
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # ========== LOGIN ==========
                    if method == b'GET' and path == b'/api/login':
                        params = {}
                        if query:
                            for pair in query.split(b'&'):
                                if b'=' in pair:
                                    k, v = pair.split(b'=', 1)
                                    key = k.decode()
                                    val = percent_decode(v).decode('utf-8', 'ignore')
                                    params[key] = val
                        username = params.get('username', '').strip()
                        password = params.get('password', '').strip()
                        ok, role = login_user(username, password)
                        if ok:
                            resp = json.dumps({"success": True, "username": username, "role": role}).encode()
                        else:
                            resp = json.dumps({"success": False, "message": "Invalid credentials"}).encode()
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # ========== REGISTER ==========
                    if method == b'GET' and path == b'/api/register':
                        params = {}
                        if query:
                            for pair in query.split(b'&'):
                                if b'=' in pair:
                                    k, v = pair.split(b'=', 1)
                                    key = k.decode()
                                    val = percent_decode(v).decode('utf-8', 'ignore')
                                    params[key] = val
                        username = params.get('username', '').strip()
                        password = params.get('password', '').strip()
                        if not username or not password:
                            resp = json.dumps({"success": False, "message": "Username and password required"}).encode()
                        else:
                            ok, msg = register_user(username, password)
                            resp = json.dumps({"success": ok, "message": msg}).encode()
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # ========== REACTION (with direct reactions return) ==========
                    if method == b'GET' and path == b'/api/reaction':
                        params = {}
                        if query:
                            for pair in query.split(b'&'):
                                if b'=' in pair:
                                    k, v = pair.split(b'=', 1)
                                    key = k.decode()
                                    val = percent_decode(v).decode('utf-8', 'ignore')
                                    params[key] = val
                        username = params.get('username', '').strip()
                        password = params.get('password', '').strip()
                        msg_id = int(params.get('msg_id', 0))
                        emoji = params.get('emoji', '')
                        ok, _ = login_user(username, password)
                        if not ok:
                            resp = json.dumps({"success": False, "message": "Auth failed"}).encode()
                        else:
                            save_reaction(msg_id, emoji, username)
                            # Return updated reactions for this message
                            updated_reactions = get_reactions_for_msg(msg_id)
                            resp = json.dumps({"success": True, "reactions": updated_reactions}).encode()
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # ========== ADMIN API ==========
                    if method == b'GET' and path == b'/api/admin':
                        params = {}
                        if query:
                            for pair in query.split(b'&'):
                                if b'=' in pair:
                                    k, v = pair.split(b'=', 1)
                                    key = k.decode()
                                    val = percent_decode(v).decode('utf-8', 'ignore')
                                    params[key] = val
                        username = params.get('username', '').strip()
                        password = params.get('password', '').strip()
                        cmd = params.get('cmd', '')
                        ok, role = login_user(username, password)
                        if not ok or role != "admin":
                            resp = json.dumps({"success": False, "message": "Admin only"}).encode()
                        else:
                            if cmd == "maintenance off":
                                config["maintenance"] = False
                                save_config()
                                resp = json.dumps({"success": True, "message": "Maintenance OFF"}).encode()
                            elif cmd == "maintenance on":
                                config["maintenance"] = True
                                save_config()
                                resp = json.dumps({"success": True, "message": "Maintenance ON"}).encode()
                            else:
                                resp = json.dumps({"success": False, "message": "Unknown command"}).encode()
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # ========== LIST FILES ==========
                    if method == b'GET' and path == b'/api/list_files':
                        resp = handle_list_files()
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # ========== DELETE FILE ==========
                    if method == b'GET' and path == b'/api/delete_file':
                        params = {}
                        if query:
                            for pair in query.split(b'&'):
                                if b'=' in pair:
                                    k, v = pair.split(b'=', 1)
                                    key = k.decode()
                                    val = percent_decode(v).decode('utf-8', 'ignore')
                                    params[key] = val
                        resp = handle_delete_file(params)
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # ========== UPDATE FILE ==========
                    if method == b'GET' and path == b'/api/update':
                        params = {}
                        if query:
                            for pair in query.split(b'&'):
                                if b'=' in pair:
                                    k, v = pair.split(b'=', 1)
                                    key = k.decode()
                                    val = percent_decode(v).decode('utf-8', 'ignore')
                                    params[key] = val
                        resp = handle_update_file(params)
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # ========== POLL MESSAGES (با pinned) ==========
                    if method == b'GET' and path == b'/api/msg_poll':
                        params = {}
                        if query:
                            for pair in query.split(b'&'):
                                if b'=' in pair:
                                    k, v = pair.split(b'=', 1)
                                    params[k.decode()] = v.decode()
                        since_id = int(params.get('since', '0'))
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
                            reply_user = get_message_by_id(reply) if reply != 0 else ""
                            msg_reactions = get_reactions_for_msg(mid)
                            new_msgs.append({
                                "id": mid,
                                "time": time_str,
                                "user": user,
                                "text": text,
                                "reply": reply,
                                "reply_user": reply_user,
                                "timestamp": timestamp,
                                "reactions": msg_reactions
                            })
                        pinned = get_pinned_message()
                        response_obj = {"total": len(messages), "messages": new_msgs, "pinned": pinned}
                        resp_body = json.dumps(response_obj).encode()
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp_body)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # ========== SEND MESSAGE ==========
                    if method == b'GET' and path == b'/send':
                        params = {}
                        if query:
                            for pair in query.split(b'&'):
                                if b'=' in pair:
                                    k, v = pair.split(b'=', 1)
                                    key = k.decode()
                                    val = percent_decode(v).decode('utf-8', 'ignore')
                                    params[key] = val
                        username = params.get('username', '')
                        password = params.get('password', '')
                        ok, _ = login_user(username, password)
                        if not ok:
                            err_resp = b'HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{"success":false,"message":"Auth failed"}'
                            send_small_response(conn_id, err_resp)
                            uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                            conn_id = None
                            gc.collect()
                            continue
                        if is_muted(username):
                            err_resp = b'HTTP/1.1 403 Forbidden\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{"success":false,"message":"You are muted"}'
                            send_small_response(conn_id, err_resp)
                            uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                            conn_id = None
                            gc.collect()
                            continue
                        msg = params.get('msg', '')
                        reply = int(params.get('reply', '0'))
                        if msg.startswith("admin:"):
                            handled, response_tuple = handle_admin_command(username, msg)
                            if handled and response_tuple:
                                add_message(response_tuple[0], response_tuple[1])
                            json_resp = json.dumps({"success": True, "id": 0, "total": len(messages)}).encode()
                            headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(json_resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                            send_small_response(conn_id, headers + json_resp)
                            uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                            conn_id = None
                            gc.collect()
                            continue
                        if msg:
                            msg_id, msg_time = add_message(username, msg, reply)
                            json_resp = json.dumps({"success": True, "id": msg_id, "time": msg_time, "total": len(messages)}).encode()
                        else:
                            json_resp = json.dumps({"success": False, "message": "Empty message"}).encode()
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(json_resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + json_resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # ========== صفحات HTML ==========
                    if method == b'GET' and path == b'/':
                        if is_maintenance_mode():
                            serve_file(conn_id, "maintenance.html", default_binary=b"<html><body><h1>Maintenance</h1></body></html>")
                        else:
                            serve_file(conn_id, "chat.html", default_binary=b"<html><body><h1>chat.html missing</h1></body></html>")
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'GET' and path == b'/update':
                        serve_file(conn_id, "update.html", default_binary=b"<html><body><h1>update.html missing</h1></body></html>")
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'GET' and path == b'/download_msgs':
                        content = read_file_content("messages.txt", b"")
                        resp = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename="messages.txt"\r\nContent-Length: ' + str(len(content)).encode() + b'\r\nConnection: close\r\n\r\n' + content
                        send_large_response(conn_id, resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'GET' and path == b'/download_temps':
                        content = read_file_content(TEMP_LOG_FILE, b"")
                        resp = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename="temp_log.txt"\r\nContent-Length: ' + str(len(content)).encode() + b'\r\nConnection: close\r\n\r\n' + content
                        send_large_response(conn_id, resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    else:
                        resp404 = b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, resp404)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                except Exception as e:
                    system_error("Request handler", e)
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