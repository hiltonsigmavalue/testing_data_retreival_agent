param(
    [int]$Port = 8000,
    [switch]$Reload
)

$python = Join-Path $PSScriptRoot "venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "python"
}

$localIp = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
    Where-Object {
        $_.IPAddress -notlike "127.*" -and
        $_.IPAddress -notlike "169.254*" -and
        $_.InterfaceAlias -notmatch "Loopback|vEthernet"
    } |
    Select-Object -First 1 -ExpandProperty IPAddress

Write-Host "Starting Real Estate SQL Agent on all network interfaces..."
Write-Host "This computer: http://127.0.0.1:$Port/"
if ($localIp) {
    Write-Host "Other devices on this Wi-Fi/LAN: http://${localIp}:$Port/"
} else {
    Write-Host "Run ipconfig to find this computer's IPv4 address for LAN access."
}

$arguments = @("-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "$Port")
if ($Reload) {
    $arguments += "--reload"
}

& $python @arguments
