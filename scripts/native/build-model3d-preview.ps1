# Maintainer build. End users get the prebuilt x64 DLL or the Python renderer.
param([string]$Cxx = 'g++')
$ErrorActionPreference = 'Stop'
if ((& $Cxx -dumpmachine) -ne 'x86_64-w64-mingw32') { throw 'Use a Windows x64 MinGW-w64 compiler.' }
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$out = Join-Path $root 'revon/model3d/preview-win-x64.dll'
& $Cxx -std=c++17 -O2 -ffp-contract=off -fno-fast-math -shared -static-libgcc -static-libstdc++ -s '-Wl,--no-insert-timestamp' (Join-Path $PSScriptRoot 'model3d_preview.cpp') -o $out
if ($LASTEXITCODE -ne 0) { throw 'Preview rasterizer build failed.' }
