# 项目全面测评清单（当前版）

> 目标：提交前确保“评得准、跑得稳、演示可复现”。

## 1) 后端快速回归（必跑）

```bash
bash scripts/run_all_tests.sh
```

期望：
- Parser 回归通过
- 5 类 verifier 自测通过
- P3 评分验证通过
- 关键模块导入与基础 smoke 通过

## 2) Streamlit 手工验收（必跑）

### 2.1 一站式主流程 (`app.py`)
- 选择任意指令后，展示约束数、关键约束数与分布图
- 勾选 persona 后可点击“开始评测模型”
- 快速演示模式秒级产出能力画像
- 完整运行模式在缺 key 时给出明确提示

### 2.2 单通详查页 (`pages/1_📂_单通详查.py`)
- 可从主页跳转并看到逐约束 verdict 与 evidence
- 切换不同 persona 对话时数据刷新正确

### 2.3 关于页 (`pages/2_📖_关于.py`)
- 关键可靠性指标与技术说明正常展示

## 3) 数据完整性（必跑）

```bash
# v6 人工标注
python - <<'PY'
from pathlib import Path
p=Path("06_gold_annotation/gold_set/human_v6_reviewed.csv")
print("exists", p.exists(), "lines", sum(1 for _ in p.open(encoding="utf-8")))
PY

# 批跑结果
python - <<'PY'
from pathlib import Path
print(Path("09_pipeline/batch_results/auto_llm_flash.csv").exists())
print(Path("09_pipeline/batch_results/three_way_summary.json").exists())
PY
```

## 4) 稳定性检查（建议）

- 批量评测支持断点续跑（中断后重跑可跳过已完成对话）
- `batch_summary.json` 包含 `llm_stats`（calls/retries/failures/p95/p99）
- `.gitignore` 能拦截 `__pycache__` 与 `*.pyc`

## 5) 提交门禁

- 禁止提交 `__pycache__/` 和 `*.pyc`
- 文档路径与 UI 现状一致（不再引用旧 5 Tab 流程）
- 关键改动附最小验证记录（命令 + 结果）
