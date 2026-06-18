"""FastAPI 入口 —— 把评测引擎暴露成 REST 接口供 React 前端调用。

跑法:
    cd 12_api
    python -m uvicorn main:app --reload --port 8000

接口:
    GET  /api/config            配置空间(内置指令 / 模型 / persona / 维度)
    POST /api/evaluate          提交配置 → 启动后台评测 → 返回 {job_id}
    GET  /api/jobs/{id}         轮询任务状态 / 进度
    GET  /api/report/{id}       取评测报告(任务完成后)
"""
from contextlib import asynccontextmanager
from typing import List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
import engine
import jobs


@asynccontextmanager
async def lifespan(app):
    engine.sweep_custom_tmp()  # 启动时清掉上次残留的自定义指令临时文件
    yield


app = FastAPI(title="外呼指令遵循评测 API", version="0.1.0", lifespan=lifespan)

# 开发期: 允许 Vite dev server(5173)跨域。生产同源部署时可收紧。
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# 自定义指令的哨兵 id(前端选「自定义指令」时用它替代内置指令名)
CUSTOM = "__custom__"


class EvaluateRequest(BaseModel):
    instruction_name: str
    model_name: str = "deepseek-v4-flash"
    persona_list: List[str] = []
    mode: str = "fast"  # fast(快速演示) | full(完整运行)
    custom_instruction_text: str = ""  # instruction_name == __custom__ 时的指令原文


class DialogueQCRequest(BaseModel):
    dialogue_text: str = ""  # 粘贴的对话文本或上传文件内容(支持 角色:内容 / JSON / JSONL)


class SimulateRequest(BaseModel):
    prompt_text: str = ""  # 一句话场景描述,系统据此模拟一通对话


@app.get("/api/config")
def get_config():
    """前端拉取配置空间,据此动态渲染配置表单。"""
    return {
        "instructions": [
            {"id": k, "label": v["label"], "has_demo": v["has_demo"]}
            for k, v in config.INSTRUCTIONS.items()
        ],
        "models": config.MODELS,
        "personas": config.PERSONAS,
        "dimensions": config.DIMENSIONS,
        "custom_id": CUSTOM,
    }


def _key_msg(var):
    return (
        f"完整运行需要环境变量 {var}(未检测到)。请在启动后端的终端里设置后重启,"
        f"或改用「快速演示」。"
    )


@app.post("/api/evaluate")
def evaluate(req: EvaluateRequest):
    """校验配置 → 选择 fast / full / 自定义 执行函数 → 起后台任务 → 返回 job_id。"""
    is_custom = req.instruction_name == CUSTOM
    if not is_custom and req.instruction_name not in config.INSTRUCTIONS:
        raise HTTPException(400, f"未知指令: {req.instruction_name}")
    if not req.persona_list:
        raise HTTPException(400, "请至少选择一个 persona")

    if is_custom:
        # 自定义指令没有预置数据,只能完整运行,需 API key。
        if not req.custom_instruction_text.strip():
            raise HTTPException(400, "自定义指令内容为空")
        miss = engine.missing_key(req.model_name)
        if miss:
            raise HTTPException(400, _key_msg(miss))

        def work(cb, req=req):
            return engine.run_full_custom(
                req.custom_instruction_text, req.model_name, req.persona_list, cb
            )
    elif req.mode == "full":
        miss = engine.missing_key(req.model_name)
        if miss:
            raise HTTPException(400, _key_msg(miss))

        def work(cb, req=req):
            return engine.run_full(req.instruction_name, req.model_name, req.persona_list, cb)
    elif req.mode == "fast":
        if not config.INSTRUCTIONS[req.instruction_name]["has_demo"]:
            raise HTTPException(400, "该指令没有预置演示数据,请改用「完整运行」。")

        def work(cb, req=req):
            # 快速演示是秒出的,用不到进度回调 cb。
            return engine.run_fast(req.instruction_name, req.model_name, req.persona_list)
    else:
        raise HTTPException(400, f"未知评测模式: {req.mode}")

    job_id = jobs.create_job()
    jobs.start_job(job_id, work)
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    """轮询任务状态。响应保持轻量(不含完整报告),完成后前端再去 /api/report 取。"""
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "job 不存在")
    return {
        "id": job["id"],
        "status": job["status"],
        "progress": job["progress"],
        "error": job["error"],
    }


@app.get("/api/report/{job_id}")
def get_report(job_id: str):
    """取评测报告(模型级聚合报告 dict)。任务未完成返回 409。"""
    job = jobs.get_job(job_id)
    if not job:
        raise HTTPException(404, "job 不存在")
    if job["status"] != "done":
        raise HTTPException(409, f"评测尚未完成(当前状态: {job['status']})")
    return job["report"]


@app.get("/api/instruction/{instruction_id}/md")
def get_instruction_md(instruction_id: str):
    """取内置指令的原文,供「自定义指令」当示例模板。"""
    instr = config.INSTRUCTIONS.get(instruction_id)
    if not instr:
        raise HTTPException(404, f"未知指令: {instruction_id}")
    return {"text": instr["md"].read_text(encoding="utf-8")}


@app.post("/api/eval-dialogue")
def eval_dialogue(req: DialogueQCRequest):
    """质检用户给的一通对话 → 单通报告(report_type=single_dialogue)。"""
    if not req.dialogue_text.strip():
        raise HTTPException(400, "对话内容为空")

    def work(cb, req=req):
        return engine.run_dialogue_qc(req.dialogue_text)

    job_id = jobs.create_job()
    jobs.start_job(job_id, work)
    return {"job_id": job_id}


@app.post("/api/simulate-eval")
def simulate_eval(req: SimulateRequest):
    """据描述模拟一通对话再质检。生成对话要调 LLM,需 DeepSeek key。"""
    if not req.prompt_text.strip():
        raise HTTPException(400, "描述为空")
    miss = engine.missing_key("deepseek-v4-flash")
    if miss:
        raise HTTPException(400, f"模拟对话需要环境变量 {miss}(未检测到)。")

    def work(cb, req=req):
        return engine.run_simulate_qc(req.prompt_text)

    job_id = jobs.create_job()
    jobs.start_job(job_id, work)
    return {"job_id": job_id}
