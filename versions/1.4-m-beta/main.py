import machine
import time
import os

# ========== تنظیمات ==========
SSID = "YOUR_WIFI_SSID"
PASSWORD = "YOUR_WIFI_PASSWORD"
PORT = 80
MAX_MSGS = 100
DISPLAY_MSGS = 20

messages = []

# ========== عملیات فایل ==========
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
        messages = []

def save_messages():
    try:
        to_save = messages[-MAX_MSGS:] if len(messages) > MAX_MSGS else messages
        with open("messages.txt", "wb") as f:
            for msg in to_save:
                f.write(msg + b'\n')
        print(f"Saved {len(to_save)} messages")
    except Exception as e:
        print(f"Save error: {e}")

# ========== پالایش ==========
def sanitize(bs):
    bs = bs.replace(b'\r\n', b' ').replace(b'\r', b' ').replace(b'\n', b' ')
    out = bytearray()
    for b in bs:
        if b == 0x09 or 0x20 <= b <= 0x7E or b >= 0x80:
            out.append(b)
    return bytes(out)

def add_message(msg_bytes):
    if not msg_bytes or len(msg_bytes.strip()) == 0:
        return
    msg_bytes = sanitize(msg_bytes).strip()
    if not msg_bytes:
        return
    t = time.localtime()
    time_str = "%02d:%02d:%02d" % (t[3], t[4], t[5])
    combined = time_str.encode() + b'|' + msg_bytes[:100]
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
        temp = f"{temp_c:.1f}C"
    except:
        temp = "N/A"
    uptime_sec = time.ticks_ms() // 1000
    uptime = f"{uptime_sec//3600}h {(uptime_sec%3600)//60}m"
    return temp, uptime, len(messages)

# ========== ارسال پاسخ به صورت تکه‌تکه ==========
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

def html_page():
    temp, uptime, msg_count = get_system_stats()
    msg_html = b''
    for m in messages[-DISPLAY_MSGS:]:
        parts = m.split(b'|', 1)
        if len(parts) == 2:
            msg_html += b'<div class=m><span class=t>' + parts[0] + b'</span><span class=msg-txt>' + parts[1] + b'</span></div>'
        else:
            msg_html += b'<div class=m>' + m + b'</div>'

    # رفع مشکل Full Screen با استفاده از dvh و تنظیمات دقیق‌تر
    html = b'''<!DOCTYPE html><html><head><meta charset=UTF-8><meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no,viewport-fit=cover"><title>HIVE ChatRoom 1.4.m · Beta</title><style>html,body{height:100%;height:100dvh;margin:0;font-family:system-ui,sans-serif;color:#eef2ff;overflow:hidden}body{background:#0a0f1a;display:flex;justify-content:center;align-items:center}.c{width:100%;max-width:700px;height:100%;height:100dvh;display:flex;flex-direction:column;background:#111827;overflow:hidden}.h{background:#0f172a;padding:12px 16px;text-align:center;border-bottom:1px solid #1e2a3e;flex-shrink:0}.h h2{font-weight:600;font-size:1.4rem;background:linear-gradient(135deg,#7dd3fc,#38bdf8);-webkit-background-clip:text;background-clip:text;color:transparent}.msgs{flex:1;overflow-y:auto;margin:10px;background:#0f172a;border-radius:20px;padding:6px;-webkit-overflow-scrolling:touch;scrollbar-width:thin;scrollbar-color:#334155 #0f172a}.msgs::-webkit-scrollbar{width:3px}.msgs::-webkit-scrollbar-thumb{background:#334155;border-radius:10px}.m{display:flex;align-items:baseline;gap:8px;padding:8px 12px;margin-bottom:4px;background:#1e293b;border-radius:18px}.t{background:#0f172a;padding:2px 8px;border-radius:30px;font-family:monospace;font-size:0.7rem;color:#7dd3fc;white-space:nowrap}.msg-txt{word-break:break-word;font-size:0.9rem;line-height:1.4}form{display:flex;gap:8px;margin:0 10px 10px 10px;flex-shrink:0}input{flex:1;background:#0f172a;border:1px solid #334155;padding:12px 14px;border-radius:40px;color:#fff;font-size:16px;outline:none}input:focus{border-color:#38bdf8}button{background:#1e3a8a;border:none;padding:12px 20px;border-radius:40px;font-weight:bold;color:#fff;font-size:16px;cursor:pointer}.menu{display:flex;gap:12px;justify-content:center;margin:0 10px 10px 10px;flex-shrink:0}.menu a,.menu .re{background:#1e293b;padding:8px 18px;border-radius:40px;text-decoration:none;font-size:0.8rem;color:#bae6fd;border:1px solid #334155;cursor:pointer;display:inline-block}.stats{background:#0f172a;padding:10px;font-size:0.75rem;text-align:center;display:flex;justify-content:center;gap:12px;flex-wrap:wrap;border-top:1px solid #1e2a3e;flex-shrink:0}.stats span{background:#1e293b;padding:4px 12px;border-radius:30px}</style><script>window.onload=function(){let d=document.querySelector('.msgs');if(d)d.scrollTop=d.scrollHeight;document.querySelector('input')?.focus();}</script></head><body><div class=c><div class=h><h2>💬 HIVE ChatRoom 1.4.m · Beta</h2></div><div class=msgs>''' + msg_html + b'''</div><form action=/send method=GET><input type=text name=msg placeholder="Message..." autofocus required><button>Send</button></form><div class=menu><button class=re onclick="location.reload()">🔄 Refresh</button><a href=/download_msgs target=_blank>⬇️ Download</a></div><div class=stats><span>🌡️ ''' + temp.encode() + b'''</span><span>⏱️ ''' + uptime.encode() + b'''</span><span>💬 ''' + str(msg_count).encode() + b'''</span></div></div></body></html>'''
    return html.replace(b'\n', b'\r\n')

def download_messages():
    try:
        with open("messages.txt", "rb") as f:
            return f.read()
    except:
        return b"No messages file yet."

# ========== راه‌اندازی UART و ESP01s ==========
print("System starting")
load_messages()
if len(messages) == 0:
    add_message(b"Welcome! \xd8\xae\xd9\x88\xd8\xb4 \xd8\xa2\xd9\x85\xd8\xaf\xdb\x8c\xd8\xaf")

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

                if method == b'GET' and path == b'/':
                    html = html_page()
                    headers = b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: ' + str(len(html)).encode() + b'\r\nConnection: close\r\n\r\n'
                    full_response = headers + html
                    if send_large_response(conn_id, full_response):
                        print("Page sent")
                    else:
                        print("Failed to send page")
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None

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
                            add_message(msg)
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
                    if send_large_response(conn_id, resp):
                        print("Download sent")
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