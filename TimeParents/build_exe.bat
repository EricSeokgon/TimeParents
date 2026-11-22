@echo off
rem 빌드 설정은 TimeParents.spec 한 곳에서 관리합니다.
pushd "%~dp0" || exit /b 1
python -m PyInstaller --noconfirm TimeParents.spec
if errorlevel 1 (
    popd
    exit /b 1
)
popd
echo.
echo Build complete. Distribute dist\TimeParents.exe together with dist\family.
pause
