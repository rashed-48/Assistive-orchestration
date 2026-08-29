# Opens Mosquitto to the local network so ESP32 boards can connect.
#
# RUN AS ADMINISTRATOR.
#
# WARNING: allow_anonymous lets anyone on your Wi-Fi command the
# devices. Fine on a lab bench. Add a password file before this
# controls anything real.

$ErrorActionPreference = "Stop"

$dir  = "C:\Program Files\mosquitto"
$conf = Join-Path $dir "mosquitto.conf"
$bin  = Join-Path $dir "mosquitto.exe"

# The config MUST be plain ASCII with no byte-order mark. Mosquitto
# fails to parse a BOM and the service then refuses to start, which
# looks exactly like "nothing is listening".
$text = @"
# Assistive Orchestration - listen on every interface so the ESP32
# nodes can reach the broker. Loopback-only is the default and
# silently blocks every board.
listener 1883 0.0.0.0
allow_anonymous true

# Log every connect and disconnect with a reason. Without this a node
# that keeps dropping looks identical to one that never arrived, and
# the board's own serial output cannot tell you which side gave up.
log_dest file C:\Program Files\mosquitto\mosquitto.log
log_type all
connection_messages true
log_timestamp true
"@

[System.IO.File]::WriteAllText($conf, $text, (New-Object System.Text.UTF8Encoding($false)))

$firstBytes = [System.IO.File]::ReadAllBytes($conf)[0..2] -join ","
if ($firstBytes -eq "239,187,191") {
    Write-Host "ERROR: the file still has a BOM. Mosquitto will not start." -ForegroundColor Red
    exit 1
}
Write-Host "wrote $conf (no BOM)" -ForegroundColor Green

# Mosquitto has no config-test flag, so the service start IS the test.
# If it fails, the foreground run below prints the real reason.
Restart-Service mosquitto
Start-Sleep -Seconds 2

$svc = Get-Service mosquitto
Write-Host "service: $($svc.Status)" -ForegroundColor Cyan

if ($svc.Status -ne "Running") {
    Write-Host "`nThe service did not start. Running it in the foreground to" -ForegroundColor Yellow
    Write-Host "show the actual error (Ctrl+C to stop):`n" -ForegroundColor Yellow
    & $bin -c $conf -v
    exit 1
}

$listening = netstat -an | Select-String "LISTENING" | Select-String ":1883"
Write-Host "`nListeners:" -ForegroundColor Cyan
$listening

if ($listening -match "0\.0\.0\.0:1883") {
    Write-Host "`nOK - the broker is open to the network." -ForegroundColor Green
} else {
    Write-Host "`nStill loopback only. The config did not take effect." -ForegroundColor Red
    exit 1
}

if (-not (Get-NetFirewallRule -DisplayName "MQTT 1883" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "MQTT 1883" -Direction Inbound `
        -Protocol TCP -LocalPort 1883 -Action Allow | Out-Null
    Write-Host "firewall rule added" -ForegroundColor Green
}

$ip = (Get-NetIPAddress -AddressFamily IPv4 |
       Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } |
       Select-Object -First 1).IPAddress
Write-Host "`nPut this in the firmware as MQTT_HOST:  $ip" -ForegroundColor Cyan
