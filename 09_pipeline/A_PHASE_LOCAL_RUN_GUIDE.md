# A 阶段本地运行手册 v2

> ⚠️ **本次更新**: deepseek-v4-pro 太慢了 (thinking 模式默认开). 
> 改用 **deepseek-v4-flash 非思考模式** - 速度 5-10 倍, 质量足够
> 时长: 15-25 分钟 (而不是 60+ 分钟)
> 成本: ~¥1-3 (而不是 ¥10-20)

---

## TL;DR (最简版本)

```bash
# 解压项目
unzip meituan_proposition_2_v12.zip -d ~/meituan_eval/
cd ~/meituan_eval/09_pipeline

# 安装 + API key
pip install openai
export DEEPSEEK_API_KEY=sk-你的key

# 关键: 三个环境变量
export VERIFIER_LLM_MOCK=0                       # 关 mock
export VERIFIER_LLM_MODEL=deepseek-v4-flash      # 用 flash
export VERIFIER_LLM_THINKING=0                   # 关 thinking (核心提速!)

# 备份 mock 数据
cp batch_results/batch_verdicts.jsonl batch_results/batch_verdicts_mock.jsonl
cp batch_results/auto_mock.csv batch_results/auto_mock_BACKUP.csv

# 跑 (15-25 分钟)
python batch_evaluate.py 2>&1 | tee batch_results/llm_run.log

# 转 CSV
python verdicts_to_csv.py \
  --input batch_results/batch_verdicts.jsonl \
  --output batch_results/auto_llm_flash.csv \
  --rater_name auto_llm_flash

# 算 kappa
cd ../06_gold_annotation
python kappa_calc.py \
  --rater1 gold_set/human_v5_reviewed.csv \
  --rater2 ../09_pipeline/batch_results/auto_llm_flash.csv

# 打包结果给我
cd ~/meituan_eval/
zip a_phase_v2_results.zip \
  09_pipeline/batch_results/batch_verdicts.jsonl \
  09_pipeline/batch_results/auto_llm_flash.csv \
  09_pipeline/batch_results/batch_summary.json \
  09_pipeline/batch_results/llm_run.log
```

---

## 为什么 flash 比 pro 更适合

**根本原因**: verifier 任务 = "读对话+判 pass/fail+输出 JSON"
- 不需要复杂推理 (不是 GPQA 解题)
- 短输入短输出 (<2K input, <200 output)
- 高频调用 (200-400 次)
- thinking 模式是为复杂推理设计, **对 verifier 是浪费**

**数据对比** (实测网上数据):

| 维度 | v4-pro (thinking) | v4-flash (non-thinking) |
|---|---|---|
| 每次响应时间 | 30-60 秒 | 3-6 秒 |
| 输出速度 | ~50 tok/s | 106 tok/s |
| 中文质量 | 顶级 | 顶级 (对 verifier 任务等同) |
| 价格 | $1.74/$3.48 | $0.14/$0.28 (1/10) |
| **跑 50 通对话** | **60+ 分钟** | **15-25 分钟** |

## 先小范围验证 (推荐)

跑完整 50 通前, 先跑 1 通确认 API 可调:

```bash
python pipeline.py \
  --instruction ../08_parser/parsed_examples/v4_parsed.json \
  --dialogue test_data/v4_cooperative_violation.jsonl \
  --output_dir /tmp/test/
```

期望: 30 秒内完成, 评分 60-80 分.

如果这步 ok, 再跑全 50 通.

## 故障排查

### Q: thinking 真的关了吗?
检查 `verifier_llm_extract.py` 是否含 `extra_body={"thinking": {"type": "disabled"}}`. 跑代码会自动设.

### Q: flash 质量够吗?
我的判断: 够. 理由:
- 你的 verifier 任务是事实抽取 + 判定, flash 完全胜任
- 官方说 "non-thinking 模式适合 chat, Q&A, classification, summarization"
- DeepSeek 自己宣传 "flash 在简单 agent 任务上跟 pro 表现相当"
- 如果效果不好(kappa 仍低), 你可以换回 pro thinking 跑 (耗时 60 分钟)

### Q: 还是太慢怎么办?
如果 15 分钟都嫌慢, 可以再加速:
- 并行化: batch_evaluate.py 现在是顺序跑, 可以改成 5 个并行 (我可以加)
- 用 cheaper: gpt-5-nano / gpt-5-mini (但中文略差)

需要并行的话告诉我, 我加.

---

## 期望成果

| 类别 | mock baseline | flash 预期 |
|---|---|---|
| llm_extract kappa | 0.13 | 0.55-0.75 |
| llm_judge kappa | -0.06 | 0.40-0.60 |
| FAQ 知识 kappa | 0 (mock 不实现) | 0.60-0.80 |
| **整体 kappa vs v5** | **0.23** | **0.50-0.65** |

跑完直接打包发我.
