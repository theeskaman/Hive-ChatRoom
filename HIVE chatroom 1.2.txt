import machine
import time

SSID = "Mehrbod"
PASSWORD = "357913802"
PORT = 80
MAX_MSGS = 100

messages = []

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
        print("Loaded", len(messages), "messages")
    except:
        print("Fresh start")

def save_messages():
    try:
        to_save = messages[-MAX_MSGS:] if len(messages) > MAX_MSGS else messages
        with open("messages.txt", "wb") as f:
            for m in to_save:
                f.write(m + b'\n')
        print("Saved", len(to_save), "messages")
    except Exception as e:
        print("Save error:", e)

def add_message(msg_bytes):
    if not msg_bytes or len(msg_bytes.strip()) == 0:
        return
    t = time.localtime()
    ts = "%02d:%02d:%02d" % (t[3], t[4], t[5])
    combined = ts.encode() + b'|' + msg_bytes.strip()
    messages.append(combined)
    if len(messages) > MAX_MSGS:
        messages.pop(0)
    save_messages()
    print("New message:", msg_bytes[:50])

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

def get_stats():
    try:
        adc = machine.ADC(4)
        v = adc.read_u16() * 3.3 / 65535
        temp = 27 - (v - 0.706) / 0.001721
        temp_str = f"{temp:.1f}°C"
    except:
        temp_str = "N/A"
    uptime_sec = time.ticks_ms() // 1000
    uptime = f"{uptime_sec//3600}h {(uptime_sec%3600)//60}m {uptime_sec%60}s"
    return temp_str, uptime, len(messages)

def html_page():
    temp, uptime, msg_cnt = get_stats()
    msg_html = b''
    for m in reversed(messages[-50:]):
        parts = m.split(b'|', 1)
        if len(parts) == 2:
            msg_html += b'<div class="msg"><span class="time">' + parts[0] + b'</span><span class="text">' + parts[1] + b'</span></div>'
        else:
            msg_html += b'<div class="msg">' + m + b'</div>'
    html = b"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><title>HIVE chatroom test 1</title>
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<style>
body{background:#0a0c10;font-family:system-ui;margin:0;padding:20px;display:flex;justify-content:center}
.container{max-width:720px;width:100%;background:#1e1e2e;border-radius:28px;overflow:hidden}
.header{padding:16px;text-align:center;background:#11131e;border-bottom:1px solid #2a2a3a}
.header h2{margin:0;color:#c084fc}
.msgs{height:400px;overflow-y:auto;padding:12px;background:#12141c}
.msg{background:#252531;margin-bottom:10px;padding:8px 12px;border-radius:16px;border-left:4px solid #c084fc}
.time{color:#7aa2f7;font-size:0.7rem;margin-right:12px}
.text{color:#e2e8f0}
.input-area{padding:16px;background:#11131e;border-top:1px solid #2a2a3a}
form{display:flex;gap:10px}
input{flex:1;background:#252836;border:none;padding:12px;border-radius:40px;color:#fff;outline:none}
button{background:#c084fc;border:none;padding:0 24px;border-radius:40px;font-weight:bold;cursor:pointer}
.refresh, .download{background:#3b3f5c;color:white;margin-top:10px;padding:8px 20px;border-radius:40px;border:none;cursor:pointer;display:inline-block;text-decoration:none;font-size:0.9rem}
.download{background:#2a5c5c;margin-left:10px}
.stats{text-align:center;padding:8px;font-size:0.7rem;color:#9ca3af}
</style>
</head>
<body>
<div class="container">
<div class="header"><h2>💬 HIVE chatroom test 1</h2></div>
<div class="msgs">""" + msg_html + b"""</div>
<div class="input-area">
<form action="/send" method="GET" accept-charset="UTF-8">
<input type="text" name="msg" placeholder="Message..." autofocus required>
<button type="submit">Send</button>
</form>
<div style="display:flex; gap:10px; margin-top:12px;">
<button class="refresh" onclick="window.location.href='/'">⟳ Refresh</button>
<a class="download" href="/download_messages">📥 Download messages.txt</a>
</div>
</div>
<div class="stats">🌡️ """ + temp.encode() + b""" &nbsp;| ⏱️ """ + uptime.encode() + b""" &nbsp;| 💬 """ + str(msg_cnt).encode() + b"""</div>
</div>
<script>
    var msgsDiv = document.querySelector('.msgs');
    msgsDiv.scrollTop = msgsDiv.scrollHeight;
</script>
</body>
</html>"""
    return html.replace(b'\n', b'\r\n')

# ---------- UART ----------
try:
    uart = machine.UART(1, 115200)
    print("UART ready")
except Exception as e:
    print("UART error:", e)
    uart = None

def send_cmd(cmd, expect, timeout=5000):
    if not uart: return False
    while uart.any(): uart.read()
    uart.write(cmd + b'\r\n')
    start = time.ticks_ms()
    while time.ticks_ms() - start < timeout:
        if uart.any():
            line = uart.readline()
            if line and expect in line:
                return True
    return False

def send_chunked(conn_id, data, chunk=1024):
    offset = 0
    while offset < len(data):
        part = data[offset:offset+chunk]
        uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(part)).encode() + b'\r\n')
        time.sleep(0.08)
        # Wait for '>'
        start = time.ticks_ms()
        while time.ticks_ms() - start < 2000:
            if uart.any() and uart.read(1) == b'>':
                break
        uart.write(part)
        time.sleep(0.08)
        # Wait for SEND OK
        start_ok = time.ticks_ms()
        ok = False
        while time.ticks_ms() - start_ok < 3000:
            if uart.any():
                line = uart.readline()
                if line and b'SEND OK' in line:
                    ok = True
                    break
        if not ok:
            return False
        offset += chunk
    return True

# ---------- ESP setup ----------
print("Loading messages...")
load_messages()
if len(messages) == 0:
    add_message(b"Welcome to HIVE chatroom test 1! \xf0\x9f\x8c\x99")

if uart:
    print("Reset ESP...")
    send_cmd(b'AT+RST', b'ready', 5000)
    time.sleep(2)
    send_cmd(b'AT+CWMODE=1', b'OK')
    print("Connecting WiFi...")
    if not send_cmd(b'AT+CWJAP="' + SSID.encode() + b'","' + PASSWORD.encode() + b'"', b'OK', 20000):
        print("WiFi fail")
        uart = None
    else:
        print("WiFi OK")
        send_cmd(b'AT+CIFSR', b'OK')
        send_cmd(b'AT+CIPMUX=1', b'OK')
        send_cmd(b'AT+CIPSERVER=1,' + str(PORT).encode(), b'OK')
        print("Server ready. Find IP above.")

# ---------- Main loop ----------
while True:
    if uart and uart.any():
        line = uart.readline()
        if line and line.startswith(b'+IPD'):
            try:
                parts = line.split(b',', 2)
                if len(parts) >= 3:
                    conn_id = int(parts[1])
                    remain = parts[2]
                    colon = remain.find(b':')
                    if colon == -1:
                        continue
                    data_len = int(remain[:colon])
                    data = remain[colon+1:]
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
                    full = first[1]
                    path = full.split(b'?')[0]
                    query = full.split(b'?')[1] if b'?' in full else b''
                    
                    if method == b'GET' and path == b'/':
                        html = html_page()
                        header = b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nCache-Control: no-cache, no-store, must-revalidate\r\nPragma: no-cache\r\nExpires: 0\r\nContent-Length: ' + str(len(html)).encode() + b'\r\nConnection: close\r\n\r\n'
                        send_chunked(conn_id, header)
                        send_chunked(conn_id, html)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    
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
                        # ارسال ریدایرکت به صفحه اصلی (جلوگیری از ارسال مجدد با رفرش)
                        redirect = b'HTTP/1.1 302 Found\r\nLocation: /\r\nContent-Length: 0\r\nConnection: close\r\n\r\n'
                        uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',' + str(len(redirect)).encode() + b'\r\n')
                        time.sleep(0.1)
                        while uart.any() and uart.read(1) != b'>':
                            pass
                        uart.write(redirect)
                        time.sleep(0.1)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    
                    elif method == b'GET' and path == b'/download_messages':
                        try:
                            with open("messages.txt", "rb") as f:
                                content = f.read()
                            header = b'HTTP/1.1 200 OK\r\nContent-Type: application/octet-stream\r\nContent-Disposition: attachment; filename="messages.txt"\r\nCache-Control: no-cache\r\nContent-Length: ' + str(len(content)).encode() + b'\r\nConnection: close\r\n\r\n'
                            send_chunked(conn_id, header)
                            send_chunked(conn_id, content)
                            uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                            print("Messages file downloaded")
                        except Exception as e:
                            err = b'HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\nConnection: close\r\n\r\nFile not found'
                            send_chunked(conn_id, err)
                            uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    
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
                        uart.write(b'AT+CIPSEND=' + str(conn_id).encode() + b',0\r\n')
                        time.sleep(0.1)
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
            except Exception as e:
                print("Handler error:", e)
    time.sleep(0.05)