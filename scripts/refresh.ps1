# 새 MB51 export 를 누적 store 에 적재하고 genealogy 결과 DB 를 재생성한다.
# 사용:  .\scripts\refresh.ps1
#        (data\sap\ 에 EXPORT_*.xlsx 를 넣어두고 실행 — 이미 적재된 파일은 중복 무시)
#
# 선택 인자로 경로 override 가능:
#   .\scripts\refresh.ps1 -Sap "data\sap\*.xlsx" -Store "data\warehouse.sqlite"

param(
  [string]$Sap   = "data\sap\EXPORT_*.xlsx",
  [string]$Store = "data\warehouse.sqlite",
  [string]$BomDb = "data\Cenobamate_BOM_DB_v1.sqlite",
  [string]$Out   = "out\store"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

Write-Host "== 적재 + 재빌드 + 결과DB화 ==" -ForegroundColor Cyan
Write-Host "  SAP   : $Sap"
Write-Host "  Store : $Store"

python src/genealogy_tool.py --ingest --from-store `
  --sap "$Sap" `
  --store "$Store" --bom-db "$BomDb" `
  --out "$Out" --write-db "$Store" --db-replace

if ($LASTEXITCODE -ne 0) { Write-Host "실패 (exit $LASTEXITCODE)" -ForegroundColor Red; exit $LASTEXITCODE }
Write-Host "`n완료. frontend: streamlit run frontend/app.py (warehouse=$Store)" -ForegroundColor Green
