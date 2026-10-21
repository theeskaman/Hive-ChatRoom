import machine
import time
import os

# ========== تنظیمات ==========
SSID = "Mehrbod"
PASSWORD = "357913802"
PORT = 80
MAX_MSGS = 100

messages = []

# ========== عملیات پیام‌ها ==========
def load_messages():
    global messages
    messages = []
    try:
        with open("messages.txt", "rb") as f:
            data = f.read()
        if data:
            for line in data.split(b'\n'):
                if line:
                    messages.append(line)
        print(f"Loaded {len(messages)} messages")
    except:
        print("No messages file, starting fresh")

def save_messages():
    try:
        to_save = messages[-MAX_MSGS:] if len(messages) > MAX_MSGS else messages
        with open("messages.txt", "wb") as f:
            for msg in to_save:
                f.write(msg + b'\n')
        print(f"Saved {len(to_save)} messages")
    except Exception as e:
        print(f"Save error: {e}")

def add_message(msg_bytes):
    if not msg_bytes or len(msg_bytes.strip()) == 0:
        return
    t = time.localtime()
    time_str = "%02d:%02d:%02d" % (t[3], t[4], t[5])
    combined = time_str.encode() + b'|' + msg_bytes.strip()
    messages.append(combined)
    if len(messages) > MAX_MSGS:
        messages.pop(0)
    save_messages()

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
    try:
        sensor = machine.ADC(4)
        v = sensor.read_u16() * 3.3 / 65535
        temp_c = 27 - (v - 0.706) / 0.001721
        temp = f"{temp_c:.1f}°C"
    except:
        temp = "N/A"
    uptime_sec = time.ticks_ms() // 1000
    uptime = f"{uptime_sec//3600}h {(uptime_sec%3600)//60}m {uptime_sec%60}s"
    return temp, uptime, len(messages)

def html_page():
    temp, uptime, msg_count = get_system_stats()
    msg_html = b''
    # نمایش قدیمی‌ترین پیام‌ها در بالا (بدون برعکس کردن)
    for m in messages[-50:]:
        parts = m.split(b'|', 1)
        if len(parts) == 2:
            msg_html += b'<div class="msg"><span class="time">' + parts[0] + b'</span> <span class="text">' + parts[1] + b'</span></div>'
        else:
            msg_html += b'<div>' + m + b'</div>'
    html = b"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>HIVE chatroom 1.3-ALPHA</title>
<style>
body{font-family:sans-serif;max-width:700px;margin:auto;padding:20px;background:#121212;color:#e0e0e0}
.msgs{background:#1e1e1e;border-radius:10px;padding:10px;height:400px;overflow-y:auto;margin-bottom:10px}
.msg{padding:6px;border-bottom:1px solid #333}
.time{color:#80cbc4;font-weight:bold}
.text{color:#fff}
form{display:flex;gap:8px;margin:10px 0}
input{flex:1;padding:8px;border:1px solid #555;border-radius:20px;background:#333;color:#fff}
button{background:#90caf9;color:#000;border:none;padding:8px 18px;border-radius:20px;cursor:pointer;font-weight:bold}
.stats{font-size:0.8em;background:#333;padding:6px;border-radius:8px;text-align:center}
.menu{display:flex;gap:15px;justify-content:center;margin-top:10px}
.menu a{color:#90caf9;text-decoration:none;font-weight:bold}
</style>
</head>
<body>
<h2>💬 HIVE chatroom 1.3-ALPHA</h2>
<div class="msgs">""" + msg_html + b"""</div>
<form action="/send" method="GET" accept-charset="UTF-8">
<input type="text" name="msg" placeholder="Write a message..." autofocus required>
<button type="submit">Send</button>
</form>
<div class="menu">
<button onclick="location.reload();">🔄 Refresh</button>
<a href="/download_msgs" target="_blank">⬇️ Download Messages</a>
</div>
<div class="stats">
📊 Temp: """ + temp.encode() + b""" | Uptime: """ + uptime.encode() + b""" | Messages: """ + str(msg_count).encode() + b"""
</div>
</body>
</html>"""
    return html.replace(b'\n', b'\r\n')

def download_messages():
    try:
        with open("messages.txt", "rb") as f:
            content = f.read()
        return content
    except:
        return b"No messages file yet."

# ========== راه‌اندازی UART (ESP01s) ==========
print("System starting")
load_messages()
if len(messages) == 0:
    add_message(b"Welcome! \xd8\xae\xd9\x88\xd8\xb4 \xd8\xa2\xd9\x85\xd8\xaf\xdb\x8c\xd8\xaf")  # خوش آمدید

try:
    uart = machine.UART(1, 115200)
    print("UART1 initialized")
except Exception as e:
    print(f"UART init error: {e}")
    uart = None

def send_cmd(cmd_bytes, expected_bytes, timeout_ms=5000):
    if uart is None:
        return False
    while uart.any():
        uart.read()
    print(f">>> {cmd_bytes}")
    uart.write(cmd_bytes + b'\r\n')
    start = time.ticks_ms()
    while time.ticks_ms() - start < timeout_ms:
        if uart.any():
            line = uart.readline()
            if line:
                print(f"<<< {line}")
                if expected_bytes in line:
                    return True
    print(f"Timeout: {cmd_bytes}")
    return False

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

# ========== حلقه اصلی ==========
while True:
    if uart and uart.any():
        line = uart.readline()
        if line and line.startswith(b'+IPD'):
            try:
                parts = line.split(b',', 2)
                if len(parts) >= 3:
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

                    # ========== صفحه اصلی ==========
                    if method == b'GET' and path == b'/':
                        html = html_page()
                        resp = b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: ' + str(len(html)).encode() + b'\r\nConnection: close\r\n\r\n' + html
                        uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(resp)).encode() + b'\r\n')
                        time.sleep(0.1)
                        start_wait = time.ticks_ms()
                        while time.ticks_ms() - start_wait < 2000:
                            if uart.any() and uart.read(1) == b'>':
                                break
                        uart.write(resp)
                        time.sleep(0.1)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')

                    # ========== ارسال پیام ==========
                    elif method == b'GET' and path == b'/send':
                        msg = b''
                        if query.startswith(b'msg='):
                            raw = query[4:]
                            amp = raw.find(b'&')
                            if amp != -1:
                                raw = raw[:amp]
                            raw = raw.replace(b'+', b' ')
                            msg = percent_decode(raw)
                            if msg:
                                add_message(msg[:250])
                        redirect = b'HTTP/1.1 302 Found\r\nLocation: /\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                        uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(redirect)).encode() + b'\r\n')
                        time.sleep(0.1)
                        while uart.any() and uart.read(1) != b'>':
                            pass
                        uart.write(redirect)
                        time.sleep(0.1)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')

                    # ========== دانلود مستقیم فایل پیام‌ها ==========
                    elif method == b'GET' and path == b'/download_msgs':
                        content = download_messages()
                        resp = b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename="messages.txt"\r\nContent-Length: ' + str(len(content)).encode() + b'\r\nConnection: close\r\n\r\n' + content
                        uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(resp)).encode() + b'\r\n')
                        time.sleep(0.1)
                        start_wait = time.ticks_ms()
                        while time.ticks_ms() - start_wait < 2000:
                            if uart.any() and uart.read(1) == b'>':
                                break
                        uart.write(resp)
                        time.sleep(0.1)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')

                    # ========== favicon ==========
                    elif path == b'/favicon.ico':
                        noicon = b'HTTP/1.1 204 No Content\r\nConnection: close\r\n\r\n'
                        uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(noicon)).encode() + b'\r\n')
                        time.sleep(0.1)
                        while uart.any() and uart.read(1) != b'>':
                            pass
                        uart.write(noicon)
                        time.sleep(0.1)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    else:
                        resp404 = b'HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                        uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(resp404)).encode() + b'\r\n')
                        time.sleep(0.1)
                        while uart.any() and uart.read(1) != b'>':
                            pass
                        uart.write(resp404)
                        time.sleep(0.1)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
            except Exception as e:
                print(f"Handler error: {e}")
    time.sleep(0.05)