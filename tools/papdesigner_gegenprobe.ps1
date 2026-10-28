param(
    [Parameter(Mandatory = $true)][string]$ListFile,
    [Parameter(Mandatory = $true)][string]$OutDir,
    [int]$WaitSeconds = 12
)
# Öffnet jede Datei im Original-PapDesigner, liest alle Fenster und Meldungen des Prozesses über
# UI Automation aus, speichert ein Bild jedes Fensters (PrintWindow, auch wenn es verdeckt ist) und beendet
# den Prozess wieder. Es werden keine Tasten oder Klicks gesendet.

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Drawing
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left, Top, Right, Bottom; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool PrintWindow(IntPtr h, IntPtr hdc, uint flags);
    public delegate bool EnumProc(IntPtr h, IntPtr p);
    [DllImport("user32.dll")] public static extern bool EnumWindows(EnumProc cb, IntPtr p);
    [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
    [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetWindowText(IntPtr h, System.Text.StringBuilder s, int n);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] public static extern int GetClassName(IntPtr h, System.Text.StringBuilder s, int n);
}
"@

$exe = "C:\Program Files (x86)\PapDesigner\PapDesigner.exe"
New-Item -ItemType Directory -Force $OutDir | Out-Null

function Get-ProcessWindows([int]$processId) {
    $found = New-Object System.Collections.Generic.List[IntPtr]
    $callback = [Win+EnumProc] {
        param($h, $p)
        $owner = 0
        [void][Win]::GetWindowThreadProcessId($h, [ref]$owner)
        if ($owner -eq $processId -and [Win]::IsWindowVisible($h)) { $found.Add($h) }
        return $true
    }
    [void][Win]::EnumWindows($callback, [IntPtr]::Zero)
    return $found
}

function Save-WindowImage([IntPtr]$h, [string]$path) {
    $r = New-Object Win+RECT
    [void][Win]::GetWindowRect($h, [ref]$r)
    $w = $r.Right - $r.Left; $hh = $r.Bottom - $r.Top
    if ($w -le 0 -or $hh -le 0) { return }
    $bmp = New-Object System.Drawing.Bitmap $w, $hh
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $hdc = $g.GetHdc()
    [void][Win]::PrintWindow($h, $hdc, 2)
    $g.ReleaseHdc($hdc); $g.Dispose()
    $bmp.Save($path, [System.Drawing.Imaging.ImageFormat]::Png); $bmp.Dispose()
}

function Get-Texts([IntPtr]$h) {
    $element = [System.Windows.Automation.AutomationElement]::FromHandle($h)
    $all = $element.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
    $texts = @()
    foreach ($e in $all) {
        $name = $e.Current.Name
        $type = $e.Current.ControlType.ProgrammaticName -replace "ControlType\.", ""
        if ($name -and $name.Trim()) { $texts += "$type=$($name.Trim())" }
    }
    return ($texts | Select-Object -Unique)
}

$Files = Get-Content -Encoding utf8 $ListFile | Where-Object { $_.Trim() }
$report = @()
foreach ($file in $Files) {
    $base = [System.IO.Path]::GetFileNameWithoutExtension($file)
    Get-Process PapDesigner -ErrorAction SilentlyContinue | Stop-Process -Force
    Start-Sleep -Milliseconds 500
    $p = Start-Process -FilePath $exe -ArgumentList "`"$file`"" -PassThru
    Start-Sleep -Seconds $WaitSeconds
    $entry = [ordered]@{ file = $base; alive = -not $p.HasExited; windows = @() }
    if (-not $p.HasExited) {
        $i = 0
        foreach ($h in (Get-ProcessWindows $p.Id)) {
            $sb = New-Object System.Text.StringBuilder 512; [void][Win]::GetWindowText($h, $sb, 512)
            $cb = New-Object System.Text.StringBuilder 256; [void][Win]::GetClassName($h, $cb, 256)
            $img = Join-Path $OutDir ("{0}_{1}.png" -f $base, $i)
            Save-WindowImage $h $img
            $texts = @()
            try { $texts = Get-Texts $h } catch { $texts = @("UIA-Fehler: $($_.Exception.Message)") }
            $entry.windows += [ordered]@{ title = $sb.ToString(); class = $cb.ToString(); image = $img;
                                          texts = ($texts | Select-Object -First 60) }
            $i++
        }
    }
    $report += $entry
    Get-Process PapDesigner -ErrorAction SilentlyContinue | Stop-Process -Force
}
$report | ConvertTo-Json -Depth 6 | Set-Content -Encoding utf8 (Join-Path $OutDir "bericht.json")
"fertig: $($report.Count) Dateien"
