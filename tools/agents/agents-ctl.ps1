# לוח המתגים של הסוכנים — הדלקה/כיבוי לכל סוכן בנפרד, כולל קלוד.
#
# שתי משפחות של מתגים:
#   ‏GitHub (שורדים כל מכונה): ‏workflows — נשלטים ב-gh workflow enable/disable
#   מקומיים (התחנה הזאת): קובץ מצב שהרץ המתוזמן והלולאה של קלוד קוראים
#
# הקובץ: ‏%USERPROFILE%\.otogit-agents.json — ‏false פירושו כבוי.
# קלוד בודק אותו בכל איטרציה של הלולאה שלו; ‏claude=false עוצר אותה.
#
# שימוש:
#   tools\agents\agents-ctl.ps1 list
#   tools\agents\agents-ctl.ps1 off grok
#   tools\agents\agents-ctl.ps1 on  review
#   tools\agents\agents-ctl.ps1 off all-local
param(
    [Parameter(Mandatory=$true)][ValidateSet("list","on","off")] [string]$Action,
    [string]$Agent = ""
)
$ErrorActionPreference = "Stop"
$Repo = $env:OTOGIT_REPO
if (-not $Repo) { throw "OTOGIT_REPO אינו מוגדר — הכלי אינו מנחש ריפו" }
$StateFile = Join-Path $env:USERPROFILE ".otogit-agents.json"

# סוכני GitHub → שם ה-workflow; סוכנים מקומיים → מפתח בקובץ המצב
$GithubAgents = @{ review = "agent-review"; daily = "agent-daily"; idea = "idea-to-issue"; nightly = "nightly" }
$LocalAgents  = @("claude", "grok", "codex", "gemini-local", "runner")

function Get-State {
    if (Test-Path $StateFile) { Get-Content $StateFile -Raw | ConvertFrom-Json }
    else { [pscustomobject]@{ claude=$true; grok=$true; codex=$true; "gemini-local"=$true; runner=$true } }
}
function Save-State($s) {
    # כתיבה אטומית-למחצה: לקובץ זמני ואז החלפה, כדי שקורא לא יתפוס חצי קובץ
    $tmp = "$StateFile.tmp"
    $s | ConvertTo-Json | Out-File $tmp -Encoding utf8
    Move-Item -Force $tmp $StateFile
    # קריאה-בחזרה — הפקודה שהצליחה אינה ראיה שהמצב נשמר (עיקרון 5)
    $back = Get-Content $StateFile -Raw | ConvertFrom-Json
    if ($null -eq $back) { throw "קובץ המצב לא נקרא בחזרה" }
}

switch ($Action) {
    "list" {
        "== סוכני GitHub (שורדים כיבוי של המחשב) =="
        foreach ($k in $GithubAgents.Keys) {
            $wf = $GithubAgents[$k]
            $st = gh api "repos/$Repo/actions/workflows" --jq ".workflows[] | select(.name==`"$wf`") | .state" 2>$null
            if (-not $st) { $st = "לא קיים עדיין (ממתין למיזוג)" }
            "{0,-14} {1}" -f $k, $st
        }
        ""
        "== סוכנים מקומיים (התחנה הזאת; claude = הלולאה שלו) =="
        $s = Get-State
        foreach ($k in $LocalAgents) {
            $v = $s.PSObject.Properties[$k]
            $on = if ($null -eq $v -or $v.Value) { "on" } else { "OFF" }
            $cd = $s.PSObject.Properties["cooldown_$k"]
            if ($null -ne $cd -and $cd.Value.until -and [datetime]::Parse($cd.Value.until).ToUniversalTime() -gt [datetime]::UtcNow) {
                $on = "❄️ מקורר עד $($cd.Value.until) — $($cd.Value.reason); יידלק מעצמו"
            }
            "{0,-14} {1}" -f $k, $on
        }
    }
    default {
        if (-not $Agent) { throw "חסר שם סוכן. ‏list כדי לראות את הרשימה." }
        $enable = ($Action -eq "on")
        if ($Agent -eq "all-local") {
            $s = Get-State
            foreach ($k in $LocalAgents) {
                if ($null -eq $s.PSObject.Properties[$k]) { $s | Add-Member -NotePropertyName $k -NotePropertyValue $enable }
                else { $s.PSObject.Properties[$k].Value = $enable }
            }
            Save-State $s
            "כל הסוכנים המקומיים: $Action"
        } elseif ($GithubAgents.ContainsKey($Agent)) {
            $wf = $GithubAgents[$Agent]
            if ($enable) { gh workflow enable $wf --repo $Repo } else { gh workflow disable $wf --repo $Repo }
            $st = gh api "repos/$Repo/actions/workflows" --jq ".workflows[] | select(.name==`"$wf`") | .state"
            "‏$Agent ($wf) → $st"
        } elseif ($LocalAgents -contains $Agent) {
            $s = Get-State
            if ($null -eq $s.PSObject.Properties[$Agent]) { $s | Add-Member -NotePropertyName $Agent -NotePropertyValue $enable }
            else { $s.PSObject.Properties[$Agent].Value = $enable }
            Save-State $s
            $v = (Get-Content $StateFile -Raw | ConvertFrom-Json).PSObject.Properties[$Agent].Value
            "‏$Agent → $(if ($v) {'on'} else {'OFF'})  (נקרא בחזרה מהקובץ)"
        } else {
            throw "סוכן לא מוכר: $Agent. האפשרויות: $($GithubAgents.Keys -join ', '), $($LocalAgents -join ', '), all-local"
        }
    }
}
