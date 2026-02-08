@echo off
chcp 65001 >nul
echo ========================================
echo  스마트 파일 리네이머 빌드 (Anaconda)
echo ========================================
echo.

:: Anaconda 환경 확인
where conda >nul 2>&1
if errorlevel 1 (
    echo [오류] Anaconda가 활성화되지 않았습니다!
    echo Anaconda Prompt에서 이 스크립트를 실행하세요.
    pause
    exit /b 1
)

echo [1/5] Anaconda 환경 확인...
python --version
echo.

:: 의존성 설치
echo [2/5] 의존성 설치 중...
pip install pyinstaller --quiet
pip install PySide6 --quiet
pip install pdfminer.six --quiet
pip install olefile --quiet
echo 의존성 설치 완료
echo.

:: 빌드
echo [3/5] EXE 빌드 중... (약 1-3분 소요)
echo 잠시 기다려 주세요...
echo.
python -m PyInstaller SmartFileRenamer.spec --noconfirm --clean

:: 빌드 결과 확인
if not exist "dist\SmartFileRenamer.exe" (
    echo.
    echo [오류] 빌드 실패! 위의 오류 메시지를 확인하세요.
    pause
    exit /b 1
)

echo.
echo [4/5] 빌드 성공!
for %%A in ("dist\SmartFileRenamer.exe") do echo EXE 크기: %%~zA bytes
echo.

:: 릴리즈 패키징
set VERSION=1.0.0
set RELEASE_DIR=release
set ZIP_NAME=SmartFileRenamer_v%VERSION%.zip

echo [5/5] 배포 패키지 생성 중...
if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%RELEASE_DIR%"

copy "dist\SmartFileRenamer.exe" "%RELEASE_DIR%\" >nul
copy "README.md" "%RELEASE_DIR%\" >nul
copy "LICENSE" "%RELEASE_DIR%\" >nul

if exist "%ZIP_NAME%" del "%ZIP_NAME%"
powershell -Command "Compress-Archive -Path '%RELEASE_DIR%\*' -DestinationPath '%ZIP_NAME%' -CompressionLevel Optimal"

echo.
echo ========================================
echo  빌드 완료!
echo ========================================
echo.
echo  EXE: dist\SmartFileRenamer.exe
echo  ZIP: %ZIP_NAME%
echo.
echo  ZIP 파일을 GitHub Releases에 업로드하세요!
echo ========================================
echo.
pause
