# CLAUDE.md — 项目交接文档

> 这份文档是给 Claude Code 的项目上下文。开始任何工作前请先读完。
> 核心工作原则：**先验证再说话** — 不空谈，亲自读数据 / 跑代码 / 找真 bug，验证后再下结论。

---

## 0. 一句话项目定位

美团黑客松命题二参赛项目：**对话外呼任务的指令遵循自动评测系统**。
输入「任务指令 + 待测模型」，系统自动模拟多场景对话 → 评测 → 产出「模型能力画像」(0-100 分 + 可解释报告 + 优化方向)。

**目标**：一等奖以上 + 商业星途大奖。

---

## 1. 当前状态 (重要 — 别重复造轮子)

技术后端**已经基本完成且是生产级**。**不要再加新功能**，重点是：
1. 修 bug / 提质量（如果发现问题）
2. 写技术报告正文 + 演示视频（这是初赛评分主依据，还没做）

### 已完成且验证过的能力
- ✅ Parser：解析任务指令 markdown → 约束清单（支持 V1-V6 变体 + 2 个官方 sample，8/8 回归测试通过）
- ✅ 8 个用户模拟器 Persona（合作/拒绝/越界/打断/状态/模糊/对抗/提问）
- ✅ 5 类 Verifier 分层判定（rule / rule_pattern / state_tracker / llm_extract_then_rule / llm_judge）
- ✅ P3 三层评分算法（加权 + Critical 钳制 + 红线钳制，4/4 场景测试通过）
- ✅ 模型级评测聚合（多通对话 → 模型能力画像）
- ✅ 一站式 Streamlit UI（选指令 → 选模型+场景 → 一键评测 → 画像）
- ✅ 生产级保障：LLM 调用重试 / seed 可复现 / 结果缓存 / 并发评测 / 自一致性投票 / 鲁棒 JSON 解析 / 同义词容错 / 空对话语义保护
- ✅ Kappa 可靠性验证（整体 0.4483 / 客观约束 1.0 / D3=0.84 / 三路 LLM 互查 0.81）

### 还没做（真正要投入的地方）
- ⏳ 技术报告正文（15 页，目前只有大纲 `09_pipeline/TECHNICAL_REPORT_OUTLINE.md`）
- ⏳ 商业价值章节（冲商业星途，目前几乎空白）
- ⏳ 演示视频脚本 + 录制

---

## 2. 目录结构

```
meituan_eval/
├── CLAUDE.md                    # 本文档
├── 01_docs/                     # 设计文档 + 计划 + 测试清单
│   ├── README.md                #   内部作战手册 (870 行, 决策日志)
│   └── TEST_CHECKLIST.md        #   提交前测评清单
├── 02_taxonomy/                 # 23 类约束分类体系
├── 03_examples/                 # 任务指令 (markdown)
│   ├── variants/                #   V1-V6 自定义变体 + variable_values.json
│   └── official/                #   官方 sample 1(飞毛腿) + 2(课程发布), 脱敏
├── 04_scoring/
│   └── scoring_validation.py    # P3 评分算法 (4/4 测试通过)
├── 05_instruction_gen/          # 指令自动生成 (W6 雏形, 暂不动)
├── 06_gold_annotation/          # Gold Set 人工标注
│   ├── kappa_calc.py            #   kappa 计算工具
│   └── gold_set/
│       ├── gold_set_50.jsonl    #   50 通真实对话
│       └── human_v6_reviewed.csv#   1055 条 v6 标注 (最终版)
├── 07_simulator/
│   └── simulator_v2.py          # 用户模拟器 (8 persona)
├── 08_parser/
│   ├── parser.py                # 指令解析器 (574 行)
│   ├── test_parser_regression.py#   回归测试 (8/8)
│   └── parsed_examples/         #   V1-V6 + 官方 2 个的预解析 JSON
├── 09_pipeline/                 # 评测主流程 (核心)
│   ├── llm_client.py            #   ⭐统一 LLM 客户端 (重试/seed/缓存/解析) — 所有 LLM 调用走这里
│   ├── pipeline.py              #   评测主入口 run_pipeline()
│   ├── verifier_base.py         #   verifier 注册表 + dispatch
│   ├── verifiers.py             #   rule + rule_pattern
│   ├── verifier_state_tracker.py#   流程追踪 (关键词 + 同义词)
│   ├── verifier_llm_extract.py  #   LLM 抽取后规则判定
│   ├── verifier_llm_judge.py    #   LLM 主观判定 (含自一致性投票)
│   ├── suggestion_generator.py  #   优化建议生成
│   ├── html_report.py           #   HTML 报告生成
│   ├── model_evaluation.py      #   ⭐模型级评测聚合 (run_fast_demo / run_full_evaluation / aggregate_model_report)
│   ├── build_demo_data.py       #   从真实 flash 数据生成预置演示报告
│   ├── model_demo/              #   V1/V2/V4/V5 预置模型报告 (快速演示用)
│   └── batch_results/           #   1055 条真实 flash 评测 + 三路对照结果
└── 10_streamlit_app/
    ├── app.py                   # ⭐一站式主页 (选指令→选模型→评测→画像)
    └── pages/
        ├── 1_📂_单通详查.py      #   看某通对话逐约束判定
        └── 2_📖_关于.py          #   技术原理 + kappa 数据
```

---

## 3. 架构与数据流

```
[任务指令 .md]
   ↓ parser.py (解析)
[约束清单 JSON]  (16-36 条原子约束, 每条标了 verifier 类型 + 评分维度 + 是否 critical/红线)
   ↓
[待测模型 M] → simulator_v2.py (8 persona 模拟用户) → 多通对话 JSONL
   ↓
pipeline.py: run_pipeline(instruction, dialogue)
   ├─ 对每条约束 dispatch 到对应 verifier (并发执行)
   │    ├─ rule / rule_pattern        → 0 次 LLM 调用 (纯规则)
   │    ├─ state_tracker              → 关键词+同义词匹配, LLM 兜底
   │    ├─ llm_extract_then_rule      → 1 次 LLM (抽取事实) + 规则判定
   │    └─ llm_judge                  → LLM 判定 (critical 约束走 3 次自一致性投票)
   ├─ compute_p3_score()  → 三层评分 (加权 / Critical 钳制 / 红线钳制)
   └─ suggestion_generator → 优化建议
   ↓
model_evaluation.py: aggregate_model_report()  (多通聚合)
   ↓
[模型能力画像]: 综合分 + 各 persona 表现 + 最弱约束 + 自动诊断
   ↓
app.py (Streamlit UI 展示) / html_report.py (下载报告)
```

**关键设计**：所有 LLM 调用统一走 `llm_client.py`，重试/缓存/seed 集中治理，verifier 不直接碰 SDK。

---

## 4. 怎么跑 / 怎么测

### 跑 UI
```bash
cd 10_streamlit_app
export DEEPSEEK_API_KEY=sk-xxx     # 完整模式真跑需要; 快速演示不需要
streamlit run app.py
```
- **快速演示模式**：读 `model_demo/` 预置的真实评测结果，秒出。只有 V1/V2/V4/V5 有预置数据（4 个核心 persona）。
- **完整模式**：真调待测模型生成对话 + 真评测。官方 sample 只能用完整模式（没预置数据）。

### 跑全套测试 (改完代码必跑，确认没改坏)
```bash
export VERIFIER_LLM_MOCK=1     # mock 模式, 不调真实 API

# 1. parser 回归
cd 08_parser && python3 test_parser_regression.py        # 期望: ✅ 全部通过 (8/8)

# 2. 5 类 verifier 单测
cd ../09_pipeline
python3 verifiers.py
python3 verifier_state_tracker.py
python3 verifier_llm_extract.py
python3 verifier_llm_judge.py
python3 suggestion_generator.py

# 3. P3 评分
cd ../04_scoring && python3 scoring_validation.py        # 期望: ✅ 4/4 场景通过

# 4. 统一 LLM 客户端 (含鲁棒 JSON 解析测试)
cd ../09_pipeline && python3 llm_client.py               # 期望: ✅ 自测完成

# 5. 模型级聚合
python3 model_evaluation.py                              # 期望: ✅ 聚合逻辑自测通过
```

### 端到端冒烟测试 (验证 dispatch 注册链路 — 重要)
```bash
export VERIFIER_LLM_MOCK=1
cd 09_pipeline
python3 -c "
import json, glob
from pipeline import run_pipeline
from collections import Counter
instr = json.load(open('../08_parser/parsed_examples/official_1_feimaotui_parsed.json'))
dlg = json.loads(open(glob.glob('official_demo/*feimaotui_cooperative*.jsonl')[0]).readline())
r = run_pipeline(instr, dlg)
vds = Counter(v['verdict'] for v in r['verdict_details'])
print('verdict 分布:', dict(vds))
assert vds.get('error', 0) == 0, 'error 应为 0!'   # ← 关键断言
print('得分:', r['score_report']['final_score'])
"
```

---

## 5. 环境变量一览

| 变量 | 默认 | 作用 |
|---|---|---|
| `DEEPSEEK_API_KEY` | 无 | DeepSeek 模型 key (完整模式必需) |
| `OPENAI_API_KEY` | 无 | GPT 模型 key |
| `ANTHROPIC_API_KEY` | 无 | Claude 模型 key |
| `VERIFIER_LLM_MOCK` | `1` | =1 不调真实 API (调试/测试); =0 真跑 |
| `VERIFIER_LLM_MODEL` | `deepseek-v4-flash` | verifier 用哪个模型判定 |
| `VERIFIER_LLM_THINKING` | `0` | DeepSeek 是否开思考模式 |
| `LLM_SEED` | `42` | 固定随机种子 (可复现) |
| `LLM_MAX_RETRIES` | `3` | LLM 调用失败重试次数 |
| `LLM_TIMEOUT` | `60` | 单次 LLM 调用超时(秒) |
| `LLM_CACHE` | `1` | 是否启用结果缓存 |
| `LLM_SELF_CONSISTENCY` | `1` | critical 约束是否走自一致性投票 |
| `PIPELINE_MAX_WORKERS` | `8` | verifier 并发数 |

---

## 6. 踩过的坑 (别重蹈覆辙)

1. **verifier 注册装饰器装错位**（已修，但要警惕）：`@register("llm_judge")` 必须装在 `verify_llm_judge` 上，不能因为在它前面插了别的函数(如 `_vote_judge`)就装错对象。改 `verifier_llm_judge.py` 时务必跑端到端冒烟测试（第 4 节），确认 dispatch 调对了函数、error=0。单独测函数不够，要测注册链路。

2. **mock 模式 vs 真实模式分数差异大**：mock 模式下 llm_judge 类约束返回 `not_implemented`（占 ~30%），分数偏低且不代表真实能力。**演示和答辩必须用完整模式 (LLM)**，不能用 mock。

3. **空对话语义**：对话生成失败（如 API key 没设）时，对话是 0 轮，评分返回 `final_score=None` + `evaluable=False`，**不是 0 分**。0 分会被误解成"模型很差"。聚合层会把这种场景排除并提示。

4. **kappa 悖论**：整体 kappa=0.4483 被"类别不平衡"系统性低估了。真实标注一致率是 **81.8%**。答辩要讲清楚：客观约束 kappa=1.0，整体受 kappa 悖论影响，故同时报告一致率。这是技术深度，不是缺陷。

5. **打包/交付**：改完代码先跑全套测试 + 端到端冒烟，确认 error=0 再说"做完了"。

---

## 7. Kappa / 数据的真实数字 (答辩用，都已核实可复现)

| 指标 | 数值 | 说明 |
|---|---|---|
| 客观约束 kappa | 1.0000 | 字数/禁用词等规则约束，完美对齐人工 |
| D3 约束遵循 kappa | 0.84 | 顶级一致 |
| 整体 vs 人工 kappa | 0.4483 | 受 kappa 悖论影响被低估 |
| 实际一致率 (po) | 81.8% | 703 有效对中 575 一致 — 更能反映真实质量 |
| 三路 LLM 互查 kappa | 0.81 | DeepSeek-Flash/Pro + GPT-5-mini 跨模型族 |
| 4 轮标注迭代 | v3(-0.19/61%)→v4(0.13/73%)→v5(0.13/73%)→v6(0.45/82%) | 逐轮上升，可复现 |

复现 kappa：
```bash
cd 06_gold_annotation
python3 kappa_calc.py --rater1 gold_set/human_v6_reviewed.csv \
  --rater2 ../09_pipeline/batch_results/auto_llm_flash.csv
```

---

## 8. 当前任务

> 工作原则（每个任务都适用）：
> 1. **先验证再说话** — 不确定就读代码/数据，不要猜
> 2. 每改一处代码 → 跑对应测试 + 第 4 节的端到端冒烟（确认 `error=0`）→ 再说"做完了"
> 3. **不要加新功能**，聚焦：验证现有功能正确 → 修 bug → 写文档
> 4. 改 `verifier_llm_judge.py` 时**必须**跑端到端冒烟（第 4 节），因为它的 `@register` 容易装错位

---

### 阶段 1：验证现有系统真的能跑（先做，1-2 小时）

> 目的：在写任何文档前，先确认手里的系统是真能用的，拿到真实分数。

- [ ] **1.1 跑全套测试**（第 4 节所有命令），确认全绿。任何一个挂了先修，修完重跑。
- [ ] **1.2 跑端到端冒烟测试**（第 4 节最后那段），确认 `error=0`。这是验证最近修的 register bug 真的好了。
- [ ] **1.3 完整模式真跑一次**：
  - `export DEEPSEEK_API_KEY=<你的key>`，`cd 10_streamlit_app && streamlit run app.py`
  - 选「官方 Sample 1 - 飞毛腿」+ deepseek-v4-flash + 勾「合作型」「越界提问型」+ **完整运行**模式
  - 跑完到「单通详查」页，确认：① 没有 `error: TypeError` ② llm_judge 类约束有正常 pass/fail + 真实证据 ③ 分数稳定（多跑一次分数应基本一致，因为有 seed）
  - **把这次的真实分数记下来**，写报告要用真实数据，不要用之前被 bug 污染的 27/65 分。
- [ ] **1.4 如果发现 llm_judge 判错**（不是 error，是判定内容不合理）：读 `verifier_llm_judge.py` 的 prompt（`_build_judge_prompt`），看 anchor examples 是否够清晰，针对性优化。改完重跑 1.3。

---

### 阶段 2：技术报告正文（核心交付物，2-3 天）

> 初赛是线上评审，技术报告是评分主依据。目前只有大纲 `09_pipeline/TECHNICAL_REPORT_OUTLINE.md`，要写成正文。
> 评审 4 维度：创新性 / 完整性 / 应用效果 / 商业价值。

- [ ] **2.1 读这些再动笔**（先验证，别凭空写）：
  - `09_pipeline/TECHNICAL_REPORT_OUTLINE.md`（大纲，照它的结构展开）
  - `09_pipeline/RELIABILITY_REPORT_v2.md`（kappa 可靠性数据）
  - `01_docs/README.md`（决策日志，里面有为什么这么设计的理由）
  - 本文档第 3 节（架构）、第 7 节（真实数字）
- [ ] **2.2 写正文**，产出 `01_docs/技术报告.md`，章节建议：
  1. 问题定义（外呼质检痛点：人工慢/贵/不一致）
  2. 系统架构（用第 3 节的数据流图）
  3. 核心技术点：① 5 类 Verifier 分层（客观约束 0 LLM 调用、更准更稳；主观约束才用 LLM。两官方样本约 4 成约束可不调 LLM，估算——别再写"省60%"那个站不住的旧数字）② P3 三层评分 ③ 8 Persona 模拟器 ④ 模型级评测聚合
  4. 工程可靠性（重试/seed/缓存/并发/投票/同义词，对应 `关于页` 那张表）
  5. 评测可靠性（kappa 数据 + **诚实讲 kappa 悖论**：客观 1.0 / 整体 0.45 / 实际一致率 81.8% / 三路 0.81）
  6. 4 轮标注迭代故事（评测系统反过来发现人类标注盲区，可复现）
  7. 应用效果（用 1.3 跑出的真实分数 + 模型能力画像截图）
- [ ] **2.3 写作纪律**：所有数字必须能复现（用第 7 节的命令验证），不编造。不确定的数据宁可不写。

---

### 阶段 3：商业价值章节（冲商业星途，1 天）

> 商业星途大奖看商业价值（占 30%）。目前几乎空白，这是短板。

- [ ] **3.1 产出 `01_docs/商业价值.md`**，至少覆盖：
  - 市场规模：外呼质检市场测算（美团/饿了么/京东到家等平台的外呼量级）
  - 成本对比：本系统 ~¥0.2/通、30 秒 vs 人工 ~¥10-30/通、15-30 分钟（数字在 README 里核对）
  - 竞品对比：和通用 LLM 评测工具（Promptfoo / LangSmith / DeepEval）的差异——本系统是**中文外呼场景专用 + 可解释到约束级 + 模型级画像**
  - 护城河：为什么是美团做（真实业务数据 + 场景 know-how + 23 类约束体系）
  - 落地路径：内部质检 → 对外 SaaS → 评测 API
- [ ] **3.2 诚实原则**：市场数字标注为"估算"，不编造精确到个位的假数据（这是之前定下的纪律）。

---

### 不要做的事
- ❌ 不要加新 verifier / 新 persona / 新评测维度
- ❌ 不要改 kappa 数据或评分算法去"刷高分"（0.45 + 81.8% 一致率已经够，诚实讲就是加分）
- ❌ 不要做多语言 / 语音 / 自动指令生成（赛题只要中文文本，做了跑题）
- ❌ 没验证过的结论不要写进报告

