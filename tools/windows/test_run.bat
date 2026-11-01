@echo off
cd /d "%~dp0..\.."

echo ============================================================
echo  Blacksmith CurveTracer - Testing executable with error logging
echo ============================================================
echo.

if not exist "dist\CurveTracer\CurveTracer.exe" (
    echo ERROR: dist\CurveTracer\CurveTracer.exe not found!
    echo You must build first with build_windows.bat
    pause
    exit /b 1
)

echo Running CurveTracer.exe with error logging...
cd dist\CurveTracer
CurveTracer.exe 2>error.log
set exit_code=%errorlevel%

if %exit_code% NEQ 0 (
    echo.
    echo ============================================================
    echo  Executable failed with exit code: %exit_code%
    echo ============================================================
    echo.
    echo Error log:
    type error.log
    echo.
    echo ============================================================
)

pause
exit /b %exit_code%
