@echo off
echo Annotie - EXE Derleme
echo ===================================
cd /d "%~dp0"

py -3.12 -m pip install pyinstaller -q

py -3.12 -m PyInstaller Annotie.spec --noconfirm
py -3.12 -m PyInstaller AnnotieUpdater.spec --noconfirm
if not exist dist\Annotie mkdir dist\Annotie
copy /Y dist\AnnotieUpdater.exe dist\Annotie\AnnotieUpdater.exe >nul

echo.
echo Derleme tamamlandi! dist/Annotie/ klasorune bakin.
echo Not: Release ZIP'inin icinde Annotie.exe ve AnnotieUpdater.exe bulunmali.
pause
