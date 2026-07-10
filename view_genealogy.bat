@echo off
REM ====================================================================
REM  Cenobamate Genealogy - 조회 전용(뷰어) 실행
REM  공유폴더(SharePoint/Teams)에 있는 warehouse.sqlite 를 로컬에서 조회만.
REM  (데이터 적재/재빌드는 하지 않음 — 빌더 PC 에서 start_genealogy.bat 로 갱신)
REM
REM  warehouse 경로 지정 우선순위:
REM    1) 이 배치 인자:      view_genealogy.bat "C:\Users\me\...\warehouse.sqlite"
REM    2) 환경변수:          GENEALOGY_WAREHOUSE
REM    3) warehouse_path.txt (리포 루트, 한 줄에 경로)
REM    4) 그래도 없으면 화면 사이드바에서 직접 입력
REM ====================================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not "%~1"=="" set "GENEALOGY_WAREHOUSE=%~1"

echo(
echo == Cenobamate Genealogy (조회 전용) ==
if defined GENEALOGY_WAREHOUSE echo   warehouse: %GENEALOGY_WAREHOUSE%
echo(
echo 조회화면(Streamlit)을 엽니다. 종료하려면 이 창에서 Ctrl+C.
echo(

python -m streamlit run frontend\app.py

echo(
echo Streamlit 이 종료되었습니다.
pause
endlocal
