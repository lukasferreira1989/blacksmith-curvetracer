@echo off
setlocal EnableExtensions
chcp 65001 >nul
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

rem --- Localizar um Python 64 bits suportado ---------------------------
rem PyQt6/NumPy/SciPy tem wheels para 3.11-3.13. Preferir essas versoes.
set "PYTHON="
for %%V in (3.13 3.12 3.11) do (
    if not defined PYTHON (
        py -%%V -c "import sys,struct; sys.exit(0 if struct.calcsize('P') == 8 else 1)" >nul 2>nul
        if not errorlevel 1 set "PYTHON=py -%%V"
    )
)
if not defined PYTHON (
    py -3 -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON=py -3"
)
if not defined PYTHON (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PYTHON=python"
)
if not defined PYTHON goto :no_python

%PYTHON% -c "import sys; print('Python', sys.version.split()[0])"
if errorlevel 1 goto :no_python
%PYTHON% -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto :old_python
%PYTHON% -c "import sys,struct; sys.exit(0 if struct.calcsize('P')*8 == 64 else 1)"
if errorlevel 1 goto :not_64bit

rem --- Ambiente virtual de build --------------------------------------
if not exist ".venv-win\Scripts\python.exe" (
    echo Creating build virtual environment in .venv-win ...
    %PYTHON% -m venv .venv-win
    if errorlevel 1 goto :error
)

call ".venv-win\Scripts\activate.bat"
if errorlevel 1 goto :error

rem O venv pode ser antigo: validar a versao realmente usada no build.
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
if errorlevel 1 goto :old_venv
python -c "import sys,struct; sys.exit(0 if struct.calcsize('P')*8 == 64 else 1)"
if errorlevel 1 goto :not_64bit

echo.
echo Updating pip ...
python -m pip install --upgrade pip
if errorlevel 1 goto :error

echo.
echo Installing runtime and build dependencies ...
echo   (PyVISA-py[usb], pyusb, libusb-package, PyQt6, NumPy, SciPy, Matplotlib)
python -m pip install -r requirements.txt -r requirements-build.txt
if errorlevel 1 goto :error

echo.
echo Installed USB/network stack:
python -c "import pyvisa, pyvisa_py, usb; print('  pyvisa', pyvisa.__version__); print('  pyvisa-py OK'); print('  pyusb OK')"
if errorlevel 1 goto :error
python -c "import libusb_package; print('  libusb-package OK ->', libusb_package.get_library_path())"
if errorlevel 1 echo   WARNING: libusb-package not available (USB via pyusb may fail; NI-VISA still works).

echo.
echo Running the test suite ...
set "QT_QPA_PLATFORM=offscreen"
set "CURVETRACER_SKIP_DISCOVERY=1"
set "CURVETRACER_NO_DISCOVERY=1"
python -m unittest discover -s tests
if errorlevel 1 goto :error
set "QT_QPA_PLATFORM="
set "CURVETRACER_SKIP_DISCOVERY="
set "CURVETRACER_NO_DISCOVERY="

echo.
echo Building the executable ...
python -m PyInstaller --noconfirm --clean CurveTracer.spec
if errorlevel 1 goto :error

if not exist "dist\CurveTracer\CurveTracer.exe" (
    echo ERROR: PyInstaller finished but dist\CurveTracer\CurveTracer.exe was not created.
    goto :error
)

echo.
echo Verifying the frozen application (imports, Qt, libusb) ...
set "QT_QPA_PLATFORM=offscreen"
set "CURVETRACER_SKIP_DISCOVERY=1"
set "CURVETRACER_NO_DISCOVERY=1"
set "SELF_CHECK_FAILED="
start "" /wait "dist\CurveTracer\CurveTracer.exe" --self-check
if errorlevel 1 set "SELF_CHECK_FAILED=1"
set "QT_QPA_PLATFORM="
set "CURVETRACER_SKIP_DISCOVERY="
set "CURVETRACER_NO_DISCOVERY="
if defined SELF_CHECK_FAILED goto :self_check_failed

echo.
echo ============================================================
echo  Build complete.
echo  Executable: "%CD%\dist\CurveTracer\CurveTracer.exe"
echo.
echo  Distribute the whole dist\CurveTracer folder (ZIP it),
echo  not only the .exe file.
echo.
echo  Conexao com o osciloscopio:
echo   - Rede: IP do DHO, porta 5555 (firewall liberado).
echo   - USB:  instale o NI-VISA (recomendado) OU use o driver WinUSB
echo           (Zadig) para o pyusb usar a libusb empacotada.
echo ============================================================
pause
exit /b 0

:self_check_failed
echo.
echo ERROR: the built executable failed its self-check.
echo Log: %LOCALAPPDATA%\CurveTracer\curvetracer.log
echo ------------------------------------------------------------
if exist "%LOCALAPPDATA%\CurveTracer\curvetracer.log" (
    powershell -NoProfile -Command "Get-Content -Path \"$env:LOCALAPPDATA\CurveTracer\curvetracer.log\" -Tail 30"
)
echo ------------------------------------------------------------
pause
exit /b 1

:no_python
echo.
echo ERROR: Python 3 was not found.
echo Install 64-bit Python 3.11, 3.12 or 3.13 from
echo https://www.python.org/downloads/windows/
echo and enable "Add python.exe to PATH" during installation.
echo Do not use the Microsoft Store alias.
pause
exit /b 1

:old_python
echo.
echo ERROR: Python 3.11 or newer is required.
pause
exit /b 1

:old_venv
echo.
echo ERROR: the existing .venv-win uses Python older than 3.11.
echo Delete the .venv-win folder and run this script again.
pause
exit /b 1

:not_64bit
echo.
echo ERROR: 64-bit Python is required.
echo Install the 64-bit build from https://www.python.org/downloads/windows/
pause
exit /b 1

:error
echo.
echo ERROR: the build failed. Review the messages above.
pause
exit /b 1
