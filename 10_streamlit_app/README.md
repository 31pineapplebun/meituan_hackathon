# Streamlit 本地运行指南（当前版本）

## 快速启动

```bash
pip install -r requirements.txt
cd 10_streamlit_app
streamlit run app.py
```

浏览器打开 `http://localhost:8501`。

## 当前页面结构

| 页面 | 用途 |
|---|---|
| `app.py` | 一站式主流程：选指令 → 选模型/场景 → 一键评测 → 模型能力画像 |
| `pages/1_dialogue_detail.py` | 下钻查看某一通对话的逐约束判定证据 |
| `pages/2_about.py` | 技术原理与可靠性说明 |

## 推荐演示动线（3 分钟）

1. 在主页选指令（如 `V4`）并确认约束解析结果  
2. 选择模型 + 勾选 persona  
3. 先跑快速演示（秒级）展示能力画像  
4. 进入单通详查页展示逐约束证据  
5. 切到关于页展示可靠性数据

## 模式说明

- 快速演示：读取预置真实评测结果（无需 API key）
- 完整运行：实时生成对话并评测（需要对应模型 API key）

## 常见问题

- `ModuleNotFoundError`：确认在 `10_streamlit_app` 目录运行，且已 `pip install -r requirements.txt`
- 完整运行报 key 错误：检查 `DEEPSEEK_API_KEY` / `OPENAI_API_KEY`
- 场景缺失：快速演示仅覆盖核心 persona，其他场景请用完整运行模式
