param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
$guiDirectory = Split-Path -Parent $PSScriptRoot
$qtRuntime = Join-Path (Split-Path -Parent $guiDirectory) '.venv\qt'
$qtPython = Join-Path $qtRuntime 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $qtPython)) {
    & $Python -m venv $qtRuntime
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create the Qt environment.' }
}
& $qtPython -m pip install -r (Join-Path $guiDirectory 'requirements-qt.txt')
if ($LASTEXITCODE -ne 0) { throw 'Unable to install Qt dependencies.' }
& $qtPython (Join-Path $guiDirectory 'qt_frontend\build_shaders.py')
if ($LASTEXITCODE -ne 0) { throw 'Unable to compile the GPU shaders.' }
$repo = Split-Path -Parent $guiDirectory
$build = Join-Path $PSScriptRoot 'build-source'
& $qtPython (Join-Path $repo 'scripts/prepare_pack_runtimes.py') (Join-Path $build 'pack-runtimes') --cache (Join-Path $build 'downloads')
if ($LASTEXITCODE -ne 0) { throw 'Private plugin runtime staging failed.' }
Write-Output 'Ready. Launch desktop/start-qt.ps1.'
