@echo off
REM ====================================================================
REM  Cenobamate Genealogy - 데이터 적재 + 프런트엔드 실행 (한 방, 빌더용)
REM  더블클릭하면: data\sap 의 신규 MB51 적재→재빌드→Streamlit 조회화면
REM  경로 override:  start_genealogy.bat  "data\sap\*.xlsx"  "data\warehouse.sqlite"
REM
REM  Python 은 자동 탐색합니다(py 런처 / PATH / Anaconda·Miniconda / python.org).
REM ====================================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"

call :FINDPY
if not defined PYEXE goto :NOPY

REM 필요한 패키지(엔진 pandas/openpyxl + 프런트 streamlit) 확인/설치
%PYEXE% -c "import streamlit, openpyxl, numpy" 1>nul 2>nul
if errorlevel 1 (
  echo [준비] 필요한 패키지를 설치합니다... 잠시만요.
  %PYEXE% -m pip install -r requirements.txt -r requirements-frontend.txt
  if errorlevel 1 goto :PIPFAIL
)

set "SAP=%~1"
if "%SAP%"=="" set "SAP=data\sap\EXPORT_*.xlsx"
set "STORE=%~2"
if "%STORE%"=="" set "STORE=data\warehouse.sqlite"
set "BOMDB=data\Cenobamate_BOM_DB_v1.sqlite"
set "OUT=out\store"

echo(
echo == Cenobamate Genealogy ==
echo   SAP   : %SAP%
echo   Store : %STORE%
echo(

REM --- 1) 신규 MB51 이 있으면 적재 + 재빌드 + 결과DB화 ---
set "HAVE_SAP="
for %%F in (%SAP%) do set "HAVE_SAP=1"

if defined HAVE_SAP (
  echo [1/2] 데이터 적재 + 재빌드 중...
  %PYEXE% src\genealogy_tool.py --ingest --from-store ^
    --sap "%SAP%" --store "%STORE%" --bom-db "%BOMDB%" ^
    --out "%OUT%" --write-db "%STORE%" --db-replace
  if errorlevel 1 (
    echo(
    echo [오류] 재빌드 실패. 위 메시지를 확인하세요.
    pause
    exit /b 1
  )
  echo     완료.
) else (
  echo [1/2] data\sap 에 EXPORT_*.xlsx 가 없어 적재는 건너뜁니다.
  if not exist "%STORE%" (
    echo(
    echo [오류] warehouse 도 없습니다: %STORE%
    echo        data\sap 에 MB51 export 를 넣고 다시 실행하세요.
    pause
    exit /b 1
  )
  echo     기존 warehouse 로 바로 조회화면을 엽니다.
)

REM --- 2) 프런트엔드(Streamlit) 실행 ---
echo(
echo [2/2] 조회화면(Streamlit)이 뜹니다. 브라우저가 자동으로 안 열리면 http://localhost:8501 접속.
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
echo     python src\genealogy_tool.py ... 및 python -m streamlit run frontend\app.py 실행.
echo(
pause
exit /b 1

:PIPFAIL
echo(
echo [오류] 패키지 설치에 실패했습니다. 인터넷/프록시 또는 권한을 확인하세요.
echo   수동 설치:  %PYEXE% -m pip install -r requirements.txt -r requirements-frontend.txt
echo(
pause
exit /b 1
