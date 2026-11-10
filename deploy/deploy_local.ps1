<#
.SYNOPSIS
Installs the newest tested build of the Experience Journal (FaceRecognizer.exe plus the journal) on this computer,
for hands-on testing.

.DESCRIPTION
Pull-based on purpose: GitHub never reaches into this computer (the repositories are public, so a self-hosted
runner here would let anyone's pull request run code on it). This script asks GitHub for the newest run of the
"checks" workflow that passed on a push to main, downloads its experience-journal-bundle artifact with the GitHub
CLI (gh), checks every file against the bundle's SHA256SUMS.txt and its commit against the run's, and installs it
into builds\<commit> under the test folder. Start.cmd there always starts the current build.

The test build uses its own folders, never your own library: face-root (models and data) and face-home (keys,
alerts, presence log, window storage). -SeedFrom copies a face-recognizer folder's models and data into them once.

A running test app is never stopped: the new build becomes current, and the next start uses it.

.EXAMPLE
deploy\deploy_local.ps1 -Launch                      # install the newest green build and start it
deploy\deploy_local.ps1 -SeedFrom X:\source\facial-recognition\face-recognizer -Launch
deploy\deploy_local.ps1 -Install                     # check every 10 minutes, with a notification per new build
deploy\deploy_local.ps1 -Uninstall                   # stop checking

Needs: the GitHub CLI (gh), signed in (gh auth login). Windows PowerShell 5.1 or PowerShell 7.
#>
[CmdletBinding()]
param(
    [string]$Repo = "SingularityResearch/experience-journal",
    [string]$Branch = "main",
    [string]$Root = (Join-Path $env:LOCALAPPDATA "ExperienceJournal\test"),
    [int]$Keep = 3,             # builds kept (the current one, and one in use, are never removed)
    [switch]$Launch,            # start the app after installing, unless a test copy is already running
    [switch]$Force,             # install again even if this build is already the current one
    [string]$SeedFrom,          # a face-recognizer folder (models\, data\) copied into the test folders, once
    [switch]$Notify,            # a Windows notification when a new build is installed (the scheduled check)
    [switch]$Install,           # check in the background every -Every minutes (a scheduled task for this user)
    [int]$Every = 10,
    [switch]$Uninstall
)
$ErrorActionPreference = "Stop"
$TaskName = "Experience Journal test deploy"
$Artifact = "experience-journal-bundle"
New-Item -ItemType Directory -Force $Root | Out-Null
$Log = Join-Path $Root "deploy.log"

function Say([string]$Message) {
    $line = "$(Get-Date -Format s) $Message"
    Write-Host $line
    Add-Content -Path $Log -Value $line
}

function Show-Notification([string]$Title, [string]$Text) {
    try {   # Windows PowerShell 5.1 can show a Windows notification directly
        $null = [Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
        $xml = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
        $t = $xml.GetElementsByTagName("text")
        $null = $t.Item(0).AppendChild($xml.CreateTextNode($Title))
        $null = $t.Item(1).AppendChild($xml.CreateTextNode($Text))
        $app = "{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
        [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($xml))
    } catch {
        Say "(no notification: $($_.Exception.Message))"
    }
}

# ------------------------------------------------------------------ the scheduled check
if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Say "Stopped checking for new builds (removed the scheduled task '$TaskName')."
    return
}
if ($Install) {
    $taskArgs = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Notify " +
                "-Repo `"$Repo`" -Branch `"$Branch`" -Root `"$Root`" -Keep $Keep"
    $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $taskArgs
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes $Every)
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
                -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force `
        -Description "Installs the newest green build of $Repo ($Branch) into $Root for testing (deploy_local.ps1)." | Out-Null
    Say "Checking for new builds every $Every minutes (scheduled task '$TaskName'); -Uninstall stops it."
}

# ------------------------------------------------------------------ the newest green build
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw "The GitHub CLI (gh) isn't installed: winget install GitHub.cli, then gh auth login."
}
$json = gh run list -R $Repo --workflow checks.yml --branch $Branch --event push --status success --limit 1 `
        --json "databaseId,headSha,displayTitle,createdAt"
if ($LASTEXITCODE -ne 0) { throw "gh couldn't list the builds (signed in? gh auth status)" }
$run = @($json | ConvertFrom-Json)[0]
if (-not $run) { Say "No passing build of $Branch yet."; return }
$sha = $run.headSha
$short = $sha.Substring(0, 7)
$currentFile = Join-Path $Root "current.json"
$current = if (Test-Path $currentFile) { Get-Content $currentFile -Raw | ConvertFrom-Json } else { $null }
$dir = Join-Path $Root "builds\$short"
$fresh = $Force -or -not $current -or $current.commit -ne $sha -or -not (Test-Path (Join-Path $dir "FaceRecognizer.exe"))

if ($fresh) {
    Say "Installing build $short ($($run.displayTitle)) from run $($run.databaseId)"
    $tmp = Join-Path $Root "builds\.download-$short"
    if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
    gh run download $run.databaseId -R $Repo --name $Artifact --dir $tmp
    if ($LASTEXITCODE -ne 0) { throw "gh couldn't download the build (the artifact is kept 14 days)" }
    # every file as built, and the build is the commit GitHub says it is
    $bad = @()
    foreach ($line in Get-Content (Join-Path $tmp "SHA256SUMS.txt")) {
        if ($line -notmatch '^([0-9a-f]{64})  (.+)$') { continue }
        $file = Join-Path $tmp ($Matches[2] -replace '/', '\')
        if (-not (Test-Path $file) -or (Get-FileHash $file -Algorithm SHA256).Hash.ToLower() -ne $Matches[1]) { $bad += $Matches[2] }
    }
    $info = Get-Content (Join-Path $tmp "BUILD-INFO.json") -Raw | ConvertFrom-Json
    if ($bad.Count -or $info.commit -ne $sha) {
        Remove-Item $tmp -Recurse -Force
        throw "The download doesn't match its build (files: $($bad -join ', '); commit $($info.commit) vs $sha): not installed"
    }
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
    Move-Item $tmp $dir
    @{ commit = $sha; run = $run.databaseId; title = $run.displayTitle; faceRecognizer = $info.faceRecognizer;
       installed = (Get-Date).ToString("s") } | ConvertTo-Json | Set-Content $currentFile
    Set-Content (Join-Path $Root "Start.cmd") "@call `"%~dp0builds\$short\Start-FaceRecognizer.cmd`"" -Encoding ASCII
    Say "Installed $short (face recognizer $($info.faceRecognizer)): $Root\Start.cmd starts it"
    if ($Notify) { Show-Notification "New test build ready" "$short - $($run.displayTitle) - start it from 'Experience Journal (test)'" }
} else {
    Say "Up to date: build $short is installed."
}

# ------------------------------------------------------------------ test folders, shortcut, old builds
$faceRoot = Join-Path $Root "face-root"
New-Item -ItemType Directory -Force $faceRoot, (Join-Path $Root "face-home") | Out-Null
if ($SeedFrom) {
    foreach ($part in "models", "data") {
        $src = Join-Path $SeedFrom $part
        $dst = Join-Path $faceRoot $part
        if (-not (Test-Path $src)) { Say "(nothing to copy: $src isn't there)"; continue }
        if ((Test-Path $dst) -and (Get-ChildItem $dst -Force | Select-Object -First 1)) {
            Say "Not copying $part`: the test folder already has one ($dst). Delete it first to copy again."
            continue
        }
        Say "Copying $src into the test folder ..."
        robocopy $src $dst /E /NFL /NDL /NJH /NJS /NP | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "Copying $src failed (robocopy $LASTEXITCODE)" }
    }
}
$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "Experience Journal (test).lnk"
if (-not (Test-Path $lnk)) {
    $sh = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk)
    $sh.TargetPath = Join-Path $Root "Start.cmd"
    $sh.WorkingDirectory = $Root
    $sh.Description = "The newest test build of the Experience Journal (FaceRecognizer.exe with test folders)"
    $sh.WindowStyle = 7
    $sh.Save()
    Say "Start menu: 'Experience Journal (test)'"
}
$running = @(Get-Process FaceRecognizer -ErrorAction SilentlyContinue | Where-Object { $_.Path -and $_.Path.StartsWith($Root, "OrdinalIgnoreCase") })
$inUse = $running | ForEach-Object { Split-Path (Split-Path $_.Path -Parent) -Leaf }
Get-ChildItem (Join-Path $Root "builds") -Directory | Where-Object { $_.Name -notlike ".download-*" } |
    Sort-Object LastWriteTime -Descending | Select-Object -Skip $Keep |
    Where-Object { $_.Name -ne $short -and $inUse -notcontains $_.Name } |
    ForEach-Object { Remove-Item $_.FullName -Recurse -Force; Say "Removed old build $($_.Name)" }

if ($Launch) {
    if ($running) { Say "A test copy is already running: close it and start 'Experience Journal (test)' for build $short." }
    else { Start-Process (Join-Path $Root "Start.cmd") -WindowStyle Hidden; Say "Started build $short" }
}
