@echo off
echo Annotie - Masaustu Kisayolu Olusturuluyor...
cd /d "%~dp0"

set TARGET=%~dp0dist\Annotie\Annotie.exe
set SHORTCUT=%USERPROFILE%\Desktop\Annotie.lnk

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%~dp0dist\Annotie'; $s.Description = 'Annotie'; $s.Save()"

echo Kisayol olusturuldu: %SHORTCUT%
pause
