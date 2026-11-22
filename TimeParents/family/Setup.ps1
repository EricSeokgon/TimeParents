#Requires -Version 5.1
#Requires -RunAsAdministrator
[CmdletBinding()]
param(
    [Parameter(Mandatory)][ValidateSet('Install','Enroll','Remove','Uninstall')][string]$Action,
    [string]$Account = $env:TIMEPARENTS_SETUP_ACCOUNT
)
$ErrorActionPreference = 'Stop'
if (![Environment]::Is64BitProcess) { throw 'Run 64-bit Windows PowerShell.' }
$root = 'HKLM:\SOFTWARE\TimeParents\Family'
$install = Join-Path ([Environment]::GetFolderPath('ProgramFiles')) 'TimeParents Family'
$exe = Join-Path $install 'TimeParents.Family.exe'
$service = 'TimeParentsFamily'
$shellValue = '"' + $exe + '" --child'
$serviceValue = '"' + $exe + '" --service'
$policy = 'Software\Microsoft\Windows\CurrentVersion\Policies\System'

function Invoke-Native([string]$Program, [string[]]$Arguments) {
    $out = & $Program @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) { throw "$Program ($LASTEXITCODE) $out" }
}
function Get-Rule([string]$Sid) {
    (Get-ItemProperty -LiteralPath "$root\Rules" -Name $Sid -ErrorAction SilentlyContinue).$Sid
}
function Confirm-OwnService {
    if ((Get-ItemProperty "HKLM:\SYSTEM\CurrentControlSet\Services\$service").ImagePath -ne $serviceValue) {
        throw 'A different service already uses the service name.'
    }
}
if ($Action -eq 'Install') {
    $edition = (Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion').EditionID
    if ($edition -notmatch '^(Professional|Enterprise|Education|IoTEnterprise)') {
        throw 'Child mode requires Windows Pro, Education or Enterprise.'
    }
    $src = Join-Path $PSScriptRoot 'TimeParents.Family.exe'
    if (!(Test-Path -LiteralPath $src -PathType Leaf)) { throw 'Missing TimeParents.Family.exe.' }
    $existing = Get-Service $service -ErrorAction SilentlyContinue
    if ($existing) { Confirm-OwnService }
    if (!(Test-Path -LiteralPath $install)) { New-Item -ItemType Directory -Path $install | Out-Null }
    if ((Get-Item -LiteralPath $install).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Invalid install directory.' }
    # Program Files is admin-owned. Explicitly protect this service's executable and its directory.
    $admins = [Security.Principal.SecurityIdentifier]'S-1-5-32-544'
    $system = [Security.Principal.SecurityIdentifier]'S-1-5-18'
    $users  = [Security.Principal.SecurityIdentifier]'S-1-5-32-545'
    $acl = New-Object Security.AccessControl.DirectorySecurity
    $acl.SetAccessRuleProtection($true,$false)
    $acl.SetOwner($admins)
    foreach ($principal in $admins,$system,$users) {
        $right = if ($principal -eq $users) { 'ReadAndExecute' } else { 'FullControl' }
        $acl.AddAccessRule((New-Object Security.AccessControl.FileSystemAccessRule($principal,$right,'ContainerInherit,ObjectInherit','None','Allow')))
    }
    Set-Acl -LiteralPath $install -AclObject $acl
    $replace = $PSScriptRoot -ne $install
    if ($replace -and $existing) {
        $rules = Get-Item -LiteralPath "$root\Rules" -ErrorAction SilentlyContinue
        if ($rules -and @($rules.GetValueNames() | Where-Object { ($rules.GetValue($_) | ConvertFrom-Json).Enabled }).Count) {
            throw 'Remove enrolled accounts before replacing the installed service.'
        }
        Stop-Service $service
    }
    if ($replace) {
        foreach ($name in 'TimeParents.Family.exe','Setup.ps1') {
            $target = Join-Path $install $name
            if ((Test-Path $target) -and ((Get-Item $target).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                throw 'Invalid destination file.'
            }
            Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $target -Force
        }
    }
    if (!(Test-Path -LiteralPath $root)) { New-Item -Path $root -Force | Out-Null }
    $regAcl = New-Object Security.AccessControl.RegistrySecurity
    $regAcl.SetAccessRuleProtection($true,$false)
    foreach ($principal in $admins,$system) {
        $regAcl.AddAccessRule((New-Object Security.AccessControl.RegistryAccessRule($principal,'FullControl','ContainerInherit','None','Allow')))
    }
    Set-Acl -LiteralPath $root -AclObject $regAcl
    foreach ($name in 'History','Rules') {
        if (!(Test-Path -LiteralPath "$root\$name")) { New-Item -Path "$root\$name" | Out-Null }
    }
    if (!$existing) {
        New-Service -Name $service -DisplayName 'TimeParents Family' -BinaryPathName $serviceValue -StartupType Automatic | Out-Null
    }
    Invoke-Native "$env:SystemRoot\System32\sc.exe" @('failure',$service,'reset=','86400','actions=','restart/5000/restart/10000/restart/30000')
    Start-Service $service
    return
}
if ($Action -eq 'Uninstall') {
    $rules = Get-Item -LiteralPath "$root\Rules" -ErrorAction SilentlyContinue
    if ($rules -and @($rules.GetValueNames() | Where-Object { ($rules.GetValue($_) | ConvertFrom-Json).Enabled }).Count) {
        throw 'Remove each child first to restore the normal Windows desktop.'
    }
    if (Get-Service $service -ErrorAction SilentlyContinue) {
        Confirm-OwnService
        Stop-Service $service
        Invoke-Native "$env:SystemRoot\System32\sc.exe" @('delete',$service)
    }
    return
}
if ([string]::IsNullOrWhiteSpace($Account)) { throw 'Specify a local Windows account.' }
# Exact comparison prevents wildcard expansion from selecting another account.
$user = Get-LocalUser | Where-Object { $_.Name -eq $Account -or ($Action -eq 'Remove' -and $_.SID.Value -eq $Account) }
if ($user) { $sid = $user.SID.Value }
elseif ($Action -eq 'Remove' -and $Account -match '^S-1-5-21-\d+-\d+-\d+-\d+$' -and (Get-Rule $Account)) { $sid = $Account }
else { throw 'Local Windows account not found.' }
if ($Action -eq 'Enroll') {
    Confirm-OwnService
    if ((Get-Service $service).Status -ne 'Running') { throw 'Start the TimeParents Family service first.' }
    if (!$user.Enabled -or $sid -eq [Security.Principal.WindowsIdentity]::GetCurrent().User.Value -or
        [int]($sid.Split('-')[-1]) -lt 1000) { throw 'Choose a separate, enabled standard child account.' }
    if (Get-LocalGroupMember -SID 'S-1-5-32-544' | Where-Object { $_.SID.Value -eq $sid }) { throw 'Administrator accounts cannot be enrolled.' }
    if (Test-Path -LiteralPath "Registry::HKEY_USERS\$sid") { throw 'Sign out of the child account before enrolling it.' }
}
$profile = Get-ItemProperty -LiteralPath "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\ProfileList\$sid" -ErrorAction SilentlyContinue
if (!$profile) {
    if ($Action -eq 'Remove') {
        $oldRule = Get-Rule $sid
        if ($oldRule) {
            $r = $oldRule | ConvertFrom-Json
            $r.Enabled = $false
            Set-ItemProperty -LiteralPath "$root\Rules" -Name $sid -Value ($r | ConvertTo-Json -Compress)
        }
        return
    }
    throw 'Sign in to this child account once, sign out, and then enroll it.'
}
$mount = $sid
$loaded = $false
if (!(Test-Path -LiteralPath "Registry::HKEY_USERS\$sid")) {
    $mount = 'TimeParents_' + [Guid]::NewGuid().ToString('N')
    $file = Join-Path ([Environment]::ExpandEnvironmentVariables($profile.ProfileImagePath)) 'NTUSER.DAT'
    Invoke-Native "$env:SystemRoot\System32\reg.exe" @('load',"HKU\$mount",$file)
    $loaded = $true
}
try {
    $path = "Registry::HKEY_USERS\$mount\$policy"
    $oldShell = (Get-ItemProperty -LiteralPath $path -Name Shell -ErrorAction SilentlyContinue).Shell
    $oldRule = Get-Rule $sid
    if ($Action -eq 'Remove') {
        if ($oldShell -eq $shellValue) { Remove-ItemProperty -LiteralPath $path -Name Shell }
        if ($oldRule) {
            $r = $oldRule | ConvertFrom-Json
            $r.Enabled = $false
            Set-ItemProperty -LiteralPath "$root\Rules" -Name $sid -Value ($r | ConvertTo-Json -Compress)
        }
        return
    }
    if ($oldShell -and $oldShell -ne $shellValue) { throw 'An existing custom shell is configured for this account.' }
    if (!$oldShell -and !(Test-Path -LiteralPath $path)) { New-Item -Path $path -Force | Out-Null }
    $r = if ($oldRule) { $oldRule | ConvertFrom-Json } else {
        [pscustomobject]@{Name=$user.Name; Enabled=$false; Weekday=60; Weekend=60; ExtraDay=''; ExtraMinutes=0}
    }
    $r.Enabled = $true
    Set-ItemProperty -LiteralPath "$root\Rules" -Name $sid -Type String -Value ($r | ConvertTo-Json -Compress)
    try { Set-ItemProperty -LiteralPath $path -Name Shell -Type String -Value $shellValue }
    catch {
        if ($oldRule) { Set-ItemProperty -LiteralPath "$root\Rules" -Name $sid -Value $oldRule }
        else { Remove-ItemProperty -LiteralPath "$root\Rules" -Name $sid }
        throw
    }
}
finally {
    if ($loaded) {
        [GC]::Collect(); [GC]::WaitForPendingFinalizers()
        Invoke-Native "$env:SystemRoot\System32\reg.exe" @('unload',"HKU\$mount")
    }
}

