@echo off
cd /d "%~dp0"
chcp 65001 >nul
echo ========================================
echo   MediaKit 打包
echo ========================================
echo   1. 单个 exe    dist\MediaKit.exe
echo   2. 便携版目录  dist\MediaKit\MediaKit.exe
echo ========================================
set /p choice=请选择 1 或 2: 
if "%choice%"=="1" (
    call "%~dp0build-exe.bat"
    exit /b %errorlevel%
)
if "%choice%"=="2" (
    call "%~dp0build-portable.bat"
    exit /b %errorlevel%
)
echo 无效选择。
pause
exit /b 1
