@echo off
echo YOLO Etiket Editoru - EXE Derleme
echo ===================================
cd /d "%~dp0"

pip install pyinstaller -q

pyinstaller --onedir --windowed --name "YOLOEtiketEditoru" ^
    --add-data "src;src" ^
    --hidden-import PySide6.QtCore ^
    --hidden-import PySide6.QtGui ^
    --hidden-import PySide6.QtWidgets ^
    --hidden-import yaml ^
    --hidden-import PIL ^
    --hidden-import numpy ^
    main.py

echo.
echo Derleme tamamlandi! dist/YOLOEtiketEditoru/ klasorune bakin.
pause
