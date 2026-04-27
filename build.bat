@echo off
echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo Building exe...
pyinstaller --onefile --windowed ^
    --name "微信自动回复" ^
    --add-data "config.json;." ^
    main.py

echo Done! Check dist\微信自动回复.exe
pause
