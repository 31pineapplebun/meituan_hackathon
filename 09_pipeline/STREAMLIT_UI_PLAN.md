# Streamlit UI 设计 v1.0

> 目的: 5 天搭一个能现场演示的 demo
> 技术: Streamlit (Python 写 UI,无前端经验也能搞)
> 部署: 本地跑 / Streamlit Cloud / 公司内网都行

---

## 整体页面结构 (5 页)

```
┌─────────────────────────────────────────────────────────────────┐
│  🎯 美团对话外呼任务评测系统                                       │
│  [Tab 1] 上传指令  [Tab 2] 跑对话  [Tab 3] 评测  [Tab 4] 报告  [Tab 5] 关于  │
└─────────────────────────────────────────────────────────────────┘
```

### Tab 1: 📋 上传指令 (指令解析)
**目的**: 用户传 markdown 指令 → 自动解析出约束清单

**功能**:
- 文件上传框 (支持 .md 文件 或直接粘贴)
- 调用 parser.py
- 展示解析结果:
  - 任务描述
  - 约束清单 (表格: id / name / verifier / weight / critical)
  - FAQ 列表
  - 状态机 DAG (可选: 用 plotly 画)

**实现**: 已有 `parser.py`,直接调用,把 JSON 渲染成表格

**关键卖点**: "黑客松要求的指令格式很复杂,我们自动解析 16-26 条约束"

---

### Tab 2: 💬 跑对话 (对话生成)
**目的**: 选指令 + 选 Persona → 自动跑出对话

**功能**:
- 下拉选指令 (V1/V2/V4/V5)
- 下拉选 Persona (cooperative/interruption/out_of_scope/refuse_persistent)
- 下拉选模型 (GPT-5-mini / DeepSeek-Flash)
- 跑按钮 → 流式输出对话
- 跑完显示完整 JSON 可下载

**实现**: 调用 `simulator_v2.py`,流式回调显示

**关键卖点**: "通过 Persona 系统,我们能定向考察模型在 4 种用户类型下的表现"

---

### Tab 3: 🧪 评测 (Pipeline 评分)
**目的**: 对话 + 指令 → 评分报告

**功能**:
- 选指令 (从 Tab 1 解析过的)
- 选对话 (从 Tab 2 跑出来的或上传 .jsonl)
- 选 verifier 模式 (LLM / Mock)
- 开始评测按钮
- 进度条 (跑约束的过程实时显示)
- 跑完显示评分卡

**实现**: 调用 `pipeline.py`,streamlit progress bar

**关键卖点**: "5 类 verifier 同时跑,15-30 秒出完整评分"

---

### Tab 4: 📊 报告 (评分可视化)
**目的**: 漂亮的评分报告,适合截图给评委

**功能**:
- 大字显示最终分数 (彩色卡片: 90+ 绿/70-90 黄/<70 红)
- 雷达图: 5 维度分 (D1-D5) - plotly
- 约束通过率柱状图
- 详细 verdict 表格 (可筛选 fail/pass/na)
- 关键违规高亮 (红色标记)
- 优化建议 (基于 fail 的约束)
- 下载完整 JSON / Markdown 按钮

**实现**: 渲染 `pipeline.py` 输出的 score_report

**关键卖点**: "评分报告即洞察,自动定位问题约束"

---

### Tab 5: 📖 关于 (项目说明)
**目的**: 评委了解项目背景和技术架构

**功能**:
- 项目介绍 (一页 markdown)
- 技术架构图 (mermaid)
- 关键数据展示:
  - **客观约束 kappa = 1.0** (大字)
  - 三路 LLM 对照 kappa = 0.81
  - 4 轮迭代故事
- 联系方式 / GitHub 链接

**实现**: 静态页面,markdown 渲染

---

## 技术架构

```
streamlit_app/
├── app.py                    # 主入口
├── pages/
│   ├── 1_📋_上传指令.py
│   ├── 2_💬_跑对话.py
│   ├── 3_🧪_评测.py
│   ├── 4_📊_报告.py
│   └── 5_📖_关于.py
├── utils/
│   ├── parser_wrapper.py    # 包装 08_parser/parser.py
│   ├── simulator_wrapper.py  # 包装 07_simulator/simulator_v2.py
│   └── pipeline_wrapper.py  # 包装 09_pipeline/pipeline.py
└── assets/
    ├── logo.png
    └── style.css
```

---

## 5 天开发计划

### Day 1: 项目搭建 + Tab 1 (上传指令)
- streamlit 项目结构
- parser_wrapper 调通
- 上传 + 显示约束表
- **预期产出**: 能上传 V4.md 显示出 26 条约束

### Day 2: Tab 3 (评测) - 核心功能优先
- pipeline_wrapper 调通
- 调用现有 batch_evaluate.py 逻辑
- 显示评分卡 (简版)
- **预期产出**: 选 V4 + 上传对话 → 出 85/100 分

### Day 3: Tab 4 (报告) - 可视化美化
- plotly 雷达图
- 维度分柱状图
- verdict 详细表
- **预期产出**: 漂亮的评分报告页

### Day 4: Tab 2 (跑对话) + Tab 5 (关于)
- simulator_wrapper 调通
- 流式输出对话
- 关于页面 + 技术架构图
- **预期产出**: 端到端可用

### Day 5: 美化 + 部署测试
- CSS 美化
- 错误处理
- 部署到 Streamlit Cloud (备用)
- **预期产出**: 答辩可用 demo

---

## 关键设计原则

### 1. **演示驱动**
每个 Tab 都要能"独立讲一段故事"——评委点开任何 Tab 都能立刻理解功能

### 2. **数据真实**
不要 mock 数据,用真实 V1-V5 指令 + 真实对话 + 真实评分

### 3. **故障安全**
所有调用都要 try-catch,确保 demo 时不崩

### 4. **轻量级**
不上传到生产环境,本地跑 streamlit run app.py 即可演示

---

## 启动命令 (Day 1 立刻可用)

```bash
pip install streamlit plotly
mkdir streamlit_app
cd streamlit_app
streamlit hello  # 先确认环境
```

---

## 风险与备份

- **风险 1**: streamlit 不熟,可能卡住
  - **备份**: 用 Gradio (更简单) 或纯 HTML+JS
- **风险 2**: 5 天做不完
  - **备份**: 优先做 Tab 3 + Tab 4 (核心评测+报告),其他 Tab 用静态截图代替
- **风险 3**: 评委要看代码细节
  - **备份**: 准备 README 截图 + 关键代码片段
