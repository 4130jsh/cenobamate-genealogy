@echo off
REM ====================================================================
REM  Cenobamate Genealogy - 조회 전용(뷰어) 실행
REM  공유폴더(SharePoint/Teams)의 warehouse.sqlite 를 로컬에서 조회만.
REM  (데이터 적재/재빌드 안 함 — 빌더 PC 에서 start_genealogy.bat 로 갱신)
REM
REM  Python 은 자동 탐색합니다(py 런처 / PATH / Anaconda·Miniconda / python.org).
REM  warehouse 경로 지정 우선순위:
REM    1) 인자:  view_genealogy.bat "C:\...\warehouse.sqlite"
REM    2) 환경변수 GENEALOGY_WAREHOUSE
REM    3) warehouse_path.txt (리포 루트, 한 줄 경로)
REM    4) 그래도 없으면 화면 사이드바에서 직접 입력
REM ====================================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"

call :FINDPY
if not defined PYEXE goto :NOPY

if not "%~1"=="" set "GENEALOGY_WAREHOUSE=%~1"

REM streamlit 없으면 설치
%PYEXE% -c "import streamlit" 1>nul 2>nul
if errorlevel 1 (
  echo [준비] 필요한 패키지(streamlit 등)를 설치합니다... 잠시만요.
  %PYEXE% -m pip install -r requirements-frontend.txt
  if errorlevel 1 goto :PIPFAIL
)

echo(
echo == Cenobamate Genealogy (조회 전용) ==
if defined GENEALOGY_WAREHOUSE echo   warehouse: %GENEALOGY_WAREHOUSE%
echo(
echo 조회화면(Streamlit)이 뜹니다. 브라우저가 자동으로 안 열리면 http://localhost:8501 접속.
echo 종료하려면 이 창에서 Ctrl+C.
echo(

%PYEXE% -m streamlit run frontend\app.py

echo(
echo Streamlit 이 종료되었습니다.
pause
exit /b 0

REM ---- 파이썬 자동 탐색: 성공 시 PYEXE 설정 ----------------------------
:FINDPY
set "PYEXE="
py -3 --version >nul 2>&1 && set "PYEXE=py -3" && exit /b
python --version >nul 2>&1 && set "PYEXE=python" && exit /b
set "PYDIR="
for %%P in (
  "%LOCALAPPDATA%\miniconda3\python.exe"
  "%LOCALAPPDATA%\anaconda3\python.exe"
  "%USERPROFILE%\miniconda3\python.exe"
  "%USERPROFILE%\anaconda3\python.exe"
  "%ProgramData%\miniconda3\python.exe"
  "%ProgramData%\anaconda3\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
  "%LOCALAPPDATA%\Programs\Python\Python310\python.exe"
) do if exist "%%~P" if not defined PYDIR set "PYDIR=%%~dpP"
if not defined PYDIR exit /b
set "PYEXE=python"
set "PATH=%PYDIR%;%PYDIR%Library\bin;%PATH%"
exit /b

:NOPY
echo(
echo [오류] Python 을 찾지 못했습니다.
echo   - python.org 에서 Python 설치 (설치 화면에서 "Add python.exe to PATH" 체크) 후 다시 실행,
echo   - 또는 Anaconda/Miniconda 가 설치돼 있으면 "Anaconda Prompt" 에서 이 폴더로 이동해
echo     python -m streamlit run frontend\app.py 실행.
echo(
pause
exit /b 1

:PIPFAIL
echo(
echo [오류] 패키지 설치에 실패했습니다. 인터넷/프록시 또는 권한을 확인하세요.
echo   수동 설치:  %PYEXE% -m pip install -r requirements-frontend.txt
echo(
pause
exit /b 1
