<#
  install_yasar_autostart.ps1  -  Layer 0 auto-start for Yasar Usta.

  ASCII-ONLY BY DESIGN. Windows PowerShell 5.1 (powershell.exe) decodes a
  BOM-less script through the ANSI codepage, not UTF-8. Non-ASCII bytes
  (em-dash, box-drawing, arrows, Turkish letters) then mis-decode and can
  produce a stray quote -> parse error -> the whole script fails to run
  (exit 1, no output). Keep every byte in this file 7-bit ASCII.

  Registers two Task Scheduler tasks that keep the hub alive across reboots,
  crashes, AND hard-kills. Per the validated design (docs/superpowers/specs/
  2026-07-17-yasar-usta-always-live-singleton-design.md sec 4.4/7): Task
  Scheduler @ elevated in the USER session (NOT a Session-0 service, which
  would break the S13/S14 presence sensors). Never-duplicates is guaranteed by
  the hub's named mutex; these tasks are the "always-lives" relauncher.

  The hub runs as:
    python -m yasar_usta --registry <hub>\registry.yaml
  spawned by the Task Scheduler service, so it has NO console and cannot be
  killed by a window close (the failure mode on 2026-07-23, when an in-console
  launch tied the hub to a shell that was later closed and CTRL_CLOSE
  hard-killed the tree). State files (hub.alive, .watchdog_killed, hub.stopped)
  live under %LOCALAPPDATA%\YasarUsta\hub\.

  Two triggers per task (the "never dies again" core):
    - AtLogOn    : starts on every interactive logon (with auto-logon = boot).
    - Every 3m   : a standalone, boot-INDEPENDENT time trigger (NOT a
                   repetition bolted on the logon trigger). The MAIN task
                   re-attempts a start every 3 min; when the hub is already up
                   this is a genuine no-op (MultipleInstances=IgnoreNew + the
                   mutex), and when it is DOWN for any reason (crash, hard-kill,
                   clean exit) it comes back within 3 min without a logon. The
                   WATCHDOG runs its hung-hub check on the same cadence.
  Plus the main task keeps restart-on-failure (999x / 1 min) for a fast
  relaunch on a crash between the 3-min ticks.

  RUN ONCE, ELEVATED:
    powershell -ExecutionPolicy Bypass -File scripts\install_yasar_autostart.ps1

  AFTER running, for reboot recovery WITHOUT a manual login:
    - Enable Windows auto-logon: run netplwiz, uncheck "Users must enter a user
      name and password", enter the password once.
    - Remove any start_kutai.vbs shortcut from shell:startup (the mutex covers a
      stray one, but keep it clean). start_kutai.bat now just calls
      'schtasks /Run /TN YasarUsta' (detached) - safe to keep.

  UNDO:  Unregister-ScheduledTask -TaskName YasarUsta -Confirm:$false
         Unregister-ScheduledTask -TaskName YasarUstaWatchdog -Confirm:$false
#>

$ErrorActionPreference = "Stop"

# Fail loud, WITH a diagnostic, if anything throws - so an elevated run never
# again dies silently (exit 1, no log). Mirrors the C1 lesson.
trap {
    $line = $_.InvocationInfo.ScriptLineNumber
    Write-Host "INSTALL FAILED @ line $line : $($_.Exception.Message)"
    exit 1
}

$root     = "C:\Users\sakir\Dropbox\Workspaces\yasar_usta"
# Use pythonw.exe (GUI subsystem) so the every-3-min self-heal + watchdog ticks
# run WINDOWLESS - no console flashes on the desktop. The hub relays child
# output via print() and the watchdog prints diagnostics; both entry points call
# stdio.ensure_stdio() so a None stdout under pythonw is redirected to devnull
# (real logs go to files). Falls back to python.exe if pythonw is missing.
$python   = Join-Path $root ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $python)) { $python = Join-Path $root ".venv\Scripts\python.exe" }
$taskName = "YasarUsta"

if (-not (Test-Path $python)) { throw "venv python not found: $python" }

$user = "$env:USERDOMAIN\$env:USERNAME"

# Principal: elevated, in the interactive user session (presence sensors + GPU).
$principal = New-ScheduledTaskPrincipal -UserId $user `
    -LogonType Interactive -RunLevel Highest

# Immediate + repeating trigger factory (boot-independent self-heal). Each call
# returns a FRESH trigger object (Register-ScheduledTask consumes them per task).
function New-KeepAliveTrigger {
    New-ScheduledTaskTrigger -Once -At (Get-Date) `
        -RepetitionInterval (New-TimeSpan -Minutes 3) `
        -RepetitionDuration  (New-TimeSpan -Days 3650)
}

# -- Main task: launch the hub from the hub repo dir. -------------------------
$registry = Join-Path $root "registry.yaml"
$action = New-ScheduledTaskAction -Execute $python `
    -Argument "-m yasar_usta --registry `"$registry`"" -WorkingDirectory $root

$triggers = @(
    (New-ScheduledTaskTrigger -AtLogOn -User $user),   # every boot/logon
    (New-KeepAliveTrigger)                             # self-heal every 3 min, now
)

# Settings: relaunch on crash (nonzero exit) every 1 min; never a 2nd instance;
# survive battery/idle; no run-time cap.
$settings = New-ScheduledTaskSettingsSet `
    -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
    -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -StartWhenAvailable
$settings.ExecutionTimeLimit = "PT0S"   # unlimited

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers `
    -Settings $settings -Principal $principal -Force | Out-Null

# -- Watchdog task: catches a HUNG-but-alive hub (restart-on-failure can't).
# Runs every 3 min; kills the hub if hub.alive is stale, so the main task's
# restart-on-failure / 3-min keep-alive relaunches it.
$watchName   = "YasarUstaWatchdog"
$stateDir    = Join-Path $env:LOCALAPPDATA "YasarUsta\hub"
$alivePath   = Join-Path $stateDir "hub.alive"
$markerPath  = Join-Path $stateDir ".watchdog_killed"
$stoppedPath = Join-Path $stateDir "hub.stopped"
$watchAction = New-ScheduledTaskAction -Execute $python `
    -Argument "-m yasar_usta.watchdog --alive `"$alivePath`" --marker `"$markerPath`" --stopped `"$stoppedPath`"" `
    -WorkingDirectory $root
$watchTriggers = @(
    (New-ScheduledTaskTrigger -AtLogOn -User $user),   # every boot/logon
    (New-KeepAliveTrigger)                             # tick every 3 min, now
)
$watchSettings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$watchSettings.ExecutionTimeLimit = "PT0S"   # unlimited (M2: match main task)
Register-ScheduledTask -TaskName $watchName -Action $watchAction -Trigger $watchTriggers `
    -Settings $watchSettings -Principal $principal -Force | Out-Null

Write-Host "OK: '$taskName' (at-logon + every-3-min self-heal, elevated, restart-on-failure, no-duplicate) + '$watchName' (hung-hub watchdog, every 3 min from now) registered."
Write-Host "Both tasks are active immediately (no reboot needed) - the 3-min triggers are standalone time triggers, they do not wait for a logon."
Write-Host "Start now:  schtasks /Run /TN $taskName   (mutex makes it a no-op if the hub is already running)"
Write-Host "NEXT: enable auto-logon via netplwiz for reboot-without-login recovery."
