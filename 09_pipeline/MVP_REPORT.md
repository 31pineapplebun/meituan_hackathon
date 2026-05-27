# Day 7-8 端到端 MVP 报告

> **完成时间**: Day 7 (rule + rule_pattern) + Day 8 (state_tracker)
> **目标**: 把 "指令文件 → 解析约束 → 跑对话 → 评分报告" 全 pipeline 跑通
> **状态**: ✅ 完成

---

## 1. 关键数字

| 指标 | 数值 |
|---|---|
| Pipeline 实际跑通 | ✅ V1 + V4 各 1 通对话 |
| Verifier 类型实现 | **3/5** (rule + rule_pattern + state_tracker) |
| 单元测试 | verifier_base 4/4 + verifiers 5/5 + state_tracker 5/5 = **14/14 ✅** |
| V1 完美对话评分 | **100/100** (7 条约束 pass) |
| V4 含违规对话评分 | **62.43/100** (7 pass, 3 fail) |
| 整体回归测试 | 6/6 ✅ |

---

## 2. Day 7 vs Day 8 对比

| 维度 | Day 7 V1 | Day 8 V1 | Day 7 V4 | Day 8 V4 |
|---|---|---|---|---|
| 评估约束数 | 3 | **7** | 3 | **10** |
| D1 流程遵循度 | N/A | **100** | N/A | **85.7** |
| D3 约束遵循度 | 100 | 100 | 33.3 | 33.3 |
| 最终分数 | 100 | **100** | 33.33 | **62.43** |
| Critical 通过率 | 100% | 100% | 100% | **87.5%** |

**进步**:
- Day 7 → Day 8: 评估覆盖从 D3 单维 → D1+D3 双维
- V4 分数从 33→62 反映模型综合表现 (流程做得不错, 但 D3 字数/禁用词违规)

---

## 2. 架构总览

```
INPUT:
  parsed_instruction.json (来自 08_parser)
  dialogue.json           (来自 07_simulator 或 Gold Set)

PIPELINE (09_pipeline/pipeline.py):
  Step 1: 加载约束 + 对话
  Step 2: 对每条约束跑 dispatch() → 路由到对应 verifier
          - rule        → verifiers.verify_rule
          - rule_pattern → verifiers.verify_rule_pattern
          - 其他        → 返回 not_implemented (跳过)
  Step 3: P3 评分算法 (D + P1 + P2 三层防御)
  Step 4: 生成 JSON + Markdown 双格式报告

OUTPUT:
  score_report_<dlg_id>.json (机器友好)
  score_report_<dlg_id>.md   (人类可读 + 优化建议)
```

---

## 3. 关键设计决策

### 决策 1: Verifier 注册表机制

**好处**:
- 新 verifier 只需 `@register("xxx")` + 实现函数
- 主 pipeline 代码 0 改动
- 未实现的 verifier 优雅降级为 `not_implemented` 而非错误

### 决策 2: 4 状态 verdict

| Verdict | 含义 | 计入分母吗 |
|---|---|---|
| pass | 约束被遵守 | ✅ |
| fail | 约束被违反 | ✅ |
| na | 约束未被触发 | ❌ |
| not_implemented | 该 verifier 未实现 | ❌ |
| error | 执行异常 | ❌ |

**这是关键设计**: 把 not_implemented 排除在分母外, 这样 Day 8+ 增加新 verifier 时, 分数不会因为更严格而下降.

### 决策 3: 软边界

- 字数限制: 允许 +5 字软边界（如 V4 限制 20 字, 实际超过 25 字才算违规）
- 违规率门槛: 30% 以下不算 fail（防止 1-2 个超长 turn 拖累整体）

---

## 4. 实测验证（V4 真实数据）

### 输入
- 指令: V4 (商家出餐慢核实)
- 对话: V4_cooperative_1779201688_000 (来自 Gold Set, GPT 生成)
- 26 条约束

### 输出
- **最终得分**: 33.33 / 100
- **维度分**: D3 约束遵循度 33.3, 其他 N/A
- **违规明细**:
  - V4_C01 长度: 3/4 = 75% 超字数 (turn7=45字, turn3=37字, turn9=31字)
  - V4_C07 禁用词: turn9 用了"好的"

### 数据说明 Pipeline 工作正常

- ✅ rule verifier 正确识别长度违规
- ✅ rule_pattern verifier 正确识别禁用词
- ✅ P3 算法正确加权
- ✅ Markdown 报告含证据链
- ✅ 优化建议精确到 constraint_id + 具体 turn

---

## 5. 已实现的 Verifier 详情

### rule verifier (覆盖 2 种约束子类型)

1. **字数限制**: 自动从约束 name/source_text 提取限制
   - "30字以内" → max=30
   - "15-20字" → min=15, max=20
2. **占位符残留检查**: 检查对话中 ${xxx} 是否被替换
   - 这是修复 Day 4 bug 的延伸——评测系统自动捕获该类违规

### rule_pattern verifier (覆盖 2 种约束子类型)

1. **禁用词**: 检查"好的"/"哈哈"/"嘿嘿"/"嘻嘻"
2. **开场白合规**: 检查关键词（如"负责人"）

---

## 6. 限制与改进方向

### Day 7 MVP 的局限

| 局限 | 影响 | 解决时机 |
|---|---|---|
| 只支持 rule + rule_pattern | 14/16 V1 约束跳过 | Day 8 实现 state_tracker |
| 维度评分只有 D3 有效 | D1/D2/D4/D5 全 N/A | Day 8-9 |
| 关键词抽取靠启发式 | 召回率低 | Day 9 用 LLM |
| 无成本控制 | LLM verifier 跑全数据集会贵 | Day 10 加 batch+cache |

### W3 优化路线

1. **Day 8**: state_tracker (流程结构类约束) - 解锁 D1 流程遵循度
2. **Day 9**: llm_extract_then_rule + llm_judge - 解锁 D2/D4/D5
3. **Day 10**: 优化 prompt 工程 + 引入 Gold Set 反推
4. **Day 11+**: 在完整 50 通 Gold Set 上跑批量评测, 跟人工标注对照

---

## 7. 答辩素材

### Q: Pipeline 是什么样的?

> "我们的端到端 pipeline 把 markdown 指令通过 LLM 解析为 16 条原子约束, 然后用注册表机制分发到 5 种 verifier 中对应的实现. 跑完 1 通对话约 0.5 秒（rule 类）, 输出 0-100 分数 + 5 维度雷达图 + 精确到 turn 的优化建议."

### Q: 评分系统真的能抓违规吗?

> "用 V4 商家出餐慢指令跑了一通 GPT 生成的对话, 系统准确识别出:
> - 长度违规: 3/4 turn 超字数, 平均 38 字
> - 禁用词违规: turn9 出现'好的'
> 最终分数 33.33/100, 直接反映模型在该指令上的能力不足. 答辩 demo 可现场跑."

### Q: 为什么 14/16 约束跳过了?

> "Day 7 MVP 实现了 2/5 verifier (rule + rule_pattern). 这是 lean 做法——先有可跑通的 pipeline. 跳过的约束不影响已实现的部分判定, Day 8+ 陆续增加 state_tracker/llm_judge 后会全部覆盖. 完整路线见 day7_plan.md."

---

## 8. 文件清单

```
09_pipeline/
├── verifier_base.py        Verifier 接口 + 注册表 (含 4/4 单元测试)
├── verifiers.py            rule + rule_pattern 实现 (含 5/5 单元测试)
├── pipeline.py             端到端 pipeline 主脚本
└── example_reports/
    ├── v1_perfect_dialogue.md       完美对话报告(对照)
    ├── v4_violation_dialogue.md     含违规对话报告(主例)
    └── v4_violation_dialogue.json   机器友好格式
```

## 9. 立即可用的命令

```bash
cd 09_pipeline

# 跑 V1 评测
python pipeline.py \
  --instruction ../08_parser/parsed_examples/v1_parsed.json \
  --dialogue /path/to/dialogue.jsonl \
  --output_dir reports/

# 跑 V4 评测 (含违规, 推荐演示用)
python pipeline.py \
  --instruction ../08_parser/parsed_examples/v4_parsed.json \
  --dialogue /path/to/v4_dialogue.jsonl \
  --output_dir reports/
```
