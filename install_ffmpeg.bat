@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "DEST=ffmpeg_bin"
set "TMP=%cd%\ffmpeg_tmp"
set "BIN=%TMP%\bin"

rem 下载源（国内直连优先，失败自动切换）
set "URL_FFMPEG_CN=https://registry.npmmirror.com/-/binary/ffmpeg-static/b6.1.1/ffmpeg-win32-x64.gz"
set "URL_FFPROBE_CN=https://registry.npmmirror.com/-/binary/ffmpeg-static/b6.1.1/ffprobe-win32-x64.gz"
set "URL_GYAN=https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
set "URL_BTBN=https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"

echo ========================================
echo   FFmpeg 自动下载与配置脚本
echo ========================================
echo 安装位置: %cd%\%DEST%
echo.

where curl.exe >nul 2>nul || (
    echo [错误] 未找到 curl.exe，需要 Windows 10 1803 及以上版本。
    pause
    exit /b 1
)

if not exist "%DEST%" mkdir "%DEST%"

if exist "%DEST%\ffmpeg.exe" if exist "%DEST%\ffprobe.exe" (
    echo [提示] ffmpeg_bin 中已存在 ffmpeg.exe / ffprobe.exe
    set /p REINSTALL="是否重新下载覆盖？(y/N): "
    if /i "!REINSTALL!" neq "y" goto :verify
)

if exist "%TMP%" rmdir /s /q "%TMP%"
mkdir "%BIN%"

echo [1/4] 下载 ffmpeg...
echo       源1: 国内镜像 npmmirror（无需代理）
curl.exe -L --retry 2 --connect-timeout 15 -o "%TMP%\ffmpeg.gz" "%URL_FFMPEG_CN%"
curl.exe -L --retry 2 --connect-timeout 15 -o "%TMP%\ffprobe.gz" "%URL_FFPROBE_CN%"
if exist "%TMP%\ffmpeg.gz" if exist "%TMP%\ffprobe.gz" (
    echo       解压...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$i=[IO.File]::OpenRead('%TMP%\ffmpeg.gz');$o=[IO.File]::Create('%BIN%\ffmpeg.exe');$g=New-Object IO.Compression.GzipStream($i,[IO.Compression.CompressionMode]::Decompress);$g.CopyTo($o);$g.Dispose();$o.Dispose();$i.Dispose()"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$i=[IO.File]::OpenRead('%TMP%\ffprobe.gz');$o=[IO.File]::Create('%BIN%\ffprobe.exe');$g=New-Object IO.Compression.GzipStream($i,[IO.Compression.CompressionMode]::Decompress);$g.CopyTo($o);$g.Dispose();$o.Dispose();$i.Dispose()"
)
if exist "%BIN%\ffmpeg.exe" if exist "%BIN%\ffprobe.exe" goto :unpack_done

echo       源1 失败，尝试源2: gyan.dev...
curl.exe -L --retry 2 --connect-timeout 15 -o "%TMP%\ffmpeg.zip" "%URL_GYAN%"
if errorlevel 1 (
    echo       源2 失败，尝试源3: GitHub...
    curl.exe -L --retry 2 --connect-timeout 15 -o "%TMP%\ffmpeg.zip" "%URL_BTBN%"
)
if errorlevel 1 (
    echo.
    echo [错误] 所有下载源均失败，请检查网络后重试。
    rmdir /s /q "%TMP%"
    pause
    exit /b 1
)
echo       解压...
tar -xf "%TMP%\ffmpeg.zip" -C "%TMP%"
if errorlevel 1 (
    echo [错误] 解压失败，文件可能不完整。
    rmdir /s /q "%TMP%"
    pause
    exit /b 1
)
set "FFM="
set "FFP="
for /f "delims=" %%f in ('dir /s /b "%TMP%\ffmpeg.exe"') do if not defined FFM set "FFM=%%f"
for /f "delims=" %%f in ('dir /s /b "%TMP%\ffprobe.exe"') do if not defined FFP set "FFP=%%f"
if defined FFM copy /y "!FFM!" "%BIN%\ffmpeg.exe" >nul
if defined FFP copy /y "!FFP!" "%BIN%\ffprobe.exe" >nul
if not exist "%BIN%\ffmpeg.exe" (
    echo [错误] 压缩包中未找到 ffmpeg.exe。
    rmdir /s /q "%TMP%"
    pause
    exit /b 1
)
if not exist "%BIN%\ffprobe.exe" (
    echo [错误] 压缩包中未找到 ffprobe.exe。
    rmdir /s /q "%TMP%"
    pause
    exit /b 1
)

:unpack_done
echo [2/4] 复制到 ffmpeg_bin...
copy /y "%BIN%\ffmpeg.exe" "%DEST%\ffmpeg.exe" >nul
copy /y "%BIN%\ffprobe.exe" "%DEST%\ffprobe.exe" >nul
rmdir /s /q "%TMP%"

echo [3/4] 验证安装...

:verify
if not exist "%DEST%\ffmpeg.exe" (
    echo [错误] %DEST%\ffmpeg.exe 不存在，配置失败。
    pause
    exit /b 1
)
"%DEST%\ffmpeg.exe" -version 2>&1 | findstr /i "ffmpeg version" && echo        [OK] ffmpeg 就绪

if not exist "%DEST%\ffprobe.exe" (
    echo [错误] %DEST%\ffprobe.exe 不存在，配置失败。
    pause
    exit /b 1
)
"%DEST%\ffprobe.exe" -version 2>&1 | findstr /i "ffprobe version" && echo        [OK] ffprobe 就绪

echo.
echo ========================================
echo   完成！ffmpeg 已配置到: %cd%\%DEST%
echo   打包后的 exe 需与 ffmpeg_bin 放在同目录。
echo ========================================
pause
