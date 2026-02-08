@echo off
chcp 65001 >nul
echo ========================================
echo  스마트 파일 리네이머 GitHub 배포 스크립트
echo ========================================
echo.

:: Git 설치 확인
git --version >nul 2>&1
if errorlevel 1 (
    echo [오류] Git이 설치되어 있지 않습니다!
    echo.
    echo Git을 설치하려면:
    echo   1. https://git-scm.com/download/win 에서 다운로드
    echo   2. 설치 후 터미널 재시작
    echo.
    pause
    exit /b 1
)

:: Git 저장소 초기화 확인
if not exist ".git" (
    echo [1/5] Git 저장소 초기화...
    git init
    echo.
)

:: 사용자 정보 확인
git config user.name >nul 2>&1
if errorlevel 1 (
    echo [!] Git 사용자 정보를 설정해주세요:
    echo     git config --global user.name "Your Name"
    echo     git config --global user.email "your@email.com"
    echo.
)

:: 파일 스테이징
echo [2/5] 파일 스테이징...
git add .
echo.

:: 커밋
echo [3/5] 커밋 생성...
set /p commit_msg="커밋 메시지 입력 (기본: Initial release v1.0.0): "
if "%commit_msg%"=="" set commit_msg=Initial release v1.0.0
git commit -m "%commit_msg%"
echo.

:: 원격 저장소 확인
git remote -v | find "origin" >nul 2>&1
if errorlevel 1 (
    echo [4/5] 원격 저장소 설정...
    echo.
    echo GitHub에서 새 저장소를 생성한 후 URL을 입력하세요.
    echo 예: https://github.com/USERNAME/SmartFileRenamer.git
    echo.
    set /p remote_url="GitHub 저장소 URL: "
    if not "%remote_url%"=="" (
        git remote add origin %remote_url%
        git branch -M main
    ) else (
        echo [!] URL이 입력되지 않았습니다. 나중에 수동으로 설정하세요.
        echo     git remote add origin https://github.com/USERNAME/SmartFileRenamer.git
    )
) else (
    echo [4/5] 원격 저장소 이미 설정됨
)
echo.

:: 푸시
echo [5/5] GitHub에 푸시...
git push -u origin main
if errorlevel 1 (
    echo.
    echo [!] 푸시 실패. 다음을 확인하세요:
    echo     - GitHub 로그인 필요 (Personal Access Token 사용)
    echo     - 저장소 권한 확인
    echo.
    echo 수동 푸시 명령어:
    echo     git push -u origin main
) else (
    echo.
    echo ========================================
    echo  GitHub 배포 완료!
    echo ========================================
)

echo.
pause
