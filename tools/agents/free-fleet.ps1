# מרים את ה-proxy של הצי החינמי — LiteLLM על 127.0.0.1:4000.
#
# ‏.env חסר = עצירה קולנית. ‏proxy שעולה בלי מפתחות נראה תקין ונכשל
# על כל קריאה — בדיוק סוג השקט שעיקרון 5 אוסר.
#
#   tools/agents/free-fleet.ps1            # מרים בחלון הנוכחי
#   tools/agents/free-fleet.ps1 -Check     # רק בודק מוכנות, לא מרים
param([switch]$Check)
$ErrorActionPreference = 'Stop'

$root = git rev-parse --show-toplevel
$envFile = Join-Path $root ".env"
$config = Join-Path $root "tools/agents/litellm.yaml"

if (-not (Test-Path $envFile)) {
    Write-Error "אין $envFile — הצי החינמי לא עולה בלי מפתחות. ‏.env.example מפרט מה צריך."
    exit 1
}
if (-not (Test-Path $config)) { Write-Error "אין $config"; exit 1 }

# טעינת .env: שורות KEY=VALUE בלבד; שורות ריקות והערות מדולגות.
$loaded = 0
foreach ($line in Get-Content $envFile -Encoding utf8) {
    if ($line -match '^\s*(#|$)') { continue }
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
        $name, $val = $Matches[1], $Matches[2].Trim()
        if ($val) { Set-Item -Path "env:$name" -Value $val; $loaded++ }
    }
}
if ($loaded -eq 0) {
    Write-Error "‏.env קיים אבל לא נטען ממנו אף מפתח — קובץ ריק אינו קונפיגורציה."
    exit 1
}
"נטענו $loaded משתנים מ-.env"

# אילו מודלים בקונפיג חסרי מפתח? מדווחים לפני העלייה, לא מגלים בקריאה.
$missing = @()
foreach ($m in (Select-String -Path $config -Pattern 'os\.environ/(\w+)' -AllMatches).Matches) {
    $name = $m.Groups[1].Value
    if (-not (Test-Path "env:$name")) { $missing += $name }
}
if ($missing) {
    "⚠ מפתחות חסרים (המודלים שלהם לא יעבדו): $($missing | Sort-Object -Unique)"
}

if ($Check) {
    "מוכנות: config תקין, $loaded משתנים נטענו."

    # השכבה המקומית (‏routing.order[0]) — נבדקת בקריאה אמיתית ולא
    # לפי נוכחות בקונפיג. ‏ollama כבוי נראה בדיוק כמו ollama עובד עד
    # שמישהו שולח בקשה, ואז הכול נופל ל-general בשקט — כלומר הצי
    # מדווח "מוכן" ומשלם על מה שהיה מקומי. נאמר בקול, לא נבלע.
    $localOk = $false
    try {
        $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" `
            -TimeoutSec 5 -ErrorAction Stop
        $names = @($tags.models | ForEach-Object { $_.name })
        $want = @((Select-String -Path $config -Pattern 'ollama_chat/(\S+)' `
            -AllMatches).Matches | ForEach-Object { $_.Groups[1].Value } |
            Sort-Object -Unique)
        $absent = @($want | Where-Object { $names -notcontains $_ })
        if ($absent) {
            Write-Warning "‏ollama עונה אך חסרים מודלים שהקונפיג מבקש: $($absent -join ', ') — הרץ ollama pull"
        } else {
            "שכבה מקומית: ‏ollama עונה, $($want.Count) מודלים מבוקשים נמצאו."
            $localOk = $true
        }
    } catch {
        Write-Warning "‏ollama אינו עונה על 127.0.0.1:11434 — השכבה הראשונה ב-routing.order מתה, וכל מה שיועד לה ייפול ל-general."
    }
    if (-not $localOk) { "‏(הצי עדיין שמיש — אבל לא כמקומי-קודם.)" }

    # ניטור סחף מודלים: ספק חינמי מחליף מודלים בלי לשאול. נמדד ביום
    # החיבור — פעמיים. יציאה לא-אפס כאן היא התראה, לא כישלון עלייה.
    $env:PYTHONIOENCODING = 'utf-8'
    python (Join-Path $root "tools/agents/model-watch.py")
    if ($LASTEXITCODE -ne 0) { Write-Warning "מודלים נעלמו מהקטלוג — ראה למעלה"; exit 2 }
    exit 0
}

# ‏litellm פותח את הקונפיג בקידוד ברירת המחדל — cp1252 בווינדוס —
# והעברית שבו מפילה אותו ב-UnicodeDecodeError. נמדד, לא שוער.
$env:PYTHONUTF8 = '1'

$exe = Join-Path $env:USERPROFILE ".local/bin/litellm.exe"
if (-not (Test-Path $exe)) { $exe = "litellm" }
& $exe --config $config --host 127.0.0.1 --port 4000
