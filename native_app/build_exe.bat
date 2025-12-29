@echo off
setlocal

REM Build one-file EXE for the native app
python -m pip install --upgrade pip
python -m pip install pyinstaller PySide6 pandas

pyinstaller --noconfirm --windowed --onefile ^
  --name BillingApp ^
  --collect-all PySide6 ^
  native_app\main_qt.py

echo.
echo Build complete. EXE: dist\BillingApp.exe

endlocal

