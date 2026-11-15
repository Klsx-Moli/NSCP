param(
    [Parameter(Mandatory = $true)][string]$RunDir,
    [Parameter(Mandatory = $true)][ValidateSet("generation", "judge")][string]$Stage,
    [string]$BaseUrl = $(if ($env:NPSC_API_BASE_URL) { $env:NPSC_API_BASE_URL } else { "https://api.commandcode.ai/provider/v1" }),
    [int]$Throttle = 4,
    [int]$TimeoutSec = 300,
    [int]$Retries = 2
)

$ErrorActionPreference = "Stop"
$key = if ($env:NPSC_API_KEY) { $env:NPSC_API_KEY } else { $env:COMMANDCODE_API_KEY }
if (-not $key) { throw "Set NPSC_API_KEY or COMMANDCODE_API_KEY before running this script." }

$requestDir = Join-Path $RunDir "requests\$Stage"
$responseDir = Join-Path $RunDir "responses\$Stage"
if (-not (Test-Path -LiteralPath $requestDir)) { throw "Request directory not found: $requestDir" }
New-Item -ItemType Directory -Force -Path $responseDir | Out-Null

$requests = Get-ChildItem -LiteralPath $requestDir -Filter "*.json" | Where-Object {
    -not (Test-Path -LiteralPath (Join-Path $responseDir ($_.BaseName + ".response.json")))
}

Write-Output ("[ab-eval] stage={0} pending={1} throttle={2}" -f $Stage, $requests.Count, $Throttle)
if ($requests.Count -eq 0) {
    Write-Output "[ab-eval] nothing to do"
    exit 0
}

$results = $requests | ForEach-Object -ThrottleLimit $Throttle -Parallel {
    $requestPath = $_.FullName
    $requestId = $_.BaseName
    $responsePath = Join-Path $using:responseDir ($requestId + ".response.json")
    $request = Get-Content -LiteralPath $requestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $endpoint = if ($request.endpoint) { $request.endpoint } else { "/chat/completions" }
    $url = $using:BaseUrl.TrimEnd('/') + $endpoint
    $headers = @{
        Authorization = "Bearer $using:key"
        "Content-Type" = "application/json"
    }
    $body = $request.body | ConvertTo-Json -Depth 30 -Compress
    $attempt = 0
    $lastError = $null
    while ($attempt -le $using:Retries) {
        $attempt++
        $sw = [System.Diagnostics.Stopwatch]::StartNew()
        try {
            $resp = Invoke-WebRequest -Uri $url -Method Post -Headers $headers -Body $body -TimeoutSec $using:TimeoutSec -SkipHttpErrorCheck
            $sw.Stop()
            $status = [int]$resp.StatusCode
            $parsed = $null
            try { $parsed = $resp.Content | ConvertFrom-Json } catch { $parsed = $resp.Content }
            $payload = @{
                ok = ($status -ge 200 -and $status -lt 300)
                status = $status
                elapsed_ms = $sw.ElapsedMilliseconds
                attempts = $attempt
                response = $parsed
            }
            if (-not $payload.ok -and $parsed -is [string]) { $payload.error = $parsed }
            $payload | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $responsePath -Encoding UTF8
            if ($payload.ok) {
                return ("[ok] {0} status={1} {2}ms" -f $requestId, $status, $sw.ElapsedMilliseconds)
            }
            $lastError = "status=$status"
            if ($status -eq 429) {
                Start-Sleep -Seconds ([Math]::Min(30, 5 * $attempt))
                continue
            }
            return ("[fail] {0} status={1}" -f $requestId, $status)
        } catch {
            $sw.Stop()
            $lastError = $_.Exception.Message
            Start-Sleep -Seconds ([Math]::Min(20, 3 * $attempt))
        }
    }
    $failure = @{
        ok = $false
        status = $null
        elapsed_ms = 0
        attempts = $attempt
        error = $lastError
    }
    $failure | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $responsePath -Encoding UTF8
    return ("[fail] {0} {1}" -f $requestId, $lastError)
}

$results | ForEach-Object { Write-Output $_ }
$done = (Get-ChildItem -LiteralPath $responseDir -Filter "*.response.json" -ErrorAction SilentlyContinue).Count
Write-Output ("[ab-eval] stage={0} responses_in_dir={1}" -f $Stage, $done)
