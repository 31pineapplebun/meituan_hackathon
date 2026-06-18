# Day 7+ 作战计划 (Day 6 末梳理)

> **核心原则**: 先验证再说话, 不空谈
> **时间**: Day 6 末 → Day 30
> **截止**: 6 周作战手册保留, 但根据 Day 5 提前达标动态调整

---

## 一、当前位置（实证）

### 已完成（W1 + W2 半）

| 周 | 内容 | 状态 |
|---|---|---|
| W1.1 | 约束体系 + 评分算法 | ✅ |
| W1.2 | 2 示例拆解 + Flow DAG | ✅ |
| W1.3 | 6 变体指令 V1-V6 | ✅ |
| W1.4 | 用户模拟器 + 50 通 Gold Set | ✅ |
| W1.5 | Human-AI 双标注 + kappa 0.72 | ✅ |
| W2.1 | 指令解析器 | ✅（提前完成）|

### 未完成（W2 半 + W3-W6）

| 周 | 任务 | 优先级 |
|---|---|---|
| W2.2 | 端到端 MVP pipeline | 🔥 关键路径 |
| W3 | 完整 8 persona + state_tracker | 高 |
| W4 | LLM Judge 优化 + 对照实验 | 中 |
| W5 | 前端 UI + HTML 报告 | 中 |
| W6 | 答辩 PPT + Demo + 技术报告 | 高 |

---

## 二、Day 7 任务: 端到端 MVP（核心）

### 2.1 MVP 目标定义

"端到端 MVP"指的是这条 pipeline：

```
[指令 V1.md]
   ↓ (Day 6 已成功: 解析器)
[V1 解析为 JSON: 16 约束 + 4 Flow]
   ↓ (Day 4 已成功: 模拟器)
[跑 1 通对话 → JSONL]
   ↓ (Day 7 要做: Verifier)
[逐条约束判定 pass/fail]
   ↓ (Day 2 已成功: 评分算法)
[P3 三层算法 → 总分 + 维度分]
   ↓ (Day 7 要做: 报告生成)
[评分报告: 0-100 分 + 优化方向]
```

### 2.2 Day 7 工作分解

**核心要做的事是写"Verifier 注册表"**——把每种 verifier 类型对应到具体函数。

| 子任务 | 估时 | 难度 |
|---|---|---|
| 2.2.1 Verifier 接口设计 | 30 min | 低 |
| 2.2.2 实现 `rule` verifier（字数）| 30 min | 低 |
| 2.2.3 实现 `rule_pattern` verifier（关键词）| 30 min | 低 |
| 2.2.4 实现 `state_tracker` verifier（流程覆盖）| 1 h | 中 |
| 2.2.5 实现 `llm_extract_then_rule` verifier | 1 h | 中 |
| 2.2.6 实现 `llm_judge` verifier（最难）| 1.5 h | 高 |
| 2.2.7 Pipeline 串联脚本 | 1 h | 中 |
| 2.2.8 跑 V1 + 1 通对话 + 输出报告 | 30 min | 低 |
| **合计** | **6-7 h** | - |

### 2.3 MVP 简化策略（建议）

**Day 7 第一版只实现 2 种 verifier**：
- `rule` 和 `rule_pattern`（覆盖约 50% 约束）

**剩余 verifier 标"未实现，跳过该约束"**，跑出第一版报告。这是 lean 做法——先有个能跑的 pipeline，再迭代每种 verifier。

**好处**：
- Day 7 当天就有能演示的 demo
- 评委演示时"先看长度违规检测，再说我们 W3 会扩展到 LLM Judge"

---

## 三、Day 8-12: W3 模拟周

### 3.1 W3 真正要做的事

W3 不是"再跑一遍模拟器"——Day 4-5 已经跑过了 32+32 通。W3 是 **3 件升级**：

| 升级 | 内容 |
|---|---|
| W3.1 | 4 persona → 8 persona（加 elderly/impatient/skeptical/complaining）|
| W3.2 | `state_tracker` 真正能跑（Day 7 可能是 mock）|
| W3.3 | 把模拟数据扩展到 V3+V6（之前跳过的两条指令）|

### 3.2 W3 验收标准

- 8 persona 全部能在 mock 模式跑通
- 至少 1 个 persona 在真实 API 跑过 5 通对话
- state_tracker 能正确识别 V1-V6 的 step 覆盖
- 数据集扩展到 6 条指令 × 8 persona = 至少 48 个组合

---

## 四、Day 13-17: W4 可靠性周

### 4.1 针对 Day 5 发现的优化方向

Day 5 kappa 报告暴露了两个低 kappa 类别（< 0.2）：
- **流程结束**（适时挂断）：kappa 0.103
- **FAQ 知识**：kappa 0.000

### 4.2 W4 具体任务

| 任务 | 目标 |
|---|---|
| 4.1 拆解"适时终结"为多个子约束 | 把模糊判断改成可量化条件 |
| 4.2 改进 LLM Judge prompt（加入判例）| 提升主观类约束 kappa |
| 4.3 对照实验：rule vs LLM Judge | 数据证明哪种 verifier 更优 |
| 4.4 多模型评测（DeepSeek vs GPT vs Claude）| 产出"模型对比榜单" |

### 4.3 W4 验收标准

- 流程结束类 kappa 从 0.10 提升到 ≥ 0.50
- FAQ 类 kappa 从 0.00 提升到 ≥ 0.40
- 整体 kappa 从 0.72 提升到 ≥ 0.78

---

## 五、Day 18-22: W5 产品周

### 5.1 前端目标

直播原话明确要求"前端 UI"。我们做 **Streamlit 单页 demo**：

| 页面 | 功能 |
|---|---|
| Tab 1 上传指令 | 拖 V1.md 进去 |
| Tab 2 解析预览 | 显示自动拆出的约束 + 雷达图 |
| Tab 3 跑对话 | 选 persona + 模型, 显示 streaming 对话 |
| Tab 4 评分报告 | 0-100 总分 + 5 维度雷达图 + 优化建议 |
| Tab 5 历史对比 | 多模型评测榜单 |

### 5.2 HTML 报告（备用方案）

Streamlit 跑不通时的兜底方案——纯 HTML + JS 报告。

---

## 六、Day 23-30: W6 冲刺周

### 6.1 必须产出

| 交付物 | 说明 |
|---|---|
| **技术报告**（10-15 页 PDF）| 系统架构 + 关键算法 + 实验数据 |
| **答辩 PPT**（15-20 页）| 含 5 个 demo 截图 + 关键数字 |
| **Demo 视频**（3 分钟）| Streamlit 完整流程录屏 |
| **代码包**（GitHub repo 或 zip）| 含 README + 完整复现指南 |

### 6.2 Mock 答辩 3 次

| 时间 | 目的 |
|---|---|
| Day 26 | 自己讲一遍，找逻辑漏洞 |
| Day 28 | 找朋友讲一遍，看是否能 5 分钟内说清楚价值 |
| Day 30 | 最终 mock，对着评委角度想问题 |

---

## 七、关键风险 + 应对

### 风险 1：W4 LLM Judge 优化没效果

**应对**：诚实披露——"流程结束/FAQ kappa 低反映了 LLM Judge 的固有难度，我们的系统将这部分识别为后续优化方向"。这其实是答辩亮点（不是缺点）。

### 风险 2：Streamlit UI 来不及

**应对**：HTML + JS 静态报告兜底。需求只要求"前端 UI"，没指定必须用 Streamlit。

### 风险 3：API 成本超预算

**应对**：
- LLM Judge 优先用 GPT-4o-mini（便宜）
- 评测数据集大批量跑时用 DeepSeek-Flash
- 答辩时强调"DeepSeek-Pro 评测对象 + Flash 模拟器"是成本最优混搭

### 风险 4：被问"你为什么是单人作战"

**应对**：诚实说"组队失败，单人把项目推进完整"——这反而成了故事。

---

## 八、当前最大的决策点（Day 7 拍板）

### 决策点 1：MVP 范围

**Q：第一版 MVP 实现几种 verifier？**

- A. 只 rule + rule_pattern（最少 2 种，1 天可完成）
- B. + state_tracker（3 种，1.5 天）
- C. + 全部（5 种，3 天，含 LLM Judge）

**建议 A**：先有可跑通的 pipeline，再迭代。

### 决策点 2：MVP 测试用例

**Q：MVP 用哪条指令 + 哪通对话验证？**

- A. V1 + Gold Set 中 V1_cooperative 的 1 通（最简单）
- B. V4 + Gold Set 中 V4_interruption 的 1 通（中等难度）
- C. 全部 50 通（验证 robust 性）

**建议 A**：第一版只需证明 pipeline 通，不需要 robust 测试。

### 决策点 3：MVP 输出格式

**Q：第一版报告什么形式？**

- A. JSON（机器友好）
- B. Markdown（人类可读）
- C. HTML（评委演示可用）

**建议 A + B**（双输出）：MVP 不必做 HTML，W5 再做。

---

## 九、Day 6 末的状态总结

**项目健康度**: 🟢 优秀
**已完成进度**: W1 100% + W2 50% = 约 25% 总进度
**剩余时间**: 约 24 天（Day 7-30）
**关键风险**: 低（已有 Gold Set + kappa 达标，核心可靠性已证明）

**单人作战的关键优势**：
- ✅ 决策速度快（不用开会）
- ✅ 没有沟通损耗
- ✅ 所有代码风格一致
- ⚠️ 容错率低（一旦倒下没人接手）

**建议**：
- Day 7 保持节奏，不要为了"完美 MVP"拖到 Day 8
- 每天结束前更新 PROJECT_INDEX
- 每周日休息半天（你需要恢复）
INDEXEOF