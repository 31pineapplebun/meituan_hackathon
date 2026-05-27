# 项目全面测评清单 - 提交前必跑

> **目的**: 找出所有隐藏 bug,确保评委拿到的东西都对
> **用法**: 按顺序跑,每条记录通过/失败
> **预期耗时**: 完整跑一遍约 2-3 小时

---

## 第 1 类: 后端单元测试 (5 分钟)

### 1.1 Parser 回归测试
```bash
cd 08_parser
python test_parser_regression.py
```
**期望**: ✅ 全部通过 (8/8) - V1-V6 解析 + 官方 sample 1/2 解析

### 1.2 5 类 Verifier 单测
```bash
cd 09_pipeline
python verifiers.py                  # 期望: 5/5 全过
python verifier_state_tracker.py     # 期望: 全过
python verifier_llm_extract.py        # 期望: 6/6 全过
python verifier_llm_judge.py          # 期望: 4/4 全过
python suggestion_generator.py        # 期望: 通过
```

### 1.3 P3 评分算法验证
```bash
cd 04_scoring
python scoring_validation.py
```
**期望**: 4/4 通过 (含边界 case)

### 1.4 三路 LLM 对照结果完整性
```bash
ls 09_pipeline/batch_results/three_way_summary.json
```
**期望**: 存在 + Flash/Pro/GPT kappa 三个数据点 ≥ 0.77

### 1.5 Gold Set v6 完整性
```bash
cd 06_gold_annotation
wc -l gold_set/human_v6_reviewed.csv
```
**期望**: 1056 行 (1055 verdict + 表头)

---

## 第 2 类: Streamlit UI 端到端 (30 分钟)

### 2.1 启动测试
```bash
cd 10_streamlit_app
streamlit run app.py
```
**期望**: 浏览器自动打开,主页显示 4 个核心数据卡片

### 2.2 Tab 1 - 上传指令

| 测试动作 | 期望结果 |
|---|---|
| 选 "🏢 官方 Sample 1 - 飞毛腿合同" | 显示约束清单 15 条 |
| 点 "🔍 开始解析" | 进度条 + 概览 3 个数字 |
| 看约束表 | 含 ID/关键/Verifier 类型/维度/权重/约束名 |
| 看 Verifier 饼图 | 5 类 (含 state_tracker / llm_judge / rule) |
| 看维度柱状图 | 5 个维度 D1-D5 |
| 点 "下载 JSON" | 文件大小 > 5KB |
| 选 "V6" | 显示约束 36 条 |
| 选 "📤 上传自己的 .md" | 上传任一 .md 能解析 |
| 选 "✏️ 粘贴 markdown" | 粘贴框出现 |

### 2.3 Tab 2 - 用户模拟器

| 测试动作 | 期望结果 |
|---|---|
| Persona 下拉 | 8 个 (合作/拒绝/越界/打断/状态/模糊/对抗/提问) |
| 选 "🏢 官方 sample 1" + "⚔️ 对抗型" + Mock | 跑出含挑刺语气的对话 |
| 看用户回复 | 应含 "凭什么我必须配合" 类话 |
| 点 "下载对话 JSONL" | 文件能下载 |
| 切到 LLM 模式 (有 API key) | 跑出更真实对话 |

### 2.4 Tab 3 - 评测

| 测试动作 | 期望结果 |
|---|---|
| 选 V1 | "📁 从 Gold Set 选" 应有对话可选 |
| 选官方 sample 1 | **应出现 "🏢 用官方 Demo 对话" 选项** |
| 跑过 Tab2 后 | 应出现 "💬 用模拟器刚生成的" |
| 选完美对话 + Mock | 评分应 > 60 |
| 选违规对话 + Mock | 评分应 < 60, 含 fail 约束 |
| 选 LLM 模式 (有 API key) | 评分用真实判定 |

### 2.5 Tab 4 - 报告 (重点测下载)

| 测试动作 | 期望结果 |
|---|---|
| 评测后切到报告页 | 自动显示数据 (不会要重新加载) |
| 大字评分卡 | 颜色对 (绿/黄/橙/红 对应分数) |
| 雷达图 | 5 维度分对得上 |
| 优化建议 | 至少 1 条 (违规对话) |
| **下载 JSON** | 文件 > 10KB, 含 verdict_details |
| **下载 Markdown** | **必须 > 3KB, 含完整章节** ⚠️ 这是之前 bug |
| **下载 HTML** | > 20KB, 浏览器打开能看雷达图 |

### 2.6 Tab 5 - 关于

| 测试动作 | 期望结果 |
|---|---|
| 项目介绍 | 显示 |
| 核心数据 | 4 个 kappa 数字 (1.0/0.84/0.45/0.81) |
| 技术架构图 | 显示 (mermaid) |
| **未来路线** | 业务语言 (不是 W4/W5) |

---

## 第 3 类: 端到端集成 (15 分钟)

### 3.1 完整业务流程 (评委演示路径)

```
1. Tab 1 选 "🏢 官方 Sample 1" → 点解析 → 看 15 条约束
   ↓
2. Tab 2 选 "🏢 官方 sample 1" + "🤝 合作型" + Mock → 跑对话 → 看 11 轮对话
   ↓
3. Tab 3 切到此页 → 自动出现 "💬 用模拟器刚生成的" → 选它 + Mock → 评测
   ↓
4. Tab 4 自动显示 → 评分卡 + 雷达图 + 优化建议 → 下载 3 种格式
   ↓
5. 打开下载的 HTML → 浏览器渲染对应 → 跟 UI 上显示的一致
```

**关键点**: 全流程不报错 + 数据一致 + 下载文件可用

### 3.2 跨指令切换测试

| 路径 | 期望 |
|---|---|
| Tab 2 选 V4 跑对话 → Tab 3 选 V5 | 警告 "对话和指令不匹配" |
| Tab 1 解析 V6 → Tab 3 选 V6 | 26 条约束都被评测 |
| Tab 2 跑官方 sample 1 → Tab 3 选官方 sample 1 | 用模拟器对话评测成功 |

---

## 第 4 类: 数据完整性 (10 分钟)

### 4.1 文件齐全检查
```bash
# 必须存在的关键文件
ls 03_examples/variants/V{1,2,3,4,5,6}.md       # 6 个指令
ls 03_examples/official/official_{1,2}*.md        # 2 官方 sample
ls 08_parser/parsed_examples/*.json               # 8 个预解析
ls 06_gold_annotation/gold_set/*.csv              # 至少 v6
ls 09_pipeline/batch_results/three_way_summary.json
ls 09_pipeline/RELIABILITY_REPORT_v2.md
ls 10_streamlit_app/pages/                        # 5 个 .py
```

### 4.2 数据一致性
```bash
# v6 标注总数应该 = 1055
wc -l 06_gold_annotation/gold_set/human_v6_reviewed.csv

# auto_llm_flash 也应 1055
wc -l 09_pipeline/batch_results/auto_llm_flash.csv
```

### 4.3 关键数字核对 (跟答辩材料对得上)
```bash
# v6 vs LLM flash kappa
cd 06_gold_annotation
python kappa_calc.py \
  --rater1 gold_set/human_v6_reviewed.csv \
  --rater2 ../09_pipeline/batch_results/auto_llm_flash.csv 2>&1 | grep "Kappa"
```
**期望**: kappa ≈ 0.4483

---

## 第 5 类: 边界 case (15 分钟)

### 5.1 异常输入
- Tab 1 上传**空文件** → 应优雅报错
- Tab 1 上传**非 markdown** (如 .txt 含乱码) → 应报错不崩
- Tab 2 选指令但**没设 API key** + LLM 模式 → 应报错指引
- Tab 3 **没选对话**直接点评测 → 按钮应 disabled

### 5.2 极端数据
- 极长对话 (50+ turn) → 不卡死
- 极短对话 (1 turn) → 优雅报"轮数不够"
- 全 fail 对话 → 评分应 < 40

---

## 第 6 类: 性能 + 稳定性 (10 分钟)

### 6.1 评测耗时
```bash
# Mock 模式应 < 3 秒
time (cd 09_pipeline && VERIFIER_LLM_MOCK=1 python pipeline.py \
   --instruction ../08_parser/parsed_examples/v4_parsed.json \
   --dialogue test_data/v4_cooperative_violation.jsonl \
   --output_dir /tmp/perf/ )
```
**期望**: < 5 秒

### 6.2 内存
- 跑完后 Streamlit 内存占用 < 500MB

---

## 第 7 类: 报告/PDF 一致性 (技术报告写完后做)

- 答辩材料里的 kappa 数字 = 真实数据 ✅
- 答辩材料里的截图 = 实际 UI 显示 ✅
- demo 视频里的演示 = 端到端流程 ✅

---

## 通过标准

| 等级 | 标准 |
|---|---|
| 🥇 一等奖以上 | 全部 7 类通过 + 无 P0 bug |
| 🥈 二等奖 | 1-4 类全过, 5-6 类有少量瑕疵 |
| 🥉 三等奖 | 1-3 类通过, 端到端能跑 |

**P0 bug 定义**: 评委按演示路径能复现的明显错误 (如下载文件残缺/某 Tab 崩溃)

---

## 自动化测试脚本入口

```bash
# 一键跑后端全套
bash scripts/run_all_tests.sh

# UI 测试只能人工 - 但可以截图存档
```

---

## 隐藏风险清单 (Day 11 已知)

### 🔴 P0 风险
- ❌ **Tab 4 MD 下载只有 1 行** (本次修复, v28 起)
- ⚠️ **Streamlit 容器没有真正跑过** - 我在容器里没法装 streamlit, 你本地跑发现 bug 我才能修

### 🟡 P1 风险  
- ⚠️ Mock 模式生成的对话太短 (5-10 轮) - 评测会出大量 not_implemented
- ⚠️ LLM 模式没设 API key 时, 评测会失败 - 需要友好提示
- ⚠️ Pipeline 在 Streamlit 里没传 instruction 完整对象 - MD 渲染缺信息

### 🟢 P2 风险
- 浏览器缓存可能让旧版 UI 一直显示 - 建议每次重启 streamlit + Ctrl+F5
- session_state 在切 Tab 时偶尔会丢 - 重新跑评测能恢复

### 已规避的风险
- ✅ V3/V6 没在 Gold Set 里 → 用模拟器跑就行,UI 加了提示
- ✅ 官方 sample 解析失败 → parser 已支持多种 markdown 格式
- ✅ 8 个 persona 完整 → 不再是 4 个

---

## 终极测试: 模拟评委 5 分钟体验

完整跑这套, 评委 5 分钟内必看到:

1. **0:00-1:00** Tab 1 解析官方 sample → 自动出 15 条约束 + 图表
2. **1:00-2:00** Tab 2 选对抗型 + 跑对话 → 看到挑刺语气
3. **2:00-3:00** Tab 3 评测 → 看进度条 + 评分
4. **3:00-4:00** Tab 4 看评分卡 + 雷达图 + 优化建议
5. **4:00-5:00** 下载 HTML → 浏览器打开看完整报告

**任何一步卡住 = 评委印象立马降级**
