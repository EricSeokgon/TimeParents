@echo off
rem 빌드 설정은 TimeParents.spec 한 곳에서 관리합니다.
pyinstaller --noconfirm TimeParents.spec
echo.
echo Build complete! Check the 'dist' folder for TimeParents.exe
pause
