# 美团对话外呼任务评测系统

> **能发现人类盲区的工业级 LLM Judge**
>
> 把模型评测从"靠人审" 变成 "机器审 + 人监督" — 30 秒/通,¥0.20/通,跟人工 kappa = 0.45,跨模型对照 kappa = 0.81

---

## 🎯 它解决什么问题

美团每天有大量外呼对话(骑手培训通知 / 商家差评回访 / 飞毛腿合同等)需要质检。**人工评测又慢又贵又不一致** — 一通对话人工评 15-30 分钟,每通 ¥10-30,而且两个人对同一通对话的判定 kappa 才 0.4。

本系统接受 (任务指令 Markdown + 对话 JSONL) 作为输入,**自动产出**:
- 0-100 分综合评分 + 5 维度细分
- 每条约束的 pass/fail 判定 + 证据 + 改进建议
- 完整可解释报告 (JSON / Markdown / HTML 三种格式)

---

## 📊 核心数据

### 评测可靠性 (50 通真实对话 × 1055 条约束)

| 指标 | 数值 | 含义 |
|---|---|---|
| **客观约束 kappa** | **1.0000** | 字数 / 禁用词等规则约束 — 完美对齐人工 |
| **D3 约束遵循度 kappa** | **0.8400** | 顶级一致性 |
| **整体 vs 人工 kappa** | **0.4483** | 落在 LLM-as-Judge 业界标准 0.3-0.6 区间 |
| **三路 LLM 互查 kappa** | **0.81** | DeepSeek-Flash / DeepSeek-Pro / GPT-5-mini 跨模型族对照 |

### 工程性能

| 指标 | 数值 |
|---|---|
| 单通评测耗时 | **30 秒** (vs 人工 15-30 分钟) |
| 单通成本 | **¥0.20** (vs 人工 ¥10-30) |
| 5 个 Verifier 单测 | **全部通过** |
| Parser 兼容性 | **V1-V6 + 2 个官方 sample 全部解析成功** |
| 用户 Persona 覆盖 | **8 个** (合作 / 拒绝 / 越界 / 打断 / 状态 / 模糊 / 对抗 / 提问) |

---

## 🏗️ 技术架构

```
[任务指令 .md]
      ↓
   [Parser]  ─── 支持 V1-V6 + 官方 sample 两种 markdown 格式
      ↓
[约束清单 JSON]  ─── 16-36 条原子约束, 5 类 verifier
      ↓
[对话 .jsonl] ──→ [Pipeline] ←── 5 类 Verifier 分层判定
                       ↓
                [P3 三层评分算法]  ─── 加权汇总 + Critical 钳制 + Red-line 钳制
                       ↓
            [评分报告 JSON / MD / HTML]
                       ↓
                [Streamlit UI] ─── 评委演示界面
```

### 核心创新点

**1. 5 类 Verifier 分层判定 (ROI 最大化)**

| Verifier 类型 | 用途 | LLM 调用 |
|---|---|---|
| `rule` | 字数 / 占位符等纯客观 | 0 次 |
| `rule_pattern` | 禁用词 / 必含变量 | 0 次 |
| `state_tracker` | 流程步骤识别 | 关键词优先 + LLM 兜底 |
| `llm_extract_then_rule` | 事实抽取后规则判定 | 1 次 |
| `llm_judge` | 主观判断 | 1 次 |

**价值**: 客观约束不浪费 LLM 调用 — **省 60% 成本**

**2. P3 三层评分防御**

- **L1 加权分**: D1 流程(25%) + D2 任务(25%) + D3 约束(20%) + D4 知识(15%) + D5 对话(15%)
- **L2 Critical 钳制**: Critical 通过率 < 90% → 上限 85
- **L3 Red-line 钳制**: 任何 Red-line 违规 → 上限 40

**价值**: 防止"全 D3 满分但 D1 全 fail"的虚高分

**3. 三路 LLM 对照实验**

- DeepSeek-V4-Flash (主, 快)
- DeepSeek-V4-Pro (同族对照)
- GPT-5-mini (跨族对照)

**价值**: 排除单一模型偏差 — 三路平均 kappa = 0.81

**4. 评测系统反过来发现人类盲区** (4 轮标注迭代)

- v3 (Day 5): 初标, kappa = 0.72 ⚠️ 虚高 (两人犯同样错误)
- v4 (Day 9): LLM 评测**独立发现** 5 条约束的标注瑕疵 → 自动修订 73 处
- v5 (Day 9 末): 手工复核 12 处
- v6 (Day 10): 全量重标 1055 条 → **kappa = 0.45 (真实可靠数字)**

**意义**: 系统不只模仿人,**还能纠正人**

---

## 🚀 快速开始

### 环境准备

```bash
# Python 3.10+
pip install -r 10_streamlit_app/requirements.txt
# 含: streamlit / plotly / pandas / openai
```

### 启动 Streamlit Demo (推荐)

```bash
cd 10_streamlit_app
streamlit run app.py
# 浏览器自动打开 http://localhost:8501
```

### 一键端到端测试 (命令行)

```bash
# 设置 API key (有真实 LLM 评测才用,否则 Mock 模式也能跑)
export DEEPSEEK_API_KEY=你的key

cd 09_pipeline

# 跑评测 (Mock 模式秒出,LLM 模式 ~30 秒)
python pipeline.py \
  --instruction ../08_parser/parsed_examples/official_1_feimaotui_parsed.json \
  --dialogue official_demo/official_1_feimaotui_cooperative_demo.jsonl \
  --output_dir results/

# 输出 3 个文件:
# results/score_report_xxx.json   - 完整数据
# results/score_report_xxx.md     - Markdown 报告
# results/score_report_xxx.html   - 浏览器可看的精美报告
```

### 演示路径 (评委 5 分钟体验)

```
Tab 1 上传指令      选"🏢 官方 Sample 1"  →  解析出 15 条约束 + 5 类 verifier 饼图
       ↓
Tab 2 用户模拟器    选 "🏢 官方 sample 1" + "⚔️ 对抗型"  →  生成挑刺型用户对话
       ↓
Tab 3 评测         选"💬 用模拟器刚生成的" + LLM 模式  →  30 秒出 5 维度评分
       ↓
Tab 4 报告         评分卡 + 雷达图 + 优化建议  →  下载 JSON / MD / HTML
```

---

## 📂 项目结构

```
meituan_eval/
├── 01_docs/                    # 设计文档 + 计划 + 测试清单
│   ├── README.md               # 内部作战手册 (870 行)
│   ├── TEST_CHECKLIST.md       # 提交前全面测评清单
│   ├── solo_battle_plan.md     # 6 周开发计划
│   └── day7_plan.md            # 各阶段日计划
│
├── 02_taxonomy/                # 23 类约束分类体系
│   └── constraint_taxonomy.json
│
├── 03_examples/                # 任务指令 (Markdown)
│   ├── variants/               # V1-V6 自定义变体
│   └── official/               # 官方 sample 1 + 2 (脱敏)
│
├── 04_scoring/                 # P3 评分算法
│   └── scoring_validation.py   # 4/4 测试通过
│
├── 05_instruction_gen/         # 指令自动生成 (W6 雏形)
│
├── 06_gold_annotation/         # Gold Set 人工标注
│   ├── annotation_guide_v2.md  # 454 行标注规范
│   ├── per_constraint_guide.md # 648 行逐条规则
│   ├── kappa_calc.py           # Kappa 计算工具
│   └── gold_set/
│       ├── gold_set_50.jsonl   # 50 通真实对话
│       └── human_v6_reviewed.csv  # 1055 条 v6 标注 (最终)
│
├── 07_simulator/               # 用户模拟器 (8 persona)
│   ├── simulator_v2.py
│   └── batch_run.py
│
├── 08_parser/                  # 指令解析器
│   ├── parser.py                       # 574 行 (兼容多种 markdown)
│   ├── test_parser_regression.py        # 8/8 通过
│   └── parsed_examples/                # V1-V6 + 官方 2 个预解析 JSON
│
├── 09_pipeline/                # 评测主流程 + 报告
│   ├── pipeline.py                       # 评测主入口
│   ├── verifiers.py                      # 规则类 (rule + rule_pattern)
│   ├── verifier_state_tracker.py         # 流程追踪
│   ├── verifier_llm_extract.py           # LLM 抽取
│   ├── verifier_llm_judge.py             # LLM 判定
│   ├── suggestion_generator.py           # 优化建议生成
│   ├── html_report.py                    # HTML 报告生成
│   ├── batch_evaluate.py                 # 批量评测
│   ├── compare_three_models.py           # 三路 LLM 对照
│   ├── RELIABILITY_REPORT_v2.md          # kappa 可靠性报告
│   ├── TECHNICAL_REPORT_OUTLINE.md       # 技术方案大纲
│   ├── official_demo/                    # 官方 sample 演示对话 + 报告
│   └── batch_results/                    # 1055 verdict + 三路对照结果
│
└── 10_streamlit_app/           # Streamlit UI (5 Tab)
    ├── app.py
    └── pages/
        ├── 1_📋_上传指令.py
        ├── 2_💬_用户模拟器.py
        ├── 3_🧪_评测.py
        ├── 4_📊_报告.py
        └── 5_📖_关于.py
```

---

## 💡 关键模块说明

### Parser (`08_parser/parser.py`)

输入: 任务指令 Markdown
输出: 原子约束清单 JSON

**支持 2 种 markdown 格式**:
- 数字编号约束: `1. 每次回复不超过 20 字`
- 短横线约束: `- 每次回复不超过 20 字`
- FAQ 分隔符: `→` / `:` / `：`

**自动分类**: 每条约束被分到 5 类 verifier 之一 + 5 个评分维度之一

### Simulator (`07_simulator/simulator_v2.py`)

输入: 指令 + Persona + 模型选择
输出: 对话 JSONL

**8 个 Persona**:
| 核心 4 个 | 扩展 4 个 |
|---|---|
| 🤝 cooperative | 🚗 state_busy (在开车/忙) |
| 😤 refuse_persistent | 🤔 ambiguous (含糊不清) |
| 🌀 out_of_scope | ⚔️ adversarial (挑刺/抱怨) |
| ✋ interruption | ❓ probing (狂问细节) |

### Pipeline (`09_pipeline/pipeline.py`)

主入口,串联所有 verifier + 评分算法 + 报告生成。

```bash
python pipeline.py \
  --instruction <指令.json> \
  --dialogue <对话.jsonl> \
  --output_dir <输出目录>
```

---

## 📚 关键文档

| 文档 | 内容 |
|---|---|
| [`01_docs/README.md`](01_docs/README.md) | 内部作战手册 (设计决策 / 修订记录) |
| [`01_docs/TEST_CHECKLIST.md`](01_docs/TEST_CHECKLIST.md) | 提交前测评清单 (7 类测试 200+ 检查点) |
| [`09_pipeline/RELIABILITY_REPORT_v2.md`](09_pipeline/RELIABILITY_REPORT_v2.md) | Kappa 可靠性完整报告 (219 行) |
| [`09_pipeline/TECHNICAL_REPORT_OUTLINE.md`](09_pipeline/TECHNICAL_REPORT_OUTLINE.md) | 技术方案文档大纲 (15 页规划) |
| [`06_gold_annotation/annotation_guide_v2.md`](06_gold_annotation/annotation_guide_v2.md) | 标注规范 v2.0 (454 行) |
| [`06_gold_annotation/per_constraint_guide.md`](06_gold_annotation/per_constraint_guide.md) | 逐条约束规则 (648 行) |

---

## 🎯 适用场景

### 场景 A: 美团内部质检
每天数万通外呼对话自动评估,节省人工质检成本。

### 场景 B: 客服 SaaS 平台
作为评测基础设施,卖给其他外呼平台 (饿了么 / 京东到家等)。

### 场景 C: 外呼 AI 公司评测工具
给做外呼对话 AI 的公司当评测 API,按调用计费。

---

## 🚀 未来路线

- **持续校准**: 基于真实业务数据迭代 LLM Judge prompt
- **场景扩展**: 英文外呼 + 方言识别
- **闭环增强**: 业务描述 → 自动生成评测指令
- **能力延伸**: ASR 端到端评测 + Human-in-the-Loop 持续优化

---

## ⚙️ 技术栈

- **后端**: Python 3.10+, OpenAI SDK
- **LLM**: DeepSeek-V4-Flash (主) / DeepSeek-V4-Pro / GPT-5-mini
- **前端**: Streamlit + Plotly
- **评估**: scikit-learn (kappa 计算)
- **数据**: 50 通真实对话 / 1055 条 v6 人工标注 / 三路 LLM 对照结果

---

## 📧 项目信息

- **赛题**: 美团黑客松 命题二 — 复杂指令下的多轮对话评测系统
- **目标**: 一等奖以上 + 商业星途大奖
- **日期**: 2026 年

---

> 💡 **快速验证项目**: 跑一遍 `01_docs/TEST_CHECKLIST.md` 第 1 类后端单测 (5 分钟),全部通过即代表核心技术健全。
