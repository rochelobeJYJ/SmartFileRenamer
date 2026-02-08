@echo off
chcp 65001 >nul
echo ========================================
echo  스마트 파일 리네이머 빌드 스크립트
echo ========================================
echo.

:: 가상환경 확인
if exist venv (
    echo [1/4] 가상환경 활성화...
    call venv\Scripts\activate.bat
) else (
    echo [!] 가상환경이 없습니다. 시스템 Python 사용
)

:: 의존성 설치
echo [2/4] 의존성 설치...
pip install pyinstaller --quiet
pip install -r requirements.txt --quiet

:: 빌드
echo [3/4] EXE 빌드 중... (시간이 걸릴 수 있습니다)
pyinstaller SmartFileRenamer.spec --noconfirm --clean

:: 결과 확인
if exist "dist\SmartFileRenamer.exe" (
    echo.
    echo ========================================
    echo  빌드 성공!
    echo  위치: dist\SmartFileRenamer.exe
    echo ========================================
    
    :: 크기 확인
    for %%A in ("dist\SmartFileRenamer.exe") do echo  크기: %%~zA bytes
    echo.
    
    :: ZIP 생성
    echo [4/4] ZIP 파일 생성 중...
    if exist "SmartFileRenamer_v1.0.0.zip" del "SmartFileRenamer_v1.0.0.zip"
    powershell -Command "Compress-Archive -Path 'dist\SmartFileRenamer.exe' -DestinationPath 'SmartFileRenamer_v1.0.0.zip'"
    
    if exist "SmartFileRenamer_v1.0.0.zip" (
        echo  ZIP 생성 완료: SmartFileRenamer_v1.0.0.zip
        for %%A in ("SmartFileRenamer_v1.0.0.zip") do echo  크기: %%~zA bytes
    )
) else (
    echo.
    echo [오류] 빌드 실패! 로그를 확인하세요.
)

echo.
pause
