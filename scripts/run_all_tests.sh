#!/usr/bin/env bash
set -euo pipefail
export PYTHONIOENCODING=utf-8

echo "== Parser 回归 =="
python "08_parser/test_parser_regression.py"

echo "== Verifier 自测 =="
python "09_pipeline/verifiers.py"
python "09_pipeline/verifier_state_tracker.py"
python "09_pipeline/verifier_llm_extract.py"
python "09_pipeline/verifier_llm_judge.py"
python "09_pipeline/suggestion_generator.py"

echo "== 评分算法回归 =="
python "04_scoring/scoring_validation.py"

echo "== 模型聚合回归 =="
python "09_pipeline/model_evaluation.py"

echo "== Pipeline 快照回归 =="
python "tests/test_pipeline_snapshot.py"

echo "== compileall 健康检查 =="
python -m compileall "07_simulator" "08_parser" "09_pipeline" "10_streamlit_app"

echo "All tests passed."

