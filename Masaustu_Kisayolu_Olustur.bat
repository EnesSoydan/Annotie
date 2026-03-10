@echo off
echo YOLO Etiket Editoru - Masaustu Kisayolu Olusturuluyor...
cd /d "%~dp0"

set TARGET=%~dp0dist\YOLOEtiketEditoru\YOLOEtiketEditoru.exe
set SHORTCUT=%USERPROFILE%\Desktop\YOLO Etiket Editoru.lnk

powershell -Command "$ws = New-Object -ComObject WScript.Shell; $s = $ws.CreateShortcut('%SHORTCUT%'); $s.TargetPath = '%TARGET%'; $s.WorkingDirectory = '%~dp0dist\YOLOEtiketEditoru'; $s.Description = 'YOLO Etiket Editoru'; $s.Save()"

echo Kisayol olusturuldu: %SHORTCUT%
pause
