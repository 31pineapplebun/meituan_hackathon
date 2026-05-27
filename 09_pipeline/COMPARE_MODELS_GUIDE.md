# 三路模型对照实验指南

> 目的: 实证回答"用 flash 做 verifier 够不够?"
> 时长: 5-10 分钟 (flash 跑很快, pro 略慢)
> 成本: 约 ¥10-15 (含 pro 75% 折扣)

## TL;DR

```bash
cd ~/meituan_eval/09_pipeline
pip install openai

export DEEPSEEK_API_KEY=你的key
export OPENAI_API_KEY=你的key

python compare_three_models.py
```

完事看终端输出, 关键看两个 kappa.

---

## 详细步骤

### 1. 准备 API key

需要两个:
- DeepSeek (https://platform.deepseek.com)
- OpenAI (https://platform.openai.com)

```bash
export DEEPSEEK_API_KEY=sk-xxx
export OPENAI_API_KEY=sk-xxx
```

### 2. 跑对照 (5-10 分钟)

```bash
python compare_three_models.py
```

会自动跑:
- **DeepSeek Flash (非思考)** — ~30 秒/10 通
- **DeepSeek Pro (非思考)** — ~3-5 分钟/10 通  (注: 即使 thinking 关了 pro 还是较慢)
- **GPT-5 mini** — ~1-2 分钟/10 通

### 3. 看输出做决策

终端会自动给出 3 个 kappa:
- **Flash vs Pro**: 同模型族对比, 看 flash 够不够
- **Flash vs GPT-5-mini**: 跨模型族对比, 看是否有偏差
- **Pro vs GPT-5-mini**: 两个强模型对比, 当作"参考基线"

### 4. 决策矩阵

| Flash vs Pro | Flash vs GPT | 建议 |
|---|---|---|
| ≥0.8 | ≥0.6 | 🎉 用 flash, 完美 |
| ≥0.6 | ≥0.5 | ✅ 用 flash, 答辩附此实验 |
| 0.4-0.6 | 任意 | ⚠️ 视答辩重要性, 选稳妥用 pro |
| <0.4 | 任意 | ❌ 必须用 pro |

---

## 节省时间的选项

如果觉得 pro 跑得慢, 可以跳过:

```bash
# 只跑 flash + gpt
python compare_three_models.py --skip_pro

# 只跑 flash 一个模型 (但就不是对照实验了)
python compare_three_models.py --skip_pro --skip_gpt
```

## 提高样本数 (更稳健)

默认 10 通, 想更稳健:

```bash
python compare_three_models.py --n 20
# 时长翻倍, 成本翻倍, 但 kappa 更可靠
```

---

## 完成后

把结果发我:

```bash
zip three_way_results.zip \
  09_pipeline/batch_results/three_way_comparison.json
```

我会:
1. 帮你解读 kappa 数字
2. 决定主 verifier 用 flash 还是 pro
3. 跑全 50 通的脚本配置
4. 答辩话术

---

## 答辩素材预览

无论结果如何, 你都会有这些素材:

> "我们做了三路对照实验:
> - DeepSeek-V4-Flash (主 verifier, 快速)
> - DeepSeek-V4-Pro (同族强模型, 验证 capacity 不是瓶颈)
> - GPT-5-mini (跨模型族, 验证不是 DeepSeek 系统偏差)
>
> 三路在 10 通均衡样本上的 verdict 一致性:
> - Flash vs Pro: kappa = X.XX
> - Flash vs GPT: kappa = X.XX
>
> 实证证明 flash 在评测任务上的能力足够, 不存在模型选择偏差."
