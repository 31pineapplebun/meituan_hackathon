# 12_api — 评测引擎的 FastAPI 封装

把既有的 Python 评测引擎(`09_pipeline/`)包成 REST 接口,供 React 前端(`11_web_frontend/`)调用。
**不重写引擎**——这一层只做 `sys.path` 设置 + 调用既有函数(见 `engine.py`)。

## 跑起来

```bash
# 1. 装依赖(用本机的 python3.9)
python -m pip install -r requirements.txt

# 2. 启动(--app-dir 让 main/config/engine/jobs 这几个同级模块能被 import)
python -m uvicorn main:app --app-dir 12_api --host 0.0.0.0 --port 8000 --reload
```

> Windows 本机可用 `D:\download\python3.9.13\python.exe` 代替 `python`。

完整运行(`mode=full`,真跑大模型)需要对应 API key:
```bash
# deepseek 模型
export DEEPSEEK_API_KEY=<你的key>      # PowerShell: $env:DEEPSEEK_API_KEY="..."
# gpt 模型
export OPENAI_API_KEY=<你的key>
```
不设 key 时,只用 **快速演示(`mode=fast`)**——读 `09_pipeline/model_demo/` 的预置真实结果,秒出、无需联网。

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET  | `/api/config`        | 配置空间:内置指令 / 模型 / persona / 维度 |
| POST | `/api/evaluate`      | 提交配置 → 启动后台评测 → 返回 `{job_id}` |
| GET  | `/api/jobs/{id}`     | 轮询任务状态 / 进度 |
| GET  | `/api/report/{id}`   | 取评测报告(任务完成后) |

`POST /api/evaluate` 请求体:
```json
{ "instruction_name": "official_1_feimaotui", "model_name": "deepseek-v4-flash",
  "persona_list": ["cooperative", "out_of_scope"], "mode": "fast" }
```

## 文件

- `config.py` — 配置空间(单一事实来源:内置指令路径 / 模型 / persona / 维度)
- `engine.py` — 引擎桥接层(`sys.path` + 调用 `model_evaluation` 的真实函数)
- `jobs.py`   — 内存任务存储 + 后台线程执行器(支撑异步 + 轮询)
- `main.py`   — FastAPI 路由
