# Day 4 实操指南

> **目标**：跑出 ≥30 通对话作为 Gold Set 候选 + 启动第一批标注
> **预计工作量**：4-6 小时（含 API 等待时间）
> **预计成本**：$3-10 USD（取决于跑多少 + 用什么模型）

---

## 第一步：环境准备（10 分钟）

### 1.1 安装依赖

```bash
pip install openai anthropic openpyxl
```

> 注：DeepSeek 用 OpenAI 兼容格式，所以 `openai` 包就够用，不需要 deepseek 专用包。

### 1.2 配置 API key

按你要用的模型选一个（或多个）：

```bash
# OpenAI (GPT-4o, GPT-4o-mini)
export OPENAI_API_KEY=sk-xxxxx

# DeepSeek (v4-pro, v4-flash) - 推荐
export DEEPSEEK_API_KEY=sk-xxxxx

# Anthropic (Claude)
export ANTHROPIC_API_KEY=sk-ant-xxxxx
```

Windows PowerShell：
```powershell
$env:DEEPSEEK_API_KEY="sk-xxxxx"
```

### 1.3 选模型策略

**单人作战推荐**：DeepSeek 混搭最划算

| 角色 | 推荐模型 | 成本/通 | 理由 |
|---|---|---|---|
| 被测 assistant | deepseek-v4-pro | ~$0.08 | 评测对象，要有代表性 |
| 用户模拟器 | deepseek-v4-flash | ~$0.02 | 用户回复简单，flash 够用 |

或者用 GPT-4o-mini 一把梭（更便宜但能力略弱）：
| 角色 | 模型 | 成本/通 |
|---|---|---|
| 双方 | gpt-4o-mini | ~$0.003 |

### 1.4 验证环境

```bash
cd 07_simulator
python simulator_v2.py \
  --instruction ../03_examples/variants/V1.md \
  --persona cooperative \
  --tested_model deepseek-v4-pro \
  --user_model deepseek-v4-flash \
  --dry_run
```

应该输出"Persona: cooperative..." 没有"DEEPSEEK_API_KEY 未设置"警告。

---

## 第二步：先 mock 验证 pipeline（5 分钟，零成本）

不调 API 跑一遍，确认所有脚本工作正常：

```bash
cd 07_simulator
python simulator_v2.py \
  --instruction ../03_examples/variants/V1.md \
  --persona cooperative \
  --num_dialogues 1 \
  --output dialogues_output/mock_test.jsonl \
  --mock
```

期望输出：`✓ 11轮 / 平均15.3字 / 耗时0.0s`

---

## 第三步：第一通真实对话（5 分钟，约 $0.10）

**这是最关键的一步**。先跑 1 通真实对话，看模型在 V1 + 配合型 下表现如何。

**DeepSeek 推荐（混搭）**：
```bash
python simulator_v2.py \
  --instruction ../03_examples/variants/V1.md \
  --persona cooperative \
  --tested_model deepseek-v4-pro \
  --user_model deepseek-v4-flash \
  --num_dialogues 1 \
  --output dialogues_output/probe.jsonl
```

**或 OpenAI**：
```bash
python simulator_v2.py \
  --instruction ../03_examples/variants/V1.md \
  --persona cooperative \
  --tested_model gpt-4o-mini \
  --user_model gpt-4o-mini \
  --num_dialogues 1 \
  --output dialogues_output/probe.jsonl
```

跑完打开 `dialogues_output/probe.jsonl`，**人工 review**：
- [ ] assistant 的开场白是否照搬了 Opening Line？
- [ ] 用户的回复是否符合"配合型 persona"的设定？
- [ ] 对话是否自然 stop（不是死循环跑满 max_turns）？
- [ ] 长度约束（30字内）大致遵守了吗？

**如果 ≥3 项检查通过，进第四步。否则回头调 prompt**。

---

## 第四步：Day 4 标准批量（45-90 分钟，约 $2-4 DeepSeek / $0.10 OpenAI）

按 solo_battle_plan.md 的 Day 4 目标，跑出 32 通对话：

**DeepSeek 混搭（推荐，约 $3）**：
```bash
python batch_run.py \
  --instructions V1,V2,V4,V5 \
  --personas all \
  --num_per_combo 2 \
  --tested_model deepseek-v4-pro \
  --user_model deepseek-v4-flash
```

**或 OpenAI（约 $0.10）**：
```bash
python batch_run.py \
  --instructions V1,V2,V4,V5 \
  --personas all \
  --num_per_combo 2 \
  --tested_model gpt-4o-mini \
  --user_model gpt-4o-mini
```

**为什么选 V1/V2/V4/V5**：
- V1/V2 = 简单档（短流程）
- V4/V5 = 复杂档（含分支）
- 跳过 V3（介于中等）和 V6（最复杂，先用 32 通试水）

**预估**：
- 耗时：每通 30-90 秒 × 32 = 30-50 分钟
- 成本：
  - DeepSeek 混搭（pro+flash）：约 $2-4
  - GPT-4o-mini 一把梭：约 $0.10
  - 全 DeepSeek-Pro：约 $5-8（不推荐，user 用 pro 浪费）

跑完后查看：
```bash
ls dialogues_output/
# 应该有 16 个 jsonl 文件 + all_dialogues.jsonl
wc -l dialogues_output/all_dialogues.jsonl
# 期望 32 行
```

---

## 第五步：对话质量抽检（30 分钟）

跑完 32 通后，**抽 5 通仔细看**：

```bash
python -c "
import json
import random
random.seed(42)
with open('dialogues_output/all_dialogues.jsonl') as f:
    dialogues = [json.loads(l) for l in f if l.strip()]
sample = random.sample(dialogues, 5)
for d in sample:
    print(f'\n=== {d[\"dialogue_id\"]} ({d[\"persona_id\"]}) ===')
    for t in d['turns']:
        print(f'  [{t[\"turn\"]}] {t[\"role\"]}: {t[\"content\"]}')
"
```

**检查清单**：
- [ ] persona 行为符合设定（配合型不闹腾，越界型确实问越界问题）
- [ ] assistant 没出现明显违规（如承诺折扣）
- [ ] 流程推进合理（不是 turn 1 就结束，也不是死循环）
- [ ] 多样性够（不是 32 通都长得一样）

如果发现批量问题（如所有对话都跑到 max_turns），**先停下来调 prompt 再批量重跑**，不要硬着头皮往后做。

---

## 第六步：准备标注 Excel（10 分钟）

```bash
cd 06_gold_annotation
python prepare_annotation.py \
  --dialogues ../07_simulator/dialogues_output/all_dialogues.jsonl \
  --constraints ../03_examples/example_2/example_2_atomic.json \
  --output annotation_to_label.xlsx
```

**注意**：上面用的是 example_2 的约束清单（36 条）。这意味着即使是 V1 对话也会被打 36 条约束的判定——其中很多约束会被标为 N/A。这是 Day 4 阶段的快捷做法。**W3 会改成"每条指令各自的约束清单"**。

打开生成的 `annotation_to_label.xlsx`，应该看到：
- **对话原文** Sheet：~440 行（含表头）
- **标注** Sheet：1152 行待标（32 对话 × 36 约束）
- **进度统计** Sheet：实时显示完成率

---

## 第七步：开始标注（Day 4-5 持续）

按 `gold_annotation_guide.md` 的 8 步流程标注。**Day 4 目标：完成第一批 25 通**（约 8-10 小时分两天做完）。

**标注纪律提醒**：
- 每标 5 通休息 5 分钟
- 不确定的标 `review`
- 客观规则（长度、关键词）先标
- 主观判断（语气、节奏）最后标

**记录每天的进度**：

| 日期 | 已标对话数 | 已标单元 | 完成率 |
|---|---|---|---|
| Day 4 上午 | 5 | 180 | 15.6% |
| Day 4 下午 | 12 | 432 | 37.5% |
| Day 5 上午 | 20 | 720 | 62.5% |
| Day 5 下午 | 25 | 900 | 78.1% |

---

## 第八步（可选，Day 5）：让 Claude AI 独立标注

如果 Day 4 你完成了 25 通，**Day 5 启动 AI 第二标注员**：

1. 把 `annotation_to_label.xlsx` 的"对话原文"Sheet 导出为 CSV
2. 让 Claude 独立标注（系统会要求 Claude 看对话 + 约束清单 + 标注规范）
3. 算 human-AI kappa

详见 W4 计划。

---

## 紧急救火规则

### 情况 A：成本超预期
- 立即停下来，切到 mock 模式
- 改用更便宜的模型（gpt-4o-mini 已经是最便宜的）
- 减少 num_per_combo（从 2 改 1）

### 情况 B：对话质量普遍差
- 不要批量重跑，先调单个 persona 的 prompt
- 用 `--num_dialogues 1` 跑单通调试
- 调到满意再批量

### 情况 C：API 经常 429（限流）
- 在 simulator_v2.py 第 ~210 行的 `time.sleep(1)` 改成 `time.sleep(3)`
- 或者分批跑（一次 8 通）

### 情况 D：时间不够
- 砍 num_per_combo 到 1（变成 16 通）
- 砍 instructions 到 V1,V4（变成 8 通）
- 砍 personas 到 cooperative, refuse_persistent（变成 4 通最小可用集）

---

## 完成标准

Day 4 结束时你应该达到：
- [ ] ≥20 通有效对话已生成
- [ ] ≥15 通完成标注
- [ ] kappa 暂不算（需要第二个标注源）
- [ ] 没破财（API 成本 < $15）

如果 Day 4 卡在某一步超 2 小时，**直接来问 Claude 怎么办**，不要硬扛。
