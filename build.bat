@echo off
chcp 65001 >nul
echo ========================================
echo   VideoTool Build Script
echo ========================================
echo.
echo [1/3] Checking dependencies...
pip install PyQt5 PyInstaller -q
if errorlevel 1 (
    echo Dependency install failed!
    pause
    exit /b 1
)
echo.
echo [2/3] Cleaning old files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist VideoTool.spec del VideoTool.spec
echo.
echo [3/3] Building exe...
python -m PyInstaller --noconsole --onefile --name VideoTool --clean main.py
if errorlevel 1 (
    echo Build failed!
    pause
    exit /b 1
)
echo.
echo ========================================
echo   Build complete!
echo   Output: dist\VideoTool.exe
echo ========================================
pause
