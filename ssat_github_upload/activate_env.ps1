# Dot-source this in any new PowerShell session before using the venv or pyrfc:
#   . .\activate_env.ps1
# Scoped to this session/project only -- does not touch machine-wide PATH.

$SdkPath = Join-Path $PSScriptRoot "sdk\nwrfc750P_16-70002755\nwrfcsdk"
$VenvScripts = Join-Path $PSScriptRoot ".venv\Scripts"

$env:SAPNWRFC_HOME = $SdkPath
$env:PATH = "$SdkPath\lib;$VenvScripts;$env:PATH"

Write-Host "SAPNWRFC_HOME = $env:SAPNWRFC_HOME"
Write-Host "venv Scripts added to PATH: $VenvScripts"
