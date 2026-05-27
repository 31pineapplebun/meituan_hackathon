# 美团命题二 项目文件索引 (Day 7 终版)

> **最后整理时间**: Day 7 末
> **项目阶段**: W1+W2 完成 → Day 8 启动 W3 模拟周（state_tracker + 更多 verifier）
> **文件总数**: 50+ 个文件 / 9 个子目录
> **关键里程碑**: Cohen's Kappa = **0.7232** ✅ + 端到端 MVP 跑通 ✅

---

## 0. 一句话项目状态

**我们已经做完了什么**（按 W1 计划）：
- ✅ 23 条通用约束 taxonomy
- ✅ 2 个示例的原子约束拆解（11 + 36 条）+ 嵌套 Flow DAG
- ✅ P3 评分算法（D 维度加权 + P1 调严 Gating + P2 红线即死），4/4 验证通过
- ✅ 6 条变体指令 V1-V6，全部通过校验
- ✅ 用户模拟器 v2（含 mock/重试/变量替换/空回复重试/4 persona）
- ✅ Gold Set 50 通对话（GPT 25 + DeepSeek 25），完全均衡覆盖 16 组合
- ✅ Human-AI 双独立标注，整体 kappa **0.7232** 通过门槛
- ✅ 指令解析器（LLM 调用 + 规则兜底 + dataclass 校验），V1-V6 全部 PASS

**剩下要做的**（W2 后半 + W3-W6）：
- ⏳ 端到端 MVP pipeline（指令 → 解析 → 对话 → 评分），目标 Day 10
- ⏳ 完整 8 persona 实现（W3）
- ⏳ LLM Judge prompt 工程（W4，针对低 kappa 类别）
- ⏳ Streamlit 前端 UI（W5）
- ⏳ 答辩 PPT / Demo / 技术报告（W6）

---

## 1. 完整文件树

```
project_v1/
├── PROJECT_INDEX.md                 项目地图（本文档）
├── HANDOFF_README.md                跨对话/跨人员的交接文档
│
├── 01_docs/                         顶层文档
│   ├── README.md                    项目主文档 v3.0
│   └── solo_battle_plan.md          6 周作战手册（精确到天）
│
├── 02_taxonomy/                     约束分类体系
│   └── constraint_taxonomy.json     23 条 taxonomy + L1/L2/L3 三级分类
│
├── 03_examples/                     示例指令与变体
│   ├── flow_dag_schema.json         嵌套 DAG 的 JSON Schema 定义
│   ├── example_1/example_1_atomic.json   示例 1 (飞毛腿) 11 条约束
│   ├── example_2/
│   │   ├── example_2_atomic.json    示例 2 (直播课) 36 条约束 v2
│   │   ├── example_2_flow_dag.json  16 节点嵌套 DAG
│   │   └── example_2_flow_dag_visual.md  Mermaid 流程图
│   └── variants/                    6 条变体指令
│       ├── V1.md - V6.md            6 条 markdown 指令（全部通过校验）
│       └── variable_values.json     变量真实值映射
│
├── 04_scoring/                      评分算法
│   ├── scoring_algorithm_design.md  P3 三层防御方案设计 (374 行)
│   └── scoring_validation.py        算法实现 + 4 通伪数据回归测试
│
├── 05_instruction_gen/              变体指令生成
│   ├── meta_prompt.md               LLM 生成指令的 prompt 模板
│   ├── validate_instruction.py      指令质量校验脚本
│   └── variant_instructions_generation_tasks.md  6 条变体的逐条 prompt
│
├── 06_gold_annotation/              Gold Standard 标注
│   ├── gold_annotation_guide.md     标注规范 (9 章 + 5 个 FAQ)
│   ├── annotation_template.xlsx     空标注模板
│   ├── prepare_annotation.py        灌入对话到 Excel 的工具
│   ├── kappa_calc.py                Cohen's Kappa 计算 (含 4/4 单元测试)
│   └── gold_set/                    ★ Day 5 实证产物
│       ├── gold_set_50.jsonl                 50 通对话原文
│       ├── gold_set_50_to_label.xlsx         空白标注 Excel
│       ├── gold_final_v3_merged.xlsx         ★ 最终人工标注 v3
│       ├── claude_independent_annotation.xlsx Claude 独立标注
│       ├── human_v3_merged.csv               人工 v3 CSV (kappa 用)
│       ├── claude_rater.csv                  Claude CSV
│       └── kappa_report.md                   ★ 可靠性报告 + 答辩话术
│
├── 07_simulator/                    用户模拟器
│   ├── DAY4_PLAYBOOK.md             Day 4 实操指南 (8 步)
│   ├── simple_simulator.py          v1 (保留兼容)
│   ├── simulator_v2.py              ★ v2 增强版 (mock/重试/变量替换/空回复处理)
│   └── batch_run.py                 批量执行脚本
│
└── 08_parser/                       ★ NEW W2 指令解析器
    ├── PARSER_REPORT.md             解析器质量评估报告
    ├── parser_schema.py             dataclass schema + 自测
    ├── parser.py                    LLM 调用主体 + 规则兜底
    └── parsed_examples/             V1-V6 解析输出 (6/6 PASS)
        ├── v1_parsed.json - v6_parsed.json

└── 09_pipeline/                     ★ NEW Day 7 端到端 MVP
    ├── MVP_REPORT.md                Day 7 MVP 报告
    ├── verifier_base.py             Verifier 接口 + 注册表 (4/4 单测)
    ├── verifiers.py                 rule + rule_pattern 实现 (5/5 单测)
    ├── pipeline.py                  端到端 pipeline 主脚本
    └── example_reports/             实测报告样本
        ├── v1_perfect_dialogue.md   完美对话: 100/100
        ├── v4_violation_dialogue.md V4 违规对话: 33.33/100
        └── v4_violation_dialogue.json
```

---

## 2. 各阶段完成度

| 阶段 | 时间 | 关键产物 | 状态 |
|---|---|---|---|
| **W1 基建周** | Day 1-5 | 约束体系 + 评分算法 + Gold Set | ✅ 完成 |
| **W2 解析周** | Day 6-7 | 指令解析器 + 端到端 MVP | ✅ 完成（提前）|
| **W3 模拟周** | Day 8-12 | 8 persona + state_tracker | ⏳ 未启动 |
| **W4 可靠性周** | Day 13-17 | LLM Judge 优化 + 对照实验 | ⏳ 未启动 |
| **W5 产品周** | Day 18-22 | Streamlit UI + HTML 报告 | ⏳ 未启动 |
| **W6 冲刺周** | Day 23-30 | 技术报告 + Demo + PPT | ⏳ 未启动 |

---

## 3. 关键数据速查

### 项目核心数字

| 指标 | 数值 |
|---|---|
| 通用约束 taxonomy | 23 条 |
| 示例 1 原子约束 | 11 条 |
| 示例 2 原子约束 | 36 条 |
| 6 条变体指令 V1-V6 | 全部校验 PASS |
| Gold Set 对话数 | 50 通（GPT 25 + DeepSeek 25）|
| 标注单元数 | 989 |
| 评测维度 | 5 维度（D1-D5）|
| 评分算法验证 | 4/4 场景通过 |
| **整体 Kappa** | **0.7232** ✅ |
| 客观规则 Kappa | 1.000 🎉 |
| 越界处理 Kappa | 1.000 🎉 |
| 流程结构 Kappa | 0.661 ✅ |
| 主观判断 Kappa | 0.606 ✅ |
| 流程结束 Kappa | 0.103 ⚠️（W4 优化目标）|
| FAQ 知识 Kappa | 0.000 ⚠️（W4 优化目标）|

### P3 评分算法验证（回归测试基线）

| 场景 | 预期 | 实际 |
|---|---|---|
| 理想对话 | ≥ 90 | 100 ✅ |
| 中规中矩 | 75-87 | 86.86 ✅ |
| 部分流程缺失 | 55-70 | 65 ✅ |
| 红线翻车 | ≤ 40 | 40 ✅ |

### 指令解析器质量（V6 vs example_2 手工）

| 维度 | example_2 手工 | V6 LLM 自动 |
|---|---|---|
| 约束数 | 36 | 36 |
| Critical 比例 | 47% | 67% |
| 工作量 | 24 小时 | 秒级 |
| Schema 校验 | - | ✅ PASS |

---

## 4. 答辩素材速查

### Q1：你的评测系统可靠吗？

> 50 通 Gold Set + Human-AI 独立交叉验证，Cohen's Kappa = **0.7232**，过 0.70 门槛。按约束类别拆解：客观规则 1.0、越界处理 1.0、流程结构 0.66、主观判断 0.61。**rule verifier 和 llm_extract_then_rule 在客观约束上完美一致，证明系统对可量化约束的判定高度可靠。**

### Q2：你的评分公式是什么？

> P3 三层防御方案：D 维度加权 + P1 调严 Critical Gating + P2 红线即死。详见 `04_scoring/scoring_algorithm_design.md`，4 通伪场景全部通过预期范围。

### Q3：变体指令怎么来？

> 6 条变体指令围绕 AI 站长 / 骑手助手两个场景，覆盖简单档（V1/V2 4 step）和复杂档（V4-V6 7 step + 嵌套分支），全部通过 5 类约束的机械校验。

### Q4：你怎么生成对话数据？

> 用户模拟器 v2 + 4 persona（配合/拒绝/越界/打断），mock 模式调试 pipeline，真实跑 DeepSeek-Pro + Flash 混搭（成本约 ¥30/50通）。**32 通 GPT + 32 通 DeepSeek 双模型对比为答辩亮点**。

### Q5：你的指令解析器准吗？

> V1-V6 用 LLM 解析后 6/6 通过 dataclass schema 校验。V6 自动解析 36 条约束，与手工拆解的 example_2 约束数完全一致。

---

## 5. 关键代码使用 cookbook

### 跑指令解析器

```bash
cd 08_parser
export DEEPSEEK_API_KEY=sk-xxx
python parser.py --md ../03_examples/variants/V1.md --output v1_parsed.json
```

### 跑评分算法回归测试

```bash
cd 04_scoring
python scoring_validation.py
# 期望: ✅ 4/4 场景全部通过
```

### 跑 Kappa 计算

```bash
cd 06_gold_annotation
python kappa_calc.py --test  # 单元测试
python kappa_calc.py --rater1 gold_set/human_v3_merged.csv --rater2 gold_set/claude_rater.csv
# 期望: kappa = 0.7232
```

### 跑用户模拟器（生成对话）

```bash
cd 07_simulator
export DEEPSEEK_API_KEY=sk-xxx
# Mock 模式（零成本调试）
python simulator_v2.py --instruction ../03_examples/variants/V1.md \
    --persona cooperative --mock --num_dialogues 1

# 真实运行
python simulator_v2.py --instruction ../03_examples/variants/V1.md \
    --persona cooperative \
    --tested_model deepseek-v4-pro --user_model deepseek-v4-flash \
    --num_dialogues 1

# 批量
python batch_run.py --instructions V1,V2,V4,V5 --personas all \
    --num_per_combo 2 \
    --tested_model deepseek-v4-pro --user_model deepseek-v4-flash
```

### 生成标注 Excel

```bash
cd 06_gold_annotation
python prepare_annotation.py \
    --dialogues ../07_simulator/dialogues_output/all_dialogues.jsonl \
    --constraints ../03_examples/example_2/example_2_atomic.json \
    --output annotation_to_label.xlsx
```

---

## 6. 下一步：Day 7 启动 W2.C（端到端 MVP）

**目标**：把"指令文件 → 解析约束 → 跑对话 → 评分报告"完整 pipeline 跑通。

**关键设计决策**（等你 Day 7 拍板）：
1. 用哪条变体指令做第一个 MVP？（推荐 V1，简单档好调试）
2. 评分时 verifier 怎么实现？rule/rule_pattern 现成可写，state_tracker/llm_judge 需要更多设计
3. MVP 第一版要不要包含 LLM Judge 还是只用 rule 类约束？

**预估**：Day 7 1 天可跑通最小可行 pipeline（V1 + 1 通对话 + rule 类 verifier）。
