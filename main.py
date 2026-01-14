import network
import socket
import time
import json
from machine import Pin

# ---------------- CONFIG ----------------
WIFI_SSID = "Sweet Home"
WIFI_PASS = "**********"
SCAN_INTERVAL = 5
RSSI_SPIKE = 20

# ---------------- STATUS LED -------------
led = Pin("LED", Pin.OUT)
led.on()

# ---------------- WIFI -------------------
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect(WIFI_SSID, WIFI_PASS)

while not wlan.isconnected():
    time.sleep(0.2)

ip = wlan.ifconfig()[0]
print("WIDS running at http://" + ip)

# ---------------- STATE ------------------
baseline = {}
alerts = []

def log_alert(msg):
    alerts.append({"t": time.time(), "msg": msg})
    if len(alerts) > 50:
        alerts.pop(0)

def scan_wids():
    seen = {}
    channels = {}
    nets = wlan.scan()

    for n in nets:
        ssid = n[0].decode("utf-8", "ignore")
        bssid = ":".join("%02x" % b for b in n[1])
        ch = n[2]
        rssi = n[3]

        seen.setdefault(ssid, []).append((bssid, rssi))
        channels.setdefault(ch, []).append(rssi)

        key = ssid + bssid
        if key in baseline and abs(rssi - baseline[key]) > RSSI_SPIKE:
            log_alert(f"RSSI anomaly: {ssid}")
        baseline[key] = rssi

    for ssid in seen:
        if len(seen[ssid]) > 1:
            log_alert(f"Evil Twin suspected: {ssid}")

    for ch in channels:
        if len(channels[ch]) > 6:
            log_alert(f"Channel flooding anomaly: ch {ch}")

    return {"channels": channels}

last_scan = {"channels": {}}
last_time = 0

# ---------------- HTML -------------------
HTML = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Pico W Wi-Fi IDS</title>
<style>
body {{
  margin:0;
  font-family: monospace;
  background:#0b0f1a;
  color:#66ffcc;
}}
#container {{
  display:flex;
  height:100vh;
}}
.panel {{
  flex:1;
  padding:12px;
  overflow-y:auto;
  border-right:1px solid #223;
}}
.panel:last-child {{
  border-right:none;
}}
.alert {{
  color:#ff5555;
  padding:2px 0;
}}
h3 {{
  margin-top:0;
}}
</style>
<script>
async function update() {{
  let s = await fetch('/scan'); s = await s.json();
  let a = await fetch('/alerts'); a = await a.json();

  let ch = '';
  for (const c in s.channels) {{
    ch += 'Channel ' + c + ': ';
    s.channels[c].forEach(() => ch += '█');
    ch += '<br>';
  }}
  document.getElementById('channels').innerHTML = ch || 'No activity';

  let al = '';
  a.forEach(x => al += '<div class="alert">⚠ ' + x.msg + '</div>');
  let ad = document.getElementById('alerts');
  ad.innerHTML = al || 'No alerts';
  ad.scrollTop = ad.scrollHeight;
}}
setInterval(update, 3000);
</script>
</head>
<body onload="update()">
<div id="container">
  <div class="panel">
    <h3>Channel Activity</h3>
    <div id="channels">Scanning…</div>
  </div>
  <div class="panel" id="alerts">
    <h3>Alerts</h3>
    Monitoring…
  </div>
</div>
</body>
</html>
"""

# ---------------- SERVER -----------------
addr = socket.getaddrinfo("0.0.0.0", 80)[0][-1]
s = socket.socket()
s.bind(addr)
s.listen(1)

while True:
    now = time.time()
    if now - last_time > SCAN_INTERVAL:
        last_scan = scan_wids()
        last_time = now

    cl, _ = s.accept()
    req = cl.recv(1024).decode()

    if "GET /scan" in req:
        cl.send("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
        cl.send(json.dumps(last_scan))
    elif "GET /alerts" in req:
        cl.send("HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n\r\n")
        cl.send(json.dumps(alerts))
    else:
        cl.send("HTTP/1.0 200 OK\r\nContent-Type: text/html\r\n\r\n")
        cl.send(HTML)

    cl.close()


