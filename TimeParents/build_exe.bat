@echo off
pyinstaller --onefile --windowed --name "TimeParents" --icon=NONE main.py
echo.
echo Build complete! Check the 'dist' folder for TimeParents.exe
pause
