@echo off
echo Annotie - EXE Derleme
echo ===================================
cd /d "%~dp0"

pip install pyinstaller -q

python -m PyInstaller Annotie.spec --noconfirm

echo.
echo Derleme tamamlandi! dist/Annotie/ klasorune bakin.
pause
