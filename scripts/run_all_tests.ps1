$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Invoke-Checked {
    param([string]$Command)
    Invoke-Expression $Command
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $Command"
    }
}

Write-Host "== Parser 回归 =="
Invoke-Checked "python `"08_parser/test_parser_regression.py`""

Write-Host "== Verifier 自测 =="
Invoke-Checked "python `"09_pipeline/verifiers.py`""
Invoke-Checked "python `"09_pipeline/verifier_state_tracker.py`""
Invoke-Checked "python `"09_pipeline/verifier_llm_extract.py`""
Invoke-Checked "python `"09_pipeline/verifier_llm_judge.py`""
Invoke-Checked "python `"09_pipeline/suggestion_generator.py`""

Write-Host "== 评分算法回归 =="
Invoke-Checked "python `"04_scoring/scoring_validation.py`""

Write-Host "== 模型聚合回归 =="
Invoke-Checked "python `"09_pipeline/model_evaluation.py`""

Write-Host "== Pipeline 快照回归 =="
Invoke-Checked "python `"tests/test_pipeline_snapshot.py`""

Write-Host "== compileall 健康检查 =="
Invoke-Checked "python -m compileall `"07_simulator`" `"08_parser`" `"09_pipeline`" `"10_streamlit_app`""

Write-Host "All tests passed."

