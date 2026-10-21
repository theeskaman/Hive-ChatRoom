import machine
import time
import os
import gc
import dht
import json
import sys

# ========== CONFIG ==========
SSID = "Mehrbod"
PASSWORD = "357913802"
PORT = 80
MAX_MSGS = 2000
DISPLAY_MSGS = 30
MIN_FREE_MEM = 40000
ADMIN_PASS = "nigga"
DHT_PIN = 0
MAX_MSG_CHARS = 400

messages = []
next_id = 1
TEMP_LOG_FILE = "temp_log.txt"
TEMP_LOG_INTERVAL_MS = 60000

last_dht_read = 0
last_dht_temp = None
last_dht_hum = None
dht_error_printed = False
system_error_logged = {}

VERSION = "1.8.3 lite"

try:
    wdt = machine.WDT(timeout=300000)
except:
    wdt = None

# ========== HELPER FUNCTIONS ==========
def simple_hash(s):
    h = 0
    for ch in s:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h

def sanitize_string(s):
    s = s.replace('|', '¦').replace('\r', ' ').replace('\n', ' ')
    res = []
    for ch in s:
        if ch >= ' ' or ch == '\t':
            res.append(ch)
    return ''.join(res).strip()

def load_messages():
    global messages, next_id
    messages = []
    max_id = 0
    try:
        with open("messages.txt", "rb") as f:
            data = f.read()
        if data:
            for line in data.split(b'\n'):
                if not line: continue
                parts = line.split(b'|')
                if len(parts) >= 6:
                    try:
                        mid = int(parts[0])
                        if mid > max_id: max_id = mid
                        messages.append(line)
                    except: pass
                elif len(parts) == 5:
                    try:
                        mid = int(parts[0])
                        if mid > max_id: max_id = mid
                        messages.append(parts[0] + b'|' + parts[1] + b'|' + parts[2] + b'|' + parts[3] + b'|' + parts[4] + b'|0')
                    except: pass
                elif len(parts) == 2:
                    messages.append(b'0|' + parts[0] + b'|Legacy|' + parts[1] + b'|0|0')
        next_id = max_id + 1
    except:
        messages = []
        next_id = 1

def save_messages():
    try:
        to_save = messages[-MAX_MSGS:] if len(messages) > MAX_MSGS else messages
        with open("messages.txt", "wb") as f:
            for msg in to_save:
                f.write(msg + b'\n')
    except Exception as e:
        system_error("Save failed", e)

def add_message(username, text, reply_to=0):
    global messages, next_id
    if not text: return None
    text_san = sanitize_string(text)
    if not text_san: return None
    if len(text_san) > MAX_MSG_CHARS:
        text_san = text_san[:MAX_MSG_CHARS]
    user_san = sanitize_string(username)[:20] or "Anonymous"
    t = time.localtime()
    time_str = "%02d:%02d:%02d" % (t[3], t[4], t[5])
    ts_unix = time.mktime(t)
    msg_id = next_id
    next_id += 1
    line = b"%d|%s|%s|%s|%d|%d" % (msg_id, time_str.encode(), user_san.encode('utf-8'), text_san.encode('utf-8'), reply_to, ts_unix)
    messages.append(line)
    if len(messages) > MAX_MSGS:
        messages.pop(0)
    save_messages()
    return msg_id, time_str

def system_error(err_msg, exc=None):
    global system_error_logged
    key = err_msg[:50]
    now = time.time()
    if key in system_error_logged and now - system_error_logged[key] < 30:
        return
    system_error_logged[key] = now
    if exc:
        sys.print_exception(exc)
    add_message("System", f"⚠️ {err_msg}"[:190].replace('|','¦'))
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
            system_error("DHT11 error", e)
            dht_error_printed = True
        return None, None

def log_all_temps():
    try:
        cpu_temp = read_cpu_temp()
        dht_temp, dht_hum = read_dht11()
        now = time.localtime()
        time_str = "%02d:%02d:%02d" % (now[3], now[4], now[5])
        cpu_str = f"{cpu_temp:.1f}" if cpu_temp is not None else "---"
        dht_t = f"{dht_temp:.1f}" if dht_temp is not None else "---"
        dht_h = f"{dht_hum:.1f}" if dht_hum is not None else "---"
        with open(TEMP_LOG_FILE, "a") as f:
            f.write(f"{time_str}|{cpu_str}|{dht_t}|{dht_h}\n")
    except Exception as e:
        system_error("Temp log failed", e)

def percent_decode(bs):
    out = bytearray()
    i = 0
    L = len(bs)
    while i < L:
        if bs[i] == 37 and i+2 < L:
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

# ========== HTML PAGE (corrected string then encode) ==========
def html_page():
    gc.collect()
    free_mem = gc.mem_free()
    display_count = 10 if free_mem < MIN_FREE_MEM else DISPLAY_MSGS
    temp_str, hum_str, uptime, msg_count = get_system_stats()

    msgs_to_show = messages[-display_count:] if len(messages) > display_count else messages
    max_msg_id = 0
    for m in messages:
        parts = m.split(b'|')
        if parts and parts[0].isdigit():
            mid = int(parts[0])
            if mid > max_msg_id: max_msg_id = mid

    # Build messages HTML as string
    msg_html = []
    for m in msgs_to_show:
        parts = m.split(b'|')
        if len(parts) < 5: continue
        mid = int(parts[0])
        username = parts[2].decode('utf-8', 'replace')
        txt = parts[3].decode('utf-8', 'replace')
        reply_to = int(parts[4])
        timestamp = int(parts[5]) if len(parts) > 5 else 0
        hue = simple_hash(username) % 360
        reply_badge = ''
        if reply_to:
            rname = get_message_by_id(reply_to)
            if rname:
                reply_badge = f'<span class="rb">↩️ {rname}</span>'
        msg_html.append(f'<div class="msg" data-id="{mid}" data-u="{username}" data-ts={timestamp}>'
                        f'<div class="av" style="background:hsl({hue},70%,55%);">{username[:2].upper()}</div>'
                        f'<div class="mc"><div class="mh"><span class="un">{username}</span>'
                        f'<span class="tm"></span>{reply_badge}</div>'
                        f'<div class="mt">{txt}</div>'
                        f'<div class="ma"><button class="rb" data-id="{mid}" data-name="{username}">💬 Reply</button></div>'
                        f'</div></div>')
    msg_html_str = ''.join(msg_html)

    # Full HTML template (as normal string, not bytes literal)
    html_str = '''<!DOCTYPE html><html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=yes"><title>HIVE lite</title><style>
:root{--bg:#0b0f19;--s:#151c2c;--p:#a78bfa;--t:#e2e8f0}*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);font-family:sans-serif;color:var(--t);height:100dvh;overflow:hidden;display:flex;justify-content:center;align-items:center}
.app{width:100%;height:100%;max-width:600px;background:rgba(21,28,44,0.6);backdrop-filter:blur(20px);display:flex;flex-direction:column;overflow:hidden}
.login-overlay{position:fixed;inset:0;background:rgba(11,15,25,0.95);backdrop-filter:blur(20px);display:flex;justify-content:center;align-items:center;z-index:200}
.login-box{background:rgba(21,28,44,0.8);border:1px solid rgba(255,255,255,0.08);border-radius:24px;padding:2rem;width:90%;max-width:360px;text-align:center}
.login-box h2{font-size:1.8rem;margin-bottom:1.5rem;background:linear-gradient(135deg,#a78bfa,#f472b6);-webkit-background-clip:text;background-clip:text;color:transparent}
.login-box input{width:100%;padding:0.8rem;border-radius:25px;background:#0f172a;border:1px solid #334155;color:#fff;margin-bottom:1rem}
.login-box button{width:100%;padding:0.8rem;border-radius:25px;background:linear-gradient(135deg,#7c3aed,#ec4899);border:none;color:#fff;font-weight:bold;cursor:pointer}
.header{background:linear-gradient(135deg,rgba(124,58,237,0.15),rgba(236,72,153,0.1));padding:1rem;border-bottom:1px solid rgba(255,255,255,0.08);text-align:center}
.header h1{font-size:1.6rem;background:linear-gradient(135deg,#a78bfa,#f472b6);-webkit-background-clip:text;background-clip:text;color:transparent}
.badge{font-size:0.7rem;background:rgba(45,55,72,0.8);display:inline-block;padding:0.2rem 1rem;border-radius:20px}
.stats-bar{display:flex;background:rgba(0,0,0,0.3);padding:0.5rem;gap:0.5rem;overflow-x:auto}
.stat{background:#1e293b;padding:0.3rem 0.8rem;border-radius:30px;font-size:0.75rem}
.messages-container{flex:1;overflow-y:auto;padding:1rem;display:flex;flex-direction:column;gap:0.8rem}
.msg{display:flex;gap:0.7rem;background:rgba(30,41,59,0.5);border-radius:18px;padding:0.8rem;border:1px solid rgba(255,255,255,0.08)}
.av{width:2.4rem;height:2.4rem;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:bold;color:#fff;flex-shrink:0}
.mc{flex:1}.mh{display:flex;align-items:baseline;gap:0.5rem;flex-wrap:wrap;margin-bottom:0.3rem}
.un{font-weight:700;color:var(--p)}.tm{font-size:0.65rem;color:#94a3b8}
.rb{background:rgba(71,85,105,0.7);padding:0.2rem 0.6rem;border-radius:20px;font-size:0.65rem}
.mt{font-size:0.9rem;word-break:break-word;cursor:pointer;margin:0.4rem 0}
.ma button{background:none;border:1px solid #475569;color:#cbd5e0;font-size:0.7rem;padding:0.3rem 0.8rem;border-radius:20px;cursor:pointer}
#inputArea{position:fixed;bottom:0;left:0;right:0;max-width:600px;margin:0 auto;background:rgba(15,23,42,0.9);backdrop-filter:blur(12px);border-top:1px solid rgba(255,255,255,0.08);padding:0.8rem;padding-bottom:calc(0.8rem + env(safe-area-inset-bottom,0px))}
.reply-indicator{background:#4c1d95;border-radius:25px;padding:0.5rem;margin-bottom:0.6rem;font-size:0.75rem;display:flex;justify-content:space-between}
.input-row{display:flex;gap:0.5rem;flex-wrap:wrap}.input-row input{flex:1;background:#0f172a;border:1px solid #334155;padding:0.7rem;border-radius:25px;color:#fff}
.send-button{background:linear-gradient(135deg,#7c3aed,#ec4899);border:none;border-radius:25px;padding:0 1.4rem;color:#fff;font-weight:bold;cursor:pointer}
.menu-buttons{display:flex;gap:0.4rem;justify-content:center;flex-wrap:wrap;margin-top:0.5rem}
.menu-buttons button,.menu-buttons a{background:rgba(51,65,85,0.7);padding:0.3rem 0.8rem;border-radius:20px;font-size:0.7rem;color:#cbd5e0;text-decoration:none;border:1px solid rgba(255,255,255,0.1);cursor:pointer}
.toast{position:fixed;bottom:5rem;left:50%;transform:translateX(-50%);background:#334155;color:#fff;padding:0.5rem 1.2rem;border-radius:20px;opacity:0;transition:opacity 0.3s;z-index:1000}
.char-counter{font-size:0.7rem;margin-left:0.5rem;color:#94a3b8}.char-counter.danger{color:#ef4444}
</style></head><body>
<div id="loginOverlay" class="login-overlay"><div class="login-box"><h2>💬 HIVE Lite</h2><input type="text" id="loginName" placeholder="Username" maxlength="20"><button onclick="doLogin()">Enter Chat</button></div></div>
<div class="app" id="appMain" style="display:none">
<div class="header"><h1>💬 HIVE Lite</h1><div class="badge">⚡ v''' + VERSION + '''</div></div>
<div class="stats-bar" id="statsBar"><div class="stat">🌡️ ''' + temp_str + '''</div><div class="stat">💧 ''' + hum_str + '''</div><div class="stat">⏱️ ''' + uptime + '''</div><div class="stat">💬 ''' + str(msg_count) + '''</div></div>
<div class="messages-container" id="msgContainer">''' + msg_html_str + '''</div>
<div id="inputArea"><div id="replyIndicator" style="display:none" class="reply-indicator"><span id="replyInfoText"></span><button onclick="clearReply()">Cancel</button></div>
<form id="msgForm"><div class="input-row"><input type="text" id="msg_input" placeholder="Message (max 400)" maxlength="400" required><span id="charCounter" class="char-counter">0/400</span><input type="hidden" id="reply_to" value="0"><button class="send-button" type="submit">Send</button></div></form>
<div class="menu-buttons"><button onclick="location.reload()">🔄 Refresh</button><a href="/download_msgs" download>⬇️ Msgs</a><a href="/download_temps" download>🌡️ Log</a><button onclick="toggleScroll()">📌 Scroll</button><button onclick="clearChat()">🗑️ Clear</button><button onclick="changeName()">🔄 Name</button><button id="notifyBtn">🔔 Notify</button></div></div></div>
<div id="toast" class="toast"></div>
<script>
let lastMsgId=''' + str(max_msg_id) + ''',replyTo=0,replyName='',autoScroll=true,sending=false,user='',notif=false;
const MAXL=400;
function fixPad(){let i=document.getElementById('inputArea'),m=document.getElementById('msgContainer');if(i&&m)m.style.paddingBottom=(i.offsetHeight+8)+'px'}
function doLogin(){let n=document.getElementById('loginName').value.trim();if(!n)return toast('Enter name');user=n;localStorage.setItem('user',n);document.getElementById('loginOverlay').style.display='none';document.getElementById('appMain').style.display='flex';fixPad();init()}
function changeName(){localStorage.removeItem('user');document.getElementById('loginOverlay').style.display='flex';document.getElementById('appMain').style.display='none';user='';notif=false}
function toast(m){let t=document.getElementById('toast');t.innerText=m;t.style.opacity='1';setTimeout(()=>t.style.opacity='0',1800)}
function toggleScroll(){autoScroll=!autoScroll;toast(autoScroll?'Scroll ON':'Scroll OFF')}
function clearReply(){replyTo=0;replyName='';document.getElementById('reply_to').value='0';document.getElementById('replyIndicator').style.display='none'}
function formatTime(ts){if(!ts)return'';let d=Math.floor(Date.now()/1000)-ts;if(d<60)return'just now';if(d<3600)return Math.floor(d/60)+' min';if(d<86400)return Math.floor(d/3600)+' h';return Math.floor(d/86400)+' d'}
function updateTimestamps(){document.querySelectorAll('.tm').forEach(el=>{let ts=parseInt(el.parentElement.parentElement.parentElement.dataset.ts);if(ts)el.innerText=formatTime(ts)})}
function copyText(el){navigator.clipboard.writeText(el.innerText);toast('Copied!')}
function escape(s){return s.replace(/[&<>]/g,function(m){return m==='&'?'&amp;':m==='<'?'&lt;':'&gt;'})}
function appendMsg(m){let hue=(function(s){let h=0;for(let i=0;i<s.length;i++)h=(h*31+s.charCodeAt(i))&0xFFFFFFFF;return h%360})(m.user);let rb=m.reply&&m.reply_user?`<span class="rb">↩️ ${escape(m.reply_user)}</span>`:'';let div=document.createElement('div');div.className='msg';div.dataset.id=m.id;div.dataset.u=m.user;div.dataset.ts=m.timestamp;div.innerHTML=`<div class="av" style="background:hsl(${hue},70%,55%);">${escape(m.user.substring(0,2).toUpperCase())}</div><div class="mc"><div class="mh"><span class="un">${escape(m.user)}</span><span class="tm">${formatTime(m.timestamp)}</span>${rb}</div><div class="mt" onclick="copyText(this)">${escape(m.text)}</div><div class="ma"><button class="rb" data-id="${m.id}" data-name="${escape(m.user)}">💬 Reply</button></div></div>`;div.querySelector('.rb').onclick=e=>{e.stopPropagation();replyTo=m.id;replyName=m.user;document.getElementById('reply_to').value=replyTo;document.getElementById('replyIndicator').style.display='flex';document.getElementById('replyInfoText').innerText='Replying to '+replyName;document.getElementById('msg_input').focus()};document.getElementById('msgContainer').appendChild(div);if(autoScroll)document.getElementById('msgContainer').scrollTop=1e9;if(notif&&m.user!==user&&Notification.permission==='granted')new Notification(`💬 ${m.user}`,{body:m.text.length>60?m.text.slice(0,57)+'...':m.text,icon:'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="%23a78bfa"%3E%3Cpath d="M20 2H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h4l4 4 4-4h4c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2z"%3E%3C/path%3E%3C/svg%3E'})}
async function poll(){if(sending)return;try{let r=await fetch(`/api/msg_poll?since=${lastMsgId}`);let d=await r.json();if(d.messages&&d.messages.length){for(let m of d.messages)appendMsg(m);lastMsgId=Math.max(...d.messages.map(m=>m.id));document.querySelector('.stat:last-child').innerHTML='💬 '+d.total}}catch(e){}}
async function updateStats(){try{let r=await fetch('/api/stats');let s=await r.json();let st=document.querySelectorAll('.stat');st[0].innerHTML='🌡️ '+s.temp;st[1].innerHTML='💧 '+s.hum;st[2].innerHTML='⏱️ '+s.uptime;st[3].innerHTML='💬 '+s.msg_count}catch(e){}}
async function clearChat(){let p=prompt('Admin password:');if(!p)return;let r=await fetch(`/api/clear_msgs?pass=${encodeURIComponent(p)}`);let d=await r.json();if(d.success){document.getElementById('msgContainer').innerHTML='';lastMsgId=0;toast('Chat cleared')}else toast('Wrong password')}
function init(){updateTimestamps();setInterval(updateTimestamps,6e4);setInterval(poll,3000);setInterval(updateStats,5000);updateStats();let btn=document.getElementById('notifyBtn');if('Notification' in window){let pref=localStorage.getItem('notif');if(pref==='true'&&Notification.permission==='granted'){notif=true;btn.innerText='🔕 ON'}else btn.innerText='🔔 Enable';btn.onclick=()=>{if(notif){notif=false;localStorage.setItem('notif','false');btn.innerText='🔔 Enable';toast('Notif OFF')}else{if(Notification.permission==='granted'){notif=true;localStorage.setItem('notif','true');btn.innerText='🔕 ON';toast('Notif ON')}else if(Notification.permission==='default'){Notification.requestPermission().then(p=>{if(p==='granted'){notif=true;localStorage.setItem('notif','true');btn.innerText='🔕 ON';toast('Notif enabled')}else toast('Permission denied')})}else toast('Blocked by browser')}}}else btn.style.display='none';let input=document.getElementById('msg_input');let counter=document.getElementById('charCounter');input.addEventListener('input',function(){let l=this.value.length;counter.innerText=l+'/'+MAXL;if(l>MAXL*0.9)counter.classList.add('danger');else counter.classList.remove('danger')});input.dispatchEvent(new Event('input'));document.getElementById('msgForm').onsubmit=async(e)=>{e.preventDefault();if(sending||!user)return;let msg=input.value.trim();if(!msg)return toast('Empty message');if(msg.length>MAXL)return toast(`Max ${MAXL} chars`);sending=true;let btn=document.querySelector('.send-button');let old=btn.innerText;btn.disabled=true;btn.innerText='⏳';try{let r=await fetch(`/send?name=${encodeURIComponent(user)}&msg=${encodeURIComponent(msg)}&reply=${replyTo}&ajax=1`);let d=await r.json();if(d.success){let fake={id:d.id,user:user,text:msg,reply:replyTo,reply_user:replyName,timestamp:Math.floor(Date.now()/1000)};appendMsg(fake);lastMsgId=d.id;input.value='';clearReply();counter.innerText='0/'+MAXL;document.querySelector('.stat:last-child').innerHTML='💬 '+d.total}else toast('Send error')}catch(e){toast('Network error')}finally{sending=false;btn.disabled=false;btn.innerText=old;input.focus()}}}
window.onload=()=>{let u=localStorage.getItem('user');if(u){user=u;document.getElementById('loginOverlay').style.display='none';document.getElementById('appMain').style.display='flex';fixPad();init()}else{document.getElementById('loginOverlay').style.display='flex';document.getElementById('appMain').style.display='none';document.getElementById('loginName').focus()}window.addEventListener('resize',fixPad)};
</script></body></html>'''

    return html_str.encode('utf-8').replace(b'\n', b'\r\n')

# ========== API HANDLERS ==========
def api_stats_handler():
    t, h, u, c = get_system_stats()
    return '{"temp":"%s","hum":"%s","uptime":"%s","msg_count":%d}' % (t, h, u, c)

def download_messages():
    try:
        with open("messages.txt", "rb") as f:
            return f.read()
    except:
        return b"No messages"

def download_temp_log():
    try:
        with open(TEMP_LOG_FILE, "rb") as f:
            return f.read()
    except:
        return b"No temp log"

# ========== UART / ESP8266 ==========
def send_cmd(cmd, expect, timeout=5000):
    if uart is None: return False
    while uart.any(): uart.read()
    uart.write(cmd + b'\r\n')
    start = time.ticks_ms()
    while time.ticks_ms() - start < timeout:
        if uart.any():
            line = uart.readline()
            if line and expect in line:
                return True
    return False

def wait_prompt(timeout=2000):
    start = time.ticks_ms()
    while time.ticks_ms() - start < timeout:
        if uart.any() and uart.read(1) == b'>':
            return True
    return False

def send_resp(conn, data, large=False):
    if large:
        chunk = 1400
        off = 0
        while off < len(data):
            uart.write(b'AT+CIPSEND=' + str(conn).encode() + b',' + str(min(chunk, len(data)-off)).encode() + b'\r\n')
            if not wait_prompt(2000): return False
            uart.write(data[off:off+chunk])
            off += chunk
            time.sleep(0.05)
            start = time.ticks_ms()
            ok = False
            while time.ticks_ms() - start < 2000:
                if uart.any() and b'OK' in uart.readline():
                    ok = True
                    break
            if not ok: return False
        return True
    else:
        uart.write(b'AT+CIPSEND=' + str(conn).encode() + b',' + str(len(data)).encode() + b'\r\n')
        if not wait_prompt(2000): return False
        uart.write(data)
        time.sleep(0.05)
        start = time.ticks_ms()
        while time.ticks_ms() - start < 2000:
            if uart.any() and b'OK' in uart.readline():
                return True
        return False

def handle_admin(username, text):
    global next_id
    if not text.startswith("admin:"): return False, None
    parts = text[6:].strip().split()
    if not parts: return True, ("Error", "Usage: admin:cmd [pass]")
    cmd = parts[0].lower()
    args = parts[1:]
    if cmd == "help":
        return True, ("System", "Commands: restart, info, clearlogs, clear")
    if cmd == "info":
        t,h,u,c = get_system_stats()
        return True, ("System", f"Temp:{t} Hum:{h} Up:{u} Msgs:{c} Mem:{gc.mem_free()}")
    if not args or args[0] != ADMIN_PASS:
        return True, ("System", "Admin password required")
    if cmd == "restart":
        add_message("System", "Restarting...")
        time.sleep(2)
        machine.reset()
    elif cmd == "clearlogs":
        try: os.remove(TEMP_LOG_FILE); return True, ("System", "Temp logs cleared")
        except: return True, ("System", "No log file")
    elif cmd == "clear":
        try: os.remove("messages.txt")
        except: pass
        messages.clear()
        next_id = 1
        add_message("System", "Chat cleared by admin")
        return True, None
    else:
        return True, ("System", f"Unknown command: {cmd}")

# ========== MAIN INIT ==========
print("HIVE Lite starting")
load_messages()
if not messages:
    add_message("System", f"Welcome to HIVE {VERSION} Lite! 🚀", 0)

try:
    uart = machine.UART(1, 115200, tx=machine.Pin(4), rx=machine.Pin(5))
except Exception as e:
    system_error("UART init fail", e)
    uart = None

if uart:
    send_cmd(b'AT+RST', b'ready', 5000)
    time.sleep(2)
    send_cmd(b'AT+CWMODE=1', b'OK')
    if not send_cmd(b'AT+CWJAP="' + SSID.encode() + b'","' + PASSWORD.encode() + b'"', b'OK', 20000):
        system_error("WiFi failed")
        uart = None
    else:
        send_cmd(b'AT+CIPMUX=1', b'OK')
        send_cmd(b'AT+CIPSERVER=1,' + str(PORT).encode(), b'OK')
        print("Server ready")

last_temp_log = time.ticks_ms()

# ========== MAIN LOOP ==========
while True:
    if wdt: wdt.feed()
    if time.ticks_diff(time.ticks_ms(), last_temp_log) >= TEMP_LOG_INTERVAL_MS:
        log_all_temps()
        last_temp_log = time.ticks_ms()
    if uart and uart.any():
        line = uart.readline()
        if line and line.startswith(b'+IPD'):
            conn_id = None
            try:
                while uart.any(): uart.read()
                parts = line.split(b',', 2)
                if len(parts) < 3: continue
                conn_id = int(parts[1].strip())
                remaining = parts[2]
                colon = remaining.find(b':')
                if colon == -1: continue
                data_len = int(remaining[:colon].strip())
                data = remaining[colon+1:]
                if len(data) < data_len:
                    need = min(data_len - len(data), 2048)
                    if need: data += uart.read(need) or b''
                req = data
                req_lines = req.split(b'\r\n')
                if not req_lines: continue
                first = req_lines[0].split(b' ')
                if len(first) < 2: continue
                method = first[0]
                path = first[1].split(b'?')[0]
                query = first[1].split(b'?')[1] if b'?' in first[1] else b''
                # ----- ROUTES -----
                if method == b'GET' and path == b'/api/stats':
                    body = api_stats_handler().encode()
                    send_resp(conn_id, b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n' + body)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()
                    continue
                if method == b'GET' and path == b'/':
                    html = html_page()
                    headers = b'HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: ' + str(len(html)).encode() + b'\r\nConnection: close\r\n\r\n'
                    send_resp(conn_id, headers + html, large=True)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()
                    continue
                if method == b'GET' and path == b'/send':
                    params = {}
                    for pair in query.split(b'&'):
                        if b'=' in pair:
                            k, v = pair.split(b'=', 1)
                            key = k.decode()
                            v = v.replace(b'+', b' ')
                            val = percent_decode(v).decode('utf-8', 'ignore')
                            params[key] = val
                    msg = params.get('msg', '')[:MAX_MSG_CHARS]
                    name = params.get('name', 'Anonymous')[:20]
                    reply = int(params.get('reply', '0'))
                    ajax = params.get('ajax', '') == '1'
                    if msg.startswith("admin:"):
                        handled, resp_tup = handle_admin(name, msg)
                        if handled and resp_tup:
                            add_message(resp_tup[0], resp_tup[1])
                        send_resp(conn_id, b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{"success":true,"id":0,"total":' + str(len(messages)).encode() + b'}')
                        uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                        conn_id = None
                        continue
                    if msg:
                        mid, _ = add_message(name, msg, reply)
                    else:
                        mid = None
                    if ajax and mid:
                        body = b'{"success":true,"id":%d,"total":%d}' % (mid, len(messages))
                        send_resp(conn_id, b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n' + body)
                    else:
                        send_resp(conn_id, b'HTTP/1.1 302 Found\r\nLocation: /\r\nConnection: close\r\n\r\n')
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()
                    continue
                if method == b'GET' and path == b'/download_msgs':
                    cont = download_messages()
                    send_resp(conn_id, b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename="messages.txt"\r\nContent-Length: ' + str(len(cont)).encode() + b'\r\nConnection: close\r\n\r\n' + cont, large=True)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()
                    continue
                if method == b'GET' and path == b'/download_temps':
                    cont = download_temp_log()
                    send_resp(conn_id, b'HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Disposition: attachment; filename="temp_log.txt"\r\nContent-Length: ' + str(len(cont)).encode() + b'\r\nConnection: close\r\n\r\n' + cont, large=True)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()
                    continue
                if method == b'GET' and path == b'/api/msg_poll':
                    since = 0
                    for pair in query.split(b'&'):
                        if pair.startswith(b'since='):
                            try: since = int(pair.split(b'=')[1])
                            except: pass
                    new_msgs = []
                    for m in messages:
                        p = m.split(b'|')
                        if len(p) < 6: continue
                        mid = int(p[0])
                        if mid <= since: continue
                        new_msgs.append({
                            "id": mid,
                            "user": p[2].decode('utf-8','replace'),
                            "text": p[3].decode('utf-8','replace'),
                            "reply": int(p[4]),
                            "reply_user": get_message_by_id(int(p[4])) or "",
                            "timestamp": int(p[5])
                        })
                    body = json.dumps({"total": len(messages), "messages": new_msgs}).encode()
                    send_resp(conn_id, b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n' + body)
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()
                    continue
                if method == b'GET' and path == b'/api/clear_msgs':
                    pwd = b''
                    for pair in query.split(b'&'):
                        if pair.startswith(b'pass='):
                            pwd = pair.split(b'=')[1]
                    if pwd.decode() == ADMIN_PASS:
                        try: os.remove("messages.txt")
                        except: pass
                        messages.clear()
                        next_id = 1
                        add_message("System", "Chat cleared")
                        send_resp(conn_id, b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{"success":true}')
                    else:
                        send_resp(conn_id, b'HTTP/1.1 403 Forbidden\r\nContent-Type: application/json\r\nConnection: close\r\n\r\n{"success":false}')
                    uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    conn_id = None
                    gc.collect()
                    continue
                # 404 for others
                send_resp(conn_id, b'HTTP/1.1 404 Not Found\r\nConnection: close\r\n\r\n')
                uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                conn_id = None
                gc.collect()
            except Exception as e:
                system_error("Request error", e)
                if conn_id is not None:
                    try: uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    except: pass
                gc.collect()
            finally:
                if conn_id is not None:
                    try: uart.write(b'AT+CIPCLOSE=' + str(conn_id).encode() + b'\r\n')
                    except: pass
    time.sleep(0.05)
    gc.collect()