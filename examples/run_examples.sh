#!/usr/bin/env bash
# Cenobamate Genealogy Tool 실행 예시
# 사용 전: SAP export 경로(SAP)를 본인 파일로 바꾸세요.
set -e
SAP="EXPORT_20260617_141501.xlsx"        # ← 본인 SAP MB51 export 파일로 변경
DB="data/Cenobamate_BOM_DB_v1.sqlite"
TOOL="src/genealogy_tool.py"

echo "[1] 빌드만 — 데이터 로딩·엣지 생성 확인"
python "$TOOL" --sap "$SAP" --bom-db "$DB" --out out

echo "[2] 단건 추적 + HTML (배치값은 normalized_sap_rows.csv에서 선택)"
# python "$TOOL" --sap "$SAP" --bom-db "$DB" --batch <배치값> --direction upstream --html --out out

echo "[3] 전 완제품 일괄 추적 + HTML + XLSX"
python "$TOOL" --sap "$SAP" --bom-db "$DB" --trace-scope all-fp --direction upstream --html --export-xlsx --out out

echo "[4] FP가 없으면 all-leaf 사용"
# python "$TOOL" --sap "$SAP" --bom-db "$DB" --trace-scope all-leaf --direction upstream --html --out out

echo "완료. out/ 폴더 확인."
