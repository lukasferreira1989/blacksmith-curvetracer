@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ============================================================
echo  CurveTracer OSS - Windows executable build
echo ============================================================
echo.

echo Cleaning old builds...
if exist "build\" rmdir /s /q build
if exist "dist\" rmdir /s /q dist
if exist "*.spec.bak" del /q *.spec.bak
echo.

set "PYTHON=py -3"
where py >nul 2>nul
if errorlevel 1 set "PYTHON=python"

%PYTHON% -c "import sys; print('Python', sys.version)"
if errorlevel 1 goto :no_python

if not exist ".venv-win\Scripts\python.exe" (
    echo Creating build virtual environment in .venv-win ...
    %PYTHON% -m venv .venv-win
    if errorlevel 1 goto :error
)

call ".venv-win\Scripts\activate.bat"
if errorlevel 1 goto :error

echo Installing runtime and build dependencies ...
python -m pip install --upgrade pip
if errorlevel 1 goto :error
python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :error

echo.
echo Running the test suite ...
set "QT_QPA_PLATFORM=offscreen"
python -m unittest discover -s tests
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM="

echo.
echo Building the executable ...
python -m PyInstaller --noconfirm --clean CurveTracer.spec
if errorlevel 1 goto :error

echo.
echo ============================================================
echo  Build complete.
echo  Executable: "%CD%\dist\CurveTracer\CurveTracer.exe"
echo.
echo  Distribute the whole dist\CurveTracer folder (ZIP it),
echo  not only the .exe file.
echo ============================================================
pause
exit /b 0

:no_python
echo.
echo ERROR: Python 3 was not found.
echo Install 64-bit Python 3.11-3.13 from https://www.python.org/downloads/windows/
echo and enable "Add python.exe to PATH" during installation.
echo Do not use the Microsoft Store alias.
pause
exit /b 1

:error
echo.
echo ERROR: the build failed. Review the messages above.
pause
exit /b 1
