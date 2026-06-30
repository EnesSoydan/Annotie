@echo off
echo Annotie - EXE Derleme
echo ===================================
cd /d "%~dp0"

py -3.12 -m pip install pyinstaller -q

py -3.12 -m PyInstaller Annotie.spec --noconfirm

echo.
echo Derleme tamamlandi! dist/Annotie/ klasorune bakin.
pause
