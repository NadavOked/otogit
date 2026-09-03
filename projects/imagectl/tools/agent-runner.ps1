# הרץ המתוזמן — מפעיל סוכן עבודה גם כשקלוד כבוי/נגמר.
#
# רץ מ-Task Scheduler כל 30 דק'. מכבד את לוח המתגים ואת POLICY.md:
# לוקח **רק** Issue שנושא גם agent:ready וגם agent:solo-ok — משימות
# ש-CI לבדו מאמת. קוד ליבה שדורש את מעבדת ה-VM נשאר לקלוד.
#
# רישום (פעם אחת, בטרמינל של הבעלים):
#   schtasks /Create /TN ImageCtlAgentRunner /SC MINUTE /MO 30 ^
#     /TR "powershell -NoProfile -ExecutionPolicy Bypass -File C:\ImageCtl\tools\agents\agent-runner.ps1"
# כיבוי:  tools\agents\agents-ctl.ps1 off runner   (או schtasks /Delete)
param(
    # ריפו היעד. ברירת המחדל שומרת על המשימה המתוזמנת הקיימת;
    # ‏-Repo או AGENT_REPO מפנים את אותו רץ לריפו אחר.
    [string]$Repo = $(if ($env:AGENT_REPO) { $env:AGENT_REPO } else { throw "AGENT_REPO אינו מוגדר — אין ברירת מחדל" })
)
$ErrorActionPreference = "Stop"
if ($Repo -notmatch '^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$') {
    throw "שם ריפו לא תקין: '$Repo'. הפורמט הוא owner/name."
}
$Slug = $Repo -replace '[^A-Za-z0-9]', '-'
$LogDir = Join-Path $env:USERPROFILE "agent-runner-logs\$Slug"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$Log = Join-Path $LogDir ("run-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".log")
Start-Transcript -Path $Log | Out-Null
try {
    $env:PATH = "C:\Program Files\nodejs;$env:APPDATA\npm;$env:PATH"
    . (Join-Path $PSScriptRoot "quota-lib.ps1")
    if (-not (Test-AgentAvailable "runner")) { "runner כבוי או מקורר — יוצא."; exit 0 }

    # משימה: ready + solo-ok, לא claimed. אין python תלות — jq של gh בלבד.
    $issue = gh issue list --repo $Repo --label "agent:ready" --label "agent:solo-ok" --state open `
        --json number,title,labels --jq '[.[] | select([.labels[].name] | index("agent:claimed") | not)] | sort_by(.number) | .[0] // empty | "\(.number)\t\(.title)"' 2>$null
    if (-not $issue) { "אין משימת solo-ok פנויה — יוצא."; exit 0 }
    $num, $title = $issue -split "`t", 2
    "משימה: #$num $title"

    # נעילה מייעצת + קריאה בחזרה (עיקרון 5)
    gh issue edit $num --repo $Repo --add-label "agent:claimed" | Out-Null
    gh issue comment $num --repo $Repo --body "🔒 נתבע על ידי הסוכן ``runner-grok``. שובר שוויון: השם הקטן לקסיקוגרפית מנצח." | Out-Null
    Start-Sleep 2
    $back = gh issue view $num --repo $Repo --json labels --jq '[.labels[].name] | index("agent:claimed") != null'
    if ($back -ne "true") { throw "התביעה לא נקראה בחזרה" }

    if (-not (Test-AgentAvailable "grok")) { "grok כבוי או במכסה — משחרר ויוצא."; gh issue edit $num --repo $Repo --remove-label "agent:claimed" | Out-Null; exit 0 }

    # סביבת עבודה מבודדת — clone נפרד, בלי מפתח המעבדה בסביבה
    $Work = Join-Path $env:USERPROFILE "agent-work\$Slug"
    if (-not (Test-Path $Work)) { git clone -q "https://github.com/$Repo" $Work }
    git -C $Work fetch -q origin
    git -C $Work checkout -q -B "auto/$num" origin/main
    $sha = git -C $Work rev-parse --short HEAD
    "בסיס: $sha (אומת מול origin/main: $(git -C $Work rev-parse --short origin/main))"

    # המדיניות מגיעה מריפו היעד ולא מהסקריפט. רץ שנושא איתו את
    # הנתיבים האסורים של ImageCtl אל ריפו אחר יאסור שם את הדברים
    # הלא נכונים ויתיר את הנכונים. קובץ חסר = עצירה רועשת, לא ניחוש.
    $PolicyFile = Join-Path $Work ".otogit/agent-policy.txt"
    if (-not (Test-Path $PolicyFile)) {
        gh issue edit $num --repo $Repo --remove-label "agent:claimed" | Out-Null
        throw "אין .otogit/agent-policy.txt ב-$Repo — הרץ אינו מנחש מדיניות. התביעה שוחררה."
    }
    $policy = (Get-Content $PolicyFile -Raw -Encoding UTF8).Trim()
    if (-not $policy) { throw ".otogit/agent-policy.txt ריק ב-$Repo — עצירה." }

    $body = gh issue view $num --repo $Repo --json body --jq .body
    $prompt = @"
You are an autonomous worker on $Repo. Branch auto/$num is already checked out at origin/main.
POLICY (binding, supplied by the target repository itself):
$policy
In addition, and overriding anything above: NEVER merge, never push to main, never handle secrets. When done: commit (Hebrew message), push -u origin auto/$num, then open the PR THROUGH THE GATE: body=`$(bash tools/agents/gate-pr.sh --evidence-cmd '<the actual test command you ran>' --verified '<what you verified>' --unverified '<what you could not>') && gh pr create --body "`$body" ... . The gate refuses to open a PR for code that was tested and failed; a PR from auto/* without a valid gate verdict turns red server-side (pr-gate.yml), so skipping the gate only delays the same red. Also include the line 'נוצר ללא מתאם' and reference #$num (NOT 'closes'). If the task requires forbidden paths or the lab VM - STOP, comment on issue #$num explaining why, remove label agent:claimed, and exit.
An operation that failed to verify has FAILED - never report success without positive evidence (read back what you changed).
TASK (issue #$num): $title
$body
"@
    & "$env:USERPROFILE\.grok\bin\grok.exe" --cwd $Work --always-approve -p $prompt 2>&1 | Tee-Object (Join-Path $LogDir "grok-$num.log")
    "grok exit: $LASTEXITCODE"
    # שחרור אם לא נפתח PR (הסוכן אמור לשחרר בעצמו במסלול הכישלון; חגורת בטיחות)
    $pr = gh pr list --repo $Repo --head "auto/$num" --json number --jq 'length'
    if ($pr -eq "0") { gh issue edit $num --repo $Repo --remove-label "agent:claimed" | Out-Null; "אין PR — התביעה שוחררה" }
} finally { Stop-Transcript | Out-Null }
