# Streamlit Demo 本地运行指南

## 快速启动 (3 步)

```bash
# 1. 装依赖
pip install streamlit plotly pandas

# 2. 设置 API key (LLM 评测要用)
export DEEPSEEK_API_KEY=你的key

# 3. 跑起来
cd 10_streamlit_app
streamlit run app.py
```

打开浏览器到 http://localhost:8501

---

## 页面说明

| 页面 | 功能 | 演示价值 |
|---|---|---|
| 主页 | 项目介绍 + 核心数据 | 评委第一眼印象 |
| 📋 上传指令 | 解析任务约束 | 展示 parser 能力 |
| 💬 跑对话 | 调用 simulator (Day 12 实现) | 展示对话生成 |
| 🧪 评测 | 调用 pipeline 评分 | **核心功能演示** |
| 📊 报告 | 评分可视化 | **直观展示评测结果** |
| 📖 关于 | 项目背景 + 技术细节 | 评委查细节 |

---

## 演示动线 (3 分钟视频脚本)

```
[0:00-0:30] 主页
  - 介绍背景: 美团每天有大量外呼对话需评测
  - 展示核心数据: 客观 kappa = 1.0 / 整体 0.45 / 三路 0.81

[0:30-1:00] 上传指令
  - 选 V4 示例 (出餐核实)
  - 点解析按钮
  - 展示自动拆出 26 条约束 + 表格

[1:00-2:00] 评测核心 ⭐
  - 切到 🧪 评测页
  - 选 V4 指令 + cooperative 对话
  - 选 LLM 模式
  - 点开始评测
  - 看进度条 + 实时展示
  - 出评分卡

[2:00-2:45] 报告可视化 ⭐
  - 切到 📊 报告页
  - 看雷达图 + 维度分
  - 看违规清单 + 优化建议
  - 下载 JSON/MD 报告

[2:45-3:00] 关于页
  - 商业价值: ¥0.20/通 vs ¥10/通
  - 4 轮迭代故事
  - 联系方式
```

---

## 故障排查

### Q: streamlit 报错 "ModuleNotFoundError"
```bash
pip install -r requirements.txt
```

### Q: 评测时报 "Pipeline 模块加载失败"
检查目录结构,要在 `meituan_eval/10_streamlit_app/` 跑

### Q: API key 没设置
评测时切到 Mock 模式不需要 key,LLM 模式必须

### Q: 跑太慢
- 用 Mock 模式 (秒出)
- 或限制约束数 (改 pipeline 加 --limit 参数)

---

## 关键设计要点

### 1. 演示即生产
所有数据都用真实的 50 通 Gold Set + 真实的 v6 标注

### 2. 故障安全
所有 LLM 调用都有 try-catch + Mock 回退

### 3. 评委友好
- 大字数字 (Score 80 一眼看到)
- 配色清晰 (绿 pass / 红 fail / 灰 na)
- 一键下载 (评委拿走素材)

---

## 下一步开发计划 (D12-D15)

| 日 | 任务 | 优先级 |
|---|---|---|
| D12 | 写 Tab 2 (跑对话, 调 simulator) | 中 |
| D13 | 美化 + 加截图 + 性能优化 | 高 |
| D14 | 录演示视频 | 高 |
| D15 | 测试 + 部署到 Streamlit Cloud (备份) | 中 |
