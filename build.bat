@echo off
chcp 65001 >nul
echo ========================================
echo   VideoTool Build Script
echo ========================================
echo.
echo [1/4] Checking dependencies...
pip install PyQt5 PyInstaller Pillow -q
if errorlevel 1 (
    echo Dependency install failed!
    pause
    exit /b 1
)
echo.
echo [2/4] Generating icon...
python -c "from PIL import Image; img=Image.open('assets/icon.jpg'); sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]; icons=[img.resize(s, Image.Resampling.LANCZOS) for s in sizes]; icons[0].save('assets/icon.ico', format='ICO', sizes=[(s[0],s[1]) for s in sizes])"
if errorlevel 1 (
    echo Icon generation failed!
    pause
    exit /b 1
)
echo.
echo [3/4] Cleaning old files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist VideoTool.spec del VideoTool.spec
echo.
echo [4/4] Building exe...
python -m PyInstaller --noconsole --onefile --name VideoTool --icon assets/icon.ico --add-data "assets;assets" --clean main.py
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
