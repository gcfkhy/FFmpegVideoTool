@echo off
cd /d "%~dp0"
echo ========================================
echo   MediaKit 单个 exe
echo   每次启动会先解压，打开较慢
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
python -c "from PIL import Image; img=Image.open('assets/icon.jpg').convert('RGBA'); sizes=[(16,16),(20,20),(24,24),(32,32),(40,40),(48,48),(64,64),(96,96),(128,128),(256,256)]; icons=[img.resize(s, Image.Resampling.LANCZOS) for s in sizes]; icons[-1].save('assets/icon.ico', format='ICO', sizes=sizes, append_images=icons[:-1])"
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
if exist MediaKit.spec del MediaKit.spec
echo.
echo [4/4] Building single exe...
if not exist ffmpeg_bin\ffmpeg.exe (
    echo ffmpeg_bin\ffmpeg.exe not found! Run install_ffmpeg.bat first.
    pause
    exit /b 1
)
python -m PyInstaller --noconsole --onefile --name MediaKit --icon assets/icon.ico --add-data "assets;assets" --add-data "ffmpeg_bin;ffmpeg_bin" --add-data "msyh.ttc;." --clean main.py
if errorlevel 1 (
    echo Build failed!
    pause
    exit /b 1
)
echo.
echo ========================================
echo   Build complete!
echo   Output: dist\MediaKit.exe
echo ========================================
pause
