# שכבת המכסות — סוכן שנגמרה לו המכסה מכבה את עצמו ונדלק כשהיא מתאפסת.
#
# ההפרדה החשובה: ‏enabled הוא מתג **ידני** של בעל הריפו; ‏cooldown_until הוא
# השתקה **אוטומטית** זמנית. סוכן זמין רק כששניהם מתירים. הקירור פג
# מעצמו — אין צורך "להדליק" אחרי איפוס מכסה, הזמן עושה את זה.
#
# איפוסים ידועים: ‏Gemini חינמי — יומי, חצות שעון האוקיינוס השקט
# (‏10:00 בישראל בקיץ); ‏Codex — חלון 5 שעות + שבועי; ‏Grok — לא פורסם,
# ולכן קירור שמרני של 6 שעות וניסיון-גישוש.
$script:StateFile = Join-Path $env:USERPROFILE ".otogit-agents.json"

function Read-AgentState {
    if (Test-Path $script:StateFile) { Get-Content $script:StateFile -Raw | ConvertFrom-Json }
    else { [pscustomobject]@{} }
}
function Save-AgentState($s) {
    $tmp = "$script:StateFile.tmp"
    $s | ConvertTo-Json -Depth 5 | Out-File $tmp -Encoding utf8
    Move-Item -Force $tmp $script:StateFile
    if ($null -eq (Get-Content $script:StateFile -Raw | ConvertFrom-Json)) { throw "קובץ המצב לא נקרא בחזרה" }
}
# ‏PSUseShouldProcessForStateChangingFunctions מושתק כאן במכוון:
# הפונקציה כותבת קובץ מצב מקומי אחד של הכלי עצמו, לא משנה מצב מערכת.
# ‏-WhatIf/-Confirm על קירור סוכן היה מוסיף שאלה למסלול שרץ אוטומטית.
function Set-AgentCooldown {
    [Diagnostics.CodeAnalysis.SuppressMessageAttribute(
        'PSUseShouldProcessForStateChangingFunctions', '')]
    param([string]$Agent, [datetime]$UntilUtc, [string]$Reason)
    $s = Read-AgentState
    $key = "cooldown_$Agent"
    $val = [pscustomobject]@{ until = $UntilUtc.ToString("o"); reason = $Reason }
    if ($null -eq $s.PSObject.Properties[$key]) { $s | Add-Member -NotePropertyName $key -NotePropertyValue $val }
    else { $s.PSObject.Properties[$key].Value = $val }
    Save-AgentState $s
    "‏$Agent מקורר עד $($UntilUtc.ToString('o')) — $Reason"
}
function Test-AgentAvailable([string]$Agent) {
    $s = Read-AgentState
    $en = $s.PSObject.Properties[$Agent]
    if ($null -ne $en -and -not $en.Value) { return $false }          # כבוי ידנית
    $cd = $s.PSObject.Properties["cooldown_$Agent"]
    if ($null -ne $cd -and $cd.Value.until) {
        if ([datetime]::Parse($cd.Value.until).ToUniversalTime() -gt [datetime]::UtcNow) { return $false }
    }
    return $true                                                       # הקירור פג = נדלק מעצמו
}
function Get-NextGeminiReset {
    # חצות באוקיינוס השקט = איפוס היומי של גוגל. מחושב, לא מנוחש.
    $pt = [TimeZoneInfo]::FindSystemTimeZoneById("Pacific Standard Time")
    $nowPt = [TimeZoneInfo]::ConvertTimeFromUtc([datetime]::UtcNow, $pt)
    [TimeZoneInfo]::ConvertTimeToUtc($nowPt.Date.AddDays(1), $pt)
}
function Test-QuotaError([string]$Text, [string]$Agent) {
    # זיהוי מכסה לפי הודעות אמיתיות: ‏429/RESOURCE_EXHAUSTED של גוגל,
    # ‏usage-limit של OpenAI/xAI. מחזיר זמן קירור מוצע, או $null.
    if ($Text -match 'RESOURCE_EXHAUSTED|"code":\s*429|quota.*exceed|rate.?limit') {
        switch ($Agent) {
            { $_ -like "gemini*" } { return Get-NextGeminiReset }
            "codex" { return [datetime]::UtcNow.AddHours(5) }   # חלון 5 השעות
            default { return [datetime]::UtcNow.AddHours(6) }   # שמרני + גישוש
        }
    }
    if ($Text -match 'weekly.?(usage|limit)|usage.?limit.*reached') { return [datetime]::UtcNow.AddDays(1) }
    return $null
}
