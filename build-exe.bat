@echo off
cd /d "%~dp0"
echo ========================================
echo   MediaKit 锟斤拷锟斤拷 exe
echo   每锟斤拷锟斤拷锟斤拷锟斤拷锟饺斤拷压锟斤拷锟津开斤拷锟斤拷
echo ========================================
echo.
echo [1/4] Checking dependencies...
pip install PyQt5 PyInstaller Pillow pypdf pymupdf reportlab pywin32 -q
if errorlevel 1 (
    echo Dependency install failed!
    pause
    exit /b 1
)
echo.
echo [2/4] Generating icon...
python make_icon.py
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
python -m PyInstaller --noconsole --onefile --name MediaKit --icon assets/icon.ico --add-data "assets;assets" --add-data "ffmpeg_bin;ffmpeg_bin" --add-data "msyh.ttc;." --hidden-import pypdf --hidden-import pypdf.constants --hidden-import PyPDF2 --hidden-import pymupdf --hidden-import fitz --hidden-import reportlab --hidden-import reportlab.pdfgen.canvas --hidden-import reportlab.pdfbase._fontdata --hidden-import PIL --hidden-import win32com --hidden-import win32com.client --hidden-import pythoncom --clean main.py
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
