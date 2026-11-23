@echo off
REM Construit ConvertiaStudio.exe sur une machine Windows (Python 3.10+ installé).
setlocal
cd /d "%~dp0.."

if not exist ".venv" python -m venv .venv
call .venv\Scripts\activate

python -m pip install --upgrade pip
python -m pip install "pyinstaller>=6.10" "numpy>=1.26" "PySide6>=6.6" "Pillow>=11"

if not exist "bin" mkdir bin
if exist "C:\ffmpeg\bin\ffmpeg.exe" copy /Y "C:\ffmpeg\bin\ffmpeg.exe" bin\ >nul
if exist "C:\ffmpeg\bin\ffprobe.exe" copy /Y "C:\ffmpeg\bin\ffprobe.exe" bin\ >nul

python build\make_icon.py
python -m PyInstaller --noconfirm --clean build\convertia_studio.spec

echo.
echo Executable pret : dist\ConvertiaStudio\ConvertiaStudio.exe
endlocal
