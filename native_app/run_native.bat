@echo off
setlocal

rem Move to project root (.. from native_app dir)
cd /d %~dp0\..

echo [1/3] Upgrading pip...
python -m pip install --upgrade pip || goto :err

echo [2/3] Installing dependencies (PySide6, pandas, streamlit, openpyxl, xlsxwriter)...
python -m pip install PySide6 pandas streamlit openpyxl xlsxwriter || goto :err

echo [3/3] Launching native app...
python -m native_app.main_qt
if errorlevel 1 goto :err
goto :end

:err
echo.
echo An error occurred while launching the app.
echo The window is kept open so you can read the error above.
pause

:end
endlocal

