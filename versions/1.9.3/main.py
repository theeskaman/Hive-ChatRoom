import machine
import time
import os
import gc
import dht
import json
import sys
import ubinascii
try:
    import uhashlib as hashlib
except ImportError:
    import hashlib

SSID = "YOUR_WIFI_SSID"
PASSWORD = "YOUR_WIFI_PASSWORD"
PORT = 80
MAX_MSGS = 5000
ADMIN_PASS = "CHANGE_ME_TO_A_LONG_UNIQUE_PASSWORD"
DHT_PIN = 0
MAX_MSG_CHARS = 400
VERSION = "1.9.3 Stable"

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
NEWS_FILE = "news.txt"

config = {"temp_log": True, "chat_log": True, "maintenance": False}

last_dht_read = 0
last_dht_temp = None
last_dht_hum = None
dht_error_printed = False
system_error_logged = {}
cached_network_info = "Not connected"
last_wifi_check = 0
loop_counter = 0

try:
    wdt = machine.WDT(timeout=300000)
    print("Watchdog activated")
except:
    wdt = None

def sanitize_string(s):
    s = s.replace('|', '¦').replace('\r', ' ').replace('\n', ' ')
    s = ''.join(ch for ch in s if ord(ch) >= 32 or ch == '\t')
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



# ===== Password hashing and short-lived, in-memory sessions =====
PASSWORD_ROUNDS = 10000
PASSWORD_PREFIX = "pbkdf2-sha256"
SESSION_TTL_MS = 6 * 60 * 60 * 1000
sessions = {}
session_counter = 0

def _sha256(data):
    return hashlib.sha256(data).digest()

def _hmac_sha256(key, message):
    if len(key) > 64:
        key = _sha256(key)
    key = key + (b'\x00' * (64 - len(key)))
    inner_key = bytes([value ^ 0x36 for value in key])
    outer_key = bytes([value ^ 0x5c for value in key])
    return _sha256(outer_key + _sha256(inner_key + message))

def _pbkdf2_sha256(password, salt, rounds=PASSWORD_ROUNDS):
    password_bytes = password.encode('utf-8')
    block = _hmac_sha256(password_bytes, salt + b'\x00\x00\x00\x01')
    derived = bytearray(block)
    for _ in range(1, rounds):
        block = _hmac_sha256(password_bytes, block)
        for index in range(len(derived)):
            derived[index] ^= block[index]
    return bytes(derived)

def _new_salt(username):
    try:
        return os.urandom(16)
    except:
        seed = machine.unique_id() + str(time.ticks_ms()).encode() + username.encode('utf-8')
        return _sha256(seed)[:16]

def _make_password_hash(password, username):
    salt = _new_salt(username)
    salt_hex = ubinascii.hexlify(salt).decode('ascii')
    digest_hex = ubinascii.hexlify(_pbkdf2_sha256(password, salt, PASSWORD_ROUNDS)).decode('ascii')
    return PASSWORD_PREFIX + "$" + str(PASSWORD_ROUNDS) + "$" + salt_hex + "$" + digest_hex

def _constant_time_equal(left, right):
    if len(left) != len(right):
        return False
    difference = 0
    for index in range(len(left)):
        difference |= left[index] ^ right[index]
    return difference == 0

def _password_matches(stored, candidate):
    if not stored.startswith(PASSWORD_PREFIX + "$"):
        return stored == candidate
    try:
        parts = stored.split('$')
        if len(parts) != 4:
            return False
        rounds = int(parts[1])
        if rounds < 1000 or rounds > 50000:
            return False
        salt = ubinascii.unhexlify(parts[2].encode('ascii'))
        expected = ubinascii.unhexlify(parts[3].encode('ascii'))
        actual = _pbkdf2_sha256(candidate, salt, rounds)
        return _constant_time_equal(actual, expected)
    except:
        return False

def create_session(username, role):
    global session_counter
    session_counter += 1
    try:
        seed = os.urandom(24)
    except:
        seed = machine.unique_id() + str(time.ticks_ms()).encode() + str(session_counter).encode() + username.encode('utf-8')
    token = ubinascii.hexlify(_sha256(seed)[:16]).decode('ascii')
    if len(sessions) >= 8:
        oldest_token = None
        oldest_age = -1
        now = time.ticks_ms()
        for existing_token, entry in sessions.items():
            age = time.ticks_diff(now, entry[2])
            if age > oldest_age:
                oldest_age = age
                oldest_token = existing_token
        if oldest_token is not None:
            del sessions[oldest_token]
    sessions[token] = (username, role, time.ticks_ms())
    return token

def get_session(token):
    if not token:
        return None
    entry = sessions.get(token)
    if not entry:
        return None
    now = time.ticks_ms()
    if time.ticks_diff(now, entry[2]) > SESSION_TTL_MS:
        try:
            del sessions[token]
        except:
            pass
        return None
    sessions[token] = (entry[0], entry[1], now)
    return (entry[0], entry[1])

def parse_request_params(req, query, method):
    if method == b'POST':
        try:
            separator = req.find(b'\r\n\r\n')
            if separator < 0:
                return {}
            body = req[separator + 4:].strip()
            if not body:
                return {}
            parsed = json.loads(body.decode('utf-8'))
            return parsed if isinstance(parsed, dict) else {}
        except:
            return {}
    params = {}
    if query:
        for pair in query.split(b'&'):
            if b'=' in pair:
                key, value = pair.split(b'=', 1)
                params[key.decode('utf-8', 'ignore')] = percent_decode(value).decode('utf-8', 'ignore')
    return params

def has_admin_session(token):
    session = get_session(token)
    return bool(session and session[1] == "admin")

def safe_system_error(err_msg, exc=None):
    global system_error_logged
    now = time.time()
    t = time.localtime()
    ts = f"{t[3]:02d}:{t[4]:02d}:{t[5]:02d}"
    if exc:
        sys.print_exception(exc)
        print(f"[ERROR] {ts}: {err_msg} | {exc}")
    else:
        print(f"[ERROR] {ts}: {err_msg}")
    key = err_msg[:50]
    if key in system_error_logged and now - system_error_logged.get(key, 0) < 30:
        return
    system_error_logged[key] = now
    if len(system_error_logged) > 100:
        oldest = min(system_error_logged.values())
        for k, v in list(system_error_logged.items()):
            if v == oldest:
                del system_error_logged[k]
                break

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

def get_news():
    try:
        with open(NEWS_FILE, "r") as f:
            content = f.read().strip()
            if len(content) > 500:
                content = content[:500] + "..."
            return content
    except:
        default = "📢 Welcome to HIVE 1.9.3!\n- Persian support\n- News panel\n- Stable"
        try:
            with open(NEWS_FILE, "w") as f:
                f.write(default)
        except:
            pass
        return default

def init_users():
    try:
        with open(USERS_FILE, "r") as f:
            existing_lines = f.readlines()
        if any(line.strip() for line in existing_lines):
            migrated = []
            changed = False
            for raw_line in existing_lines:
                line = raw_line.rstrip("\r\n")
                parts = line.split(':')
                if len(parts) != 3 or not parts[0] or parts[2] not in ("admin", "user"):
                    changed = True
                    continue
                # Remove known weak demo credentials instead of merely hashing them.
                if parts[0] == "test":
                    changed = True
                    continue
                if not parts[1].startswith(PASSWORD_PREFIX + "$"):
                    if len(parts[1]) < 12:
                        changed = True
                        continue
                    parts[1] = _make_password_hash(parts[1], parts[0])
                    changed = True
                migrated.append(":".join(parts))
            has_admin = any(len(item.split(':')) == 3 and item.split(':')[2] == "admin" for item in migrated)
            if not has_admin and ADMIN_PASS != "CHANGE_ME_TO_A_LONG_UNIQUE_PASSWORD" and len(ADMIN_PASS) >= 12:
                migrated.append("admin:" + _make_password_hash(ADMIN_PASS, "admin") + ":admin")
                changed = True
                has_admin = True
            if changed:
                with open(USERS_FILE, "w") as f:
                    for line in migrated:
                        f.write(line + "\n")
            if not has_admin:
                print("WARNING: no admin account exists; configure a unique ADMIN_PASS of at least 12 characters.")
            return
    except:
        pass
    with open(USERS_FILE, "w") as f:
        if ADMIN_PASS != "CHANGE_ME_TO_A_LONG_UNIQUE_PASSWORD" and len(ADMIN_PASS) >= 12:
            f.write("admin:" + _make_password_hash(ADMIN_PASS, "admin") + ":admin\n")
            print("Initial admin account created.")
        else:
            print("WARNING: configure a unique ADMIN_PASS of at least 12 characters before first boot.")
            print("No default admin or test account was created.")

def register_user(username, password):
    if not isinstance(username, str) or not isinstance(password, str):
        return False, "Invalid input"
    username = sanitize_string(username)[:20]
    if not username or len(username) < 2 or ':' in username:
        return False, "Invalid username"
    if len(password) < 12:
        return False, "Password must be at least 12 characters"
    if len(password) > 64:
        return False, "Password is too long"
    try:
        with open(USERS_FILE, "r") as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) == 3 and parts[0] == username:
                    return False, "Username exists"
    except:
        pass
    with open(USERS_FILE, "a") as f:
        f.write(username + ":" + _make_password_hash(password, username) + ":user\n")
    return True, "Registered"

def login_user(username, password):
    if not isinstance(username, str) or not isinstance(password, str):
        return False, None
    try:
        with open(USERS_FILE, "r") as f:
            for line in f:
                parts = line.strip().split(':')
                if len(parts) == 3 and parts[0] == username and _password_matches(parts[1], password):
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

def cleanup_reactions(active_ids_set):
    global reactions
    to_delete = [mid for mid in reactions if mid not in active_ids_set]
    if to_delete:
        for mid in to_delete:
            del reactions[mid]
        with open("reactions.txt", "w") as f:
            for mid, emojis in reactions.items():
                for em, users in emojis.items():
                    for u in users:
                        f.write(f"{mid}|{em}|{u}\n")

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

def load_messages():
    global messages, next_id
    messages = []
    max_id = 0
    try:
        with open("messages.txt", "rb") as f:
            for line in f:
                line = line.rstrip(b'\n')
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
        print(f"Loaded {len(messages)} messages")
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
        safe_system_error("Save messages failed", e)

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
    line = b"%d|%s|%s|%s|%d|%d" % (msg_id, time_str.encode(), username_sanitized.encode('utf-8'), text_sanitized.encode('utf-8'), reply_to, timestamp_unix)
    messages.append(line)
    if len(messages) > MAX_MSGS:
        removed = messages.pop(0)
        removed_id = int(removed.split(b'|')[0])
        if removed_id == pinned_msg_id:
            save_pinned(0)
    save_messages()
    print(f"Message added: id={msg_id}")
    return msg_id, time_str

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
            safe_system_error("DHT11 error", e)
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
        safe_system_error("Temp log failed", e)

def get_system_stats():
    dht_temp, dht_hum = read_dht11()
    temp_str = f"{dht_temp}°C" if dht_temp is not None else "N/A"
    hum_str = f"{dht_hum}%" if dht_hum is not None else "N/A"
    uptime_sec = time.ticks_ms() // 1000
    uptime = f"{uptime_sec//3600}h {(uptime_sec%3600)//60}m"
    return temp_str, hum_str, uptime, len(messages)

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
        return True, ("System", f"Temp logging {state}")
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
        global reactions
        reactions.clear()
        try:
            os.remove("reactions.txt")
        except:
            pass
        add_message("System", "Chat cleared")
        return True, None
    if cmd == "restart":
        save_messages()
        with open("reactions.txt", "w") as f:
            for mid, emojis in reactions.items():
                for em, users in emojis.items():
                    for u in users:
                        f.write(f"{mid}|{em}|{u}\n")
        add_message("System", "Restarting...")
        time.sleep(1)
        machine.reset()
    return True, ("System", f"Unknown: {cmd}")

def handle_list_files(params):
    if not has_admin_session(params.get('token', '')):
        return json.dumps({"success": False, "message": "Admin session required"}).encode('utf-8')
    try:
        files = []
        for item in os.listdir():
            if item.startswith('.'):
                continue
            try:
                size = os.stat(item)[6]
                files.append({"name": item, "size": size})
            except:
                files.append({"name": item, "size": 0})
        return json.dumps({"success": True, "files": files}).encode('utf-8')
    except Exception as e:
        safe_system_error("List files failed", e)
        return json.dumps({"success": False, "message": "Could not list files"}).encode('utf-8')

def handle_delete_file(params):
    try:
        if not has_admin_session(params.get('token', '')):
            return json.dumps({"success": False, "message": "Admin session required"}).encode('utf-8')
        filename = params.get('filename', '')
        if not filename or '/' in filename or '\\' in filename or '..' in filename:
            return json.dumps({"success": False, "message": "Invalid filename"}).encode('utf-8')
        protected = ['main.py', 'boot.py', 'messages.txt', 'temp_log.txt', 'users.txt', 'reactions.txt', 'config.txt', 'update.html', 'maintenance.html', 'chat.html', 'pinned.txt', 'news.txt']
        if filename in protected:
            return json.dumps({"success": False, "message": "Cannot delete system file"}).encode('utf-8')
        if filename in os.listdir():
            os.remove(filename)
            return json.dumps({"success": True, "message": "Deleted"}).encode('utf-8')
        return json.dumps({"success": False, "message": "File not found"}).encode('utf-8')
    except Exception as e:
        safe_system_error("Delete file failed", e)
        return json.dumps({"success": False, "message": "Delete failed"}).encode('utf-8')

def handle_update_file(params):
    try:
        if not has_admin_session(params.get('token', '')):
            return json.dumps({"success": False, "message": "Admin session required"}).encode('utf-8')
        filename = params.get('filename', '')
        if filename not in ('chat.html', 'maintenance.html', 'update.html'):
            return json.dumps({"success": False, "message": "Unsupported target file"}).encode('utf-8')
        b64 = params.get('content_base64', '')
        if not b64 or len(b64) > 100000:
            return json.dumps({"success": False, "message": "Invalid or oversized content"}).encode('utf-8')
        content = ubinascii.a2b_base64(b64)
        if len(content) > 70000:
            return json.dumps({"success": False, "message": "File exceeds size limit"}).encode('utf-8')
        try:
            with open(filename, 'rb') as f:
                old = f.read()
            with open(filename + '.bak', 'wb') as f:
                f.write(old)
        except:
            pass
        with open(filename, 'wb') as f:
            f.write(content)
        return json.dumps({"success": True, "message": "Updated"}).encode('utf-8')
    except Exception as e:
        safe_system_error("Update file failed", e)
        return json.dumps({"success": False, "message": "Update failed"}).encode('utf-8')

# ========== FILE SERVING WITH CACHING ENABLED ==========
def serve_file_stream(conn_id, filename, content_type="text/html", default_binary=b''):
    try:
        os.stat(filename)
    except:
        content = default_binary
        # Cache allowed even for fallback
        cache_header = "Cache-Control: public, max-age=86400\r\n"
        headers = f"HTTP/1.1 200 OK\r\nContent-Type: {content_type}; charset=utf-8\r\n{cache_header}Content-Length: {len(content)}\r\nConnection: close\r\n\r\n".encode()
        send_small_response(conn_id, headers)
        send_small_response(conn_id, content)
        return

    size = os.stat(filename)[6]
    # Enable long-term caching for all static files (including chat.html)
    cache_header = "Cache-Control: public, max-age=86400\r\n"
    headers = f"HTTP/1.1 200 OK\r\nContent-Type: {content_type}; charset=utf-8\r\n{cache_header}Content-Length: {size}\r\nConnection: close\r\n\r\n".encode()
    if not send_small_response(conn_id, headers):
        return
    try:
        with open(filename, 'rb') as f:
            sent = 0
            while sent < size:
                if wdt:
                    wdt.feed()
                chunk = f.read(512)
                if not chunk:
                    break
                if not send_small_response(conn_id, chunk):
                    break
                sent += len(chunk)
                time.sleep(0.01)
    except Exception as e:
        safe_system_error(f"Streaming {filename}", e)

uart = None
try:
    uart = machine.UART(1, 115200, tx=machine.Pin(4), rx=machine.Pin(5))
    print("UART1 initialized")
except Exception as e:
    safe_system_error("UART init error", e)

def send_cmd(cmd_bytes, expected_bytes, timeout_ms=5000):
    if uart is None: return False
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
    if uart is None: return False
    start = time.ticks_ms()
    while time.ticks_ms() - start < timeout_ms:
        if uart.any():
            if uart.read(1) == b'>':
                return True
    return False

def send_small_response(conn_id, data):
    if uart is None: return False
    try:
        uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(data)).encode() + b'\r\n')
        if not wait_for_prompt(2000):
            return False
        uart.write(data)
        time.sleep(0.05)
        start = time.ticks_ms()
        while time.ticks_ms() - start < 2000:
            if uart.any() and b'OK' in uart.readline():
                return True
        return False
    except Exception as e:
        safe_system_error("send_small_response", e)
        return False

def send_large_response(conn_id, data):
    if uart is None: return False
    chunk_size = 512
    offset = 0
    while offset < len(data):
        if wdt:
            wdt.feed()
        chunk = data[offset:offset+chunk_size]
        try:
            uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(chunk)).encode() + b'\r\n')
            if not wait_for_prompt(2000):
                return False
            uart.write(chunk)
            time.sleep(0.05)
            start = time.ticks_ms()
            ok = False
            while time.ticks_ms() - start < 2000:
                if uart.any() and b'OK' in uart.readline():
                    ok = True
                    break
            if not ok:
                return False
            offset += chunk_size
            time.sleep(0.01)
        except Exception as e:
            safe_system_error("send_large_response", e)
            return False
    return True

def check_wifi_connected():
    if uart is None: return False
    send_cmd(b'AT+CIFSR', b'OK', 2000)
    time.sleep(0.2)
    resp = b''
    while uart.any():
        resp += uart.readline()
    return b'+CIFSR:STAIP,' in resp

def init_wifi():
    global cached_network_info
    if uart is None: return False
    print("Resetting ESP...")
    send_cmd(b'AT+RST', b'ready', 5000)
    time.sleep(2)
    send_cmd(b'AT+CWMODE=1', b'OK')
    print("Connecting to WiFi...")
    if not send_cmd(b'AT+CWJAP="' + SSID.encode() + b'","' + PASSWORD.encode() + b'"', b'OK', 20000):
        safe_system_error("WiFi connection failed")
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
    print("Cached:", cached_network_info)
    send_cmd(b'AT+CIPMUX=1', b'OK')
    send_cmd(b'AT+CIPSERVER=1,' + str(PORT).encode(), b'OK')
    print(f"Server ready on port {PORT}")
    return True

def run():
    global loop_counter, last_wifi_check
    load_config()
    init_users()
    load_messages()
    if len(messages) == 0:
        add_message("System", f"Welcome to HIVE {VERSION}!", 0)
    if not init_wifi():
        print("Cannot start server")
        return
    last_temp_log = time.ticks_ms()
    last_reaction_cleanup = time.ticks_ms()
    print("Main loop running")
    while True:
        if wdt:
            wdt.feed()
        now = time.ticks_ms()
        if time.ticks_diff(now, last_temp_log) >= TEMP_LOG_INTERVAL_MS:
            log_all_temps()
            last_temp_log = now
        if time.ticks_diff(now, last_reaction_cleanup) >= 600000:
            active_ids = {int(m.split(b'|')[0]) for m in messages}
            cleanup_reactions(active_ids)
            last_reaction_cleanup = now
        if time.ticks_diff(now, last_wifi_check) >= 30000:
            if not check_wifi_connected():
                print("WiFi lost, reconnecting...")
                init_wifi()
            last_wifi_check = now

        # Improved request reading
        if uart and uart.any():
            line = uart.readline()
            if line and line.startswith(b'+IPD'):
                conn_id = None
                try:
                    time.sleep(0.05)
                    all_data = bytearray()
                    while uart.any():
                        all_data.extend(uart.read(256))
                    full_line = line + all_data
                    parts = full_line.split(b',', 2)
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
                    data = remaining[colon+1:colon+1+data_len]
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

                    # Maintenance mode whitelist (no change)
                    if is_maintenance_mode() and path not in [b'/api/stats', b'/update', b'/api/login', b'/api/register', b'/maintenance.html', b'/api/list_files', b'/api/delete_file', b'/api/update', b'/api/get_reactions', b'/api/reaction', b'/api/admin', b'/api/msg_poll', b'/api/news'] and not (method == b'GET' and path == b'/'):
                        err_resp = b'HTTP/1.1 503 Service Unavailable\r\nContent-Type: text/html\r\nConnection: close\r\n\r\n<html><body><h1>Maintenance Mode</h1></body></html>'
                        send_small_response(conn_id, err_resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # API routes (unchanged, same as original)
                    if method == b'GET' and path == b'/api/news':
                        news_text = get_news()
                        resp_body = json.dumps({"success": True, "news": news_text}).encode('utf-8')
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp_body)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'GET' and path == b'/api/stats':
                        stats = get_system_stats()
                        stats_dict = {
                            "temp": stats[0],
                            "hum": stats[1],
                            "uptime": stats[2],
                            "msg_count": stats[3],
                            "free_mem": gc.mem_free(),
                            "maintenance": config["maintenance"],
                            "version": VERSION
                        }
                        resp_body = json.dumps(stats_dict).encode('utf-8')
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp_body)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'POST' and path == b'/api/logout':
                        params = parse_request_params(req, query, method)
                        token = params.get('token', '')
                        if token in sessions:
                            del sessions[token]
                        resp = b'{"success":true}'
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'POST' and path == b'/api/login':
                        params = parse_request_params(req, query, method)
                        username = params.get('username', '').strip()
                        password = params.get('password', '')
                        ok, role = login_user(username, password)
                        if ok:
                            token = create_session(username, role)
                            resp = json.dumps({"success": True, "username": username, "role": role, "token": token}).encode('utf-8')
                        else:
                            resp = json.dumps({"success": False, "message": "Invalid credentials"}).encode('utf-8')
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'POST' and path == b'/api/register':
                        params = parse_request_params(req, query, method)
                        username = params.get('username', '').strip()
                        password = params.get('password', '')
                        if not username or not password:
                            resp = json.dumps({"success": False, "message": "Username and password required"}).encode('utf-8')
                        else:
                            ok, msg = register_user(username, password)
                            resp = json.dumps({"success": ok, "message": msg}).encode('utf-8')
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'POST' and path == b'/api/reaction':
                        params = parse_request_params(req, query, method)
                        session = get_session(params.get('token', ''))
                        msg_id = int(params.get('msg_id', 0))
                        emoji = params.get('emoji', '')
                        if not session:
                            resp = json.dumps({"success": False, "message": "Session expired"}).encode('utf-8')
                        elif emoji not in ('👍', '❤️', '😂', '😮', '😢', '😡'):
                            resp = json.dumps({"success": False, "message": "Unsupported reaction"}).encode('utf-8')
                        else:
                            username = session[0]
                            save_reaction(msg_id, emoji, username)
                            updated_reactions = get_reactions_for_msg(msg_id)
                            resp = json.dumps({"success": True, "reactions": updated_reactions}).encode('utf-8')
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'POST' and path == b'/api/admin':
                        params = parse_request_params(req, query, method)
                        session = get_session(params.get('token', ''))
                        cmd = params.get('cmd', '')
                        if not session or session[1] != "admin":
                            resp = json.dumps({"success": False, "message": "Admin only"}).encode('utf-8')
                        else:
                            if cmd == "unpin":
                                save_pinned(0)
                                resp = json.dumps({"success": True, "message": "Pinned message removed"}).encode('utf-8')
                            elif cmd == "maintenance off":
                                config["maintenance"] = False
                                save_config()
                                resp = json.dumps({"success": True, "message": "Maintenance OFF"}).encode('utf-8')
                            elif cmd == "maintenance on":
                                config["maintenance"] = True
                                save_config()
                                resp = json.dumps({"success": True, "message": "Maintenance ON"}).encode('utf-8')
                            else:
                                resp = json.dumps({"success": False, "message": "Unknown command"}).encode('utf-8')
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'POST' and path == b'/api/list_files':
                        params = parse_request_params(req, query, method)
                        resp = handle_list_files(params)
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'POST' and path == b'/api/delete_file':
                        params = parse_request_params(req, query, method)
                        resp = handle_delete_file(params)
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'POST' and path == b'/api/update':
                        params = parse_request_params(req, query, method)
                        resp = handle_update_file(params)
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'POST' and path == b'/api/msg_poll':
                        params = parse_request_params(req, query, method)
                        session = get_session(params.get('token', ''))
                        if not session:
                            err_body = b'{"success":false,"message":"Session expired"}'
                            err_headers = b'HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\nContent-Length: ' + str(len(err_body)).encode() + b'\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n'
                            send_small_response(conn_id, err_headers + err_body)
                            uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                            conn_id = None
                            gc.collect()
                            continue
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
                        resp_body = json.dumps(response_obj).encode('utf-8')
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: ' + str(len(resp_body)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + resp_body)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'POST' and path == b'/send':
                        params = parse_request_params(req, query, method)
                        session = get_session(params.get('token', ''))
                        ok = session is not None
                        if not ok:
                            err_resp = b'HTTP/1.1 401 Unauthorized\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{"success":false,"message":"Auth failed"}'
                            send_small_response(conn_id, err_resp)
                            uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                            conn_id = None
                            gc.collect()
                            continue
                        username = session[0]
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
                            json_resp = json.dumps({"success": True, "id": 0, "total": len(messages)}).encode('utf-8')
                            headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: ' + str(len(json_resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                            send_small_response(conn_id, headers + json_resp)
                            uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                            conn_id = None
                            gc.collect()
                            continue
                        if msg:
                            result = add_message(username, msg, reply)
                            if result is None:
                                json_resp = json.dumps({"success": False, "message": "Message rejected"}).encode('utf-8')
                            else:
                                msg_id, msg_time = result
                                json_resp = json.dumps({"success": True, "id": msg_id, "time": msg_time, "total": len(messages)}).encode('utf-8')
                        else:
                            json_resp = json.dumps({"success": False, "message": "Empty message"}).encode('utf-8')
                        headers = b'HTTP/1.1 200 OK\r\nContent-Type: application/json; charset=utf-8\r\nContent-Length: ' + str(len(json_resp)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_small_response(conn_id, headers + json_resp)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    # HTML pages (chat.html now cached)
                    if method == b'GET' and (path == b'/' or path == b'/chat.html'):
                        if is_maintenance_mode():
                            serve_file_stream(conn_id, "maintenance.html", default_binary=b"<html><body><h1>Maintenance</h1></body></html>")
                        else:
                            serve_file_stream(conn_id, "chat.html", default_binary=b"<html><body><h1>chat.html missing</h1></body></html>")
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'GET' and path == b'/update':
                        serve_file_stream(conn_id, "update.html", default_binary=b"<html><body><h1>update.html missing</h1></body></html>")
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        gc.collect()
                        continue

                    if method == b'POST' and path == b'/download_temps':
                        params = parse_request_params(req, query, method)
                        if not has_admin_session(params.get('token', '')):
                            err_body = b'{"success":false,"message":"Admin session required"}'
                            err_headers = b'HTTP/1.1 401 Unauthorized\\r\\nContent-Type: application/json\\r\\nContent-Length: ' + str(len(err_body)).encode() + b'\\r\\nCache-Control: no-store\\r\\nConnection: close\\r\\n\\r\\n'
                            send_small_response(conn_id, err_headers + err_body)
                        else:
                            serve_file_stream(conn_id, TEMP_LOG_FILE, content_type="text/plain", default_binary=b"")
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
                    safe_system_error("Request handler", e)
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
        time.sleep(0.01)
        loop_counter += 1
        if loop_counter % 100 == 0:
            gc.collect()

if __name__ == "__main__":
    run()