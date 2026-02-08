@echo off
chcp 65001 >nul
echo ========================================
echo  스마트 파일 리네이머 릴리즈 빌드
echo ========================================
echo.

:: 버전 설정
set VERSION=1.0.0
set RELEASE_DIR=release
set ZIP_NAME=SmartFileRenamer_v%VERSION%.zip

:: 가상환경 활성화
if exist venv (
    echo [1/5] 가상환경 활성화...
    call venv\Scripts\activate.bat
) else (
    echo [!] 가상환경이 없습니다. 시스템 Python 사용
)

:: 의존성 설치
echo [2/5] 의존성 설치...
pip install pyinstaller --quiet
pip install -r requirements.txt --quiet

:: 빌드
echo [3/5] EXE 빌드 중... (약 1-2분 소요)
pyinstaller SmartFileRenamer.spec --noconfirm --clean

:: 빌드 결과 확인
if not exist "dist\SmartFileRenamer.exe" (
    echo.
    echo [오류] 빌드 실패! 로그를 확인하세요.
    pause
    exit /b 1
)

:: 릴리즈 폴더 생성
echo [4/5] 릴리즈 패키지 생성...
if exist "%RELEASE_DIR%" rmdir /s /q "%RELEASE_DIR%"
mkdir "%RELEASE_DIR%"

:: 파일 복사
copy "dist\SmartFileRenamer.exe" "%RELEASE_DIR%\" >nul
copy "README.md" "%RELEASE_DIR%\" >nul
copy "LICENSE" "%RELEASE_DIR%\" >nul

:: ZIP 생성
echo [5/5] ZIP 파일 생성 중...
if exist "%ZIP_NAME%" del "%ZIP_NAME%"
powershell -Command "Compress-Archive -Path '%RELEASE_DIR%\*' -DestinationPath '%ZIP_NAME%' -CompressionLevel Optimal"

:: 결과 출력
echo.
echo ========================================
echo  빌드 완료!
echo ========================================
echo.
echo  EXE 파일: dist\SmartFileRenamer.exe
for %%A in ("dist\SmartFileRenamer.exe") do echo  EXE 크기: %%~zA bytes
echo.
echo  ZIP 파일: %ZIP_NAME%
for %%A in ("%ZIP_NAME%") do echo  ZIP 크기: %%~zA bytes
echo.
echo  릴리즈 폴더: %RELEASE_DIR%\
echo    - SmartFileRenamer.exe
echo    - README.md
echo    - LICENSE
echo.
echo ========================================
echo  GitHub Releases에 %ZIP_NAME% 업로드하세요!
echo ========================================
echo.
pause
