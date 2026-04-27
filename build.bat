@echo off
echo Installing dependencies...
pip install -r requirements.txt
pip install pyinstaller

echo Building exe...
python -m PyInstaller --onefile --windowed ^
    --name "WechatAutoReply" ^
    --add-data "config.json;." ^
    main.py

echo Done! Check dist\WechatAutoReply.exe
pause
