@echo off
REM ====================================================================
REM  Cenobamate Genealogy - 데이터 적재 + 프런트엔드 실행 (한 방)
REM  더블클릭하면: data\sap 의 신규 MB51 적재→재빌드→Streamlit 조회화면
REM  경로 override:  start_genealogy.bat  "data\sap\*.xlsx"  "data\warehouse.sqlite"
REM ====================================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"

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
  python src\genealogy_tool.py --ingest --from-store ^
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
echo [2/2] 조회화면(Streamlit)을 엽니다. 종료하려면 이 창에서 Ctrl+C.
echo(
python -m streamlit run frontend\app.py

echo(
echo Streamlit 이 종료되었습니다.
pause
endlocal
