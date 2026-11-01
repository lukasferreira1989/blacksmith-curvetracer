@echo off
setlocal EnableExtensions
cd /d "%~dp0..\.."

if not exist "dist\CurveTracer\CurveTracer.exe" (
    echo ============================================================
    echo  ERROR: dist\CurveTracer\CurveTracer.exe was not found.
    echo  Run build_windows.bat first.
    echo ============================================================
    pause
    exit /b 1
)

echo ============================================================
echo  Running CurveTracer.exe
echo ============================================================
echo.
cd dist\CurveTracer
CurveTracer.exe
cd /d "%~dp0"

echo.
if exist "%LOCALAPPDATA%\CurveTracer\curvetracer.log" (
    echo Last lines of %%LOCALAPPDATA%%\CurveTracer\curvetracer.log:
    echo ------------------------------------------------------------
    powershell -NoProfile -Command "Get-Content -Path \"$env:LOCALAPPDATA\CurveTracer\curvetracer.log\" -Tail 40"
    echo ------------------------------------------------------------
) else (
    echo No log file found at %%LOCALAPPDATA%%\CurveTracer\curvetracer.log
)
pause
