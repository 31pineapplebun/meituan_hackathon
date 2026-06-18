"""评测引擎桥接层。

设计原则(见 CLAUDE.md):**不重写引擎**。这里只做两件事:
1. 复刻 sys.path 设置,让我们能 import 既有的 09_pipeline 引擎模块;
2. 把引擎里的真实函数(run_fast_demo / aggregate_model_report / run_full_evaluation)
   包装成 FastAPI 好调用的形式。

为什么 import 是安全的: model_evaluation 顶层只 import 标准库;真正重的
simulator / verifier 链是在 run_full_evaluation 内部按需 import 的(且在那之前
会先设好 VERIFIER_LLM_MOCK / VERIFIER_LLM_MODEL 环境变量)。
"""
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path

from config import PROJECT_ROOT, INSTRUCTIONS

# 复刻 10_streamlit_app/bootstrap.py 的路径设置(顺序一致),否则 import 引擎模块会失败。
for _sub in ("08_parser", "09_pipeline", "07_simulator"):
    _full = str(PROJECT_ROOT / _sub)
    if _full not in sys.path:
        sys.path.insert(0, _full)

# 直接复用引擎的真实函数,不复制任何评测逻辑。
from model_evaluation import (  # noqa: E402 — 必须在 sys.path 设置之后 import
    run_fast_demo,
    aggregate_model_report,
    run_full_evaluation,
)

# 自定义指令评测时落临时 parsed.json 的专用目录。集中放一处,便于启动时清扫:
# 后台是 daemon 线程,进程被强杀(uvicorn --reload / Ctrl+C)时 finally 可能来不及删。
CUSTOM_TMP_DIR = Path(tempfile.gettempdir()) / "meituan_eval_custom"


def sweep_custom_tmp():
    """启动时清掉上次残留的自定义指令临时文件。"""
    try:
        for p in CUSTOM_TMP_DIR.glob("*.json"):
            try:
                p.unlink()
            except OSError:
                pass
    except OSError:
        pass


def run_fast(instruction_name, model_name, persona_list):
    """快速演示: 读预置真实结果 → 按所选 persona 过滤 → 重新聚合。

    预置数据只覆盖 4 个 persona,所以这里要过滤再聚合,而不是直接返回整份预置报告。
    """
    report = run_fast_demo(instruction_name, model_name)
    if "error" in report:
        return report

    selected = set(persona_list)
    filtered = [
        r for r in report.get("per_dialogue_results", [])
        if r.get("persona_id") in selected
    ]
    if not filtered:
        return {
            "error": "所选 persona 没有预置演示数据(预置覆盖: 合作型 / 坚持拒绝型 / "
                     "越界提问型 / 打断型)。请改选这些 persona,或用「完整运行」真跑。"
        }
    return aggregate_model_report(instruction_name, model_name, filtered)


def run_full(instruction_name, model_name, persona_list, progress_callback=None):
    """完整运行: 实时模拟对话 + 真评测。需要对应模型的 API key。

    已知限制: verifier 在首次 import 时读取 VERIFIER_LLM_MODEL,之后无法在同一进程内
    切换 —— 长驻进程里连续跑不同被测模型时,后续会沿用首个模型的判定配置。学习项目暂可
    接受;生产可改为子进程隔离每次运行。
    """
    instr = INSTRUCTIONS[instruction_name]
    instruction_text = Path(instr["md"]).read_text(encoding="utf-8")
    return run_full_evaluation(
        instruction_path=str(instr["parsed"]),
        instruction_text=instruction_text,
        instruction_name=instruction_name,
        model_name=model_name,
        persona_list=persona_list,
        progress_callback=progress_callback,
    )


def parse_custom_instruction(md_text):
    """把用户粘贴/上传的指令原文解析成约束 dict。

    用 importlib 按路径加载 08_parser/parser.py —— **不能** `import parser`,因为
    Python 3.9 有内置 parser 模块会遮蔽本地 parser.py(原 app.py 同样这么处理)。
    mock=True 用启发式解析(离线、不调 LLM)。
    """
    parser_path = PROJECT_ROOT / "08_parser" / "parser.py"
    spec = importlib.util.spec_from_file_location("meituan_parser", parser_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    parsed = mod.parse_instruction(
        md_text, instruction_id="CUSTOM", instruction_name="自定义指令", mock=True
    )
    return parsed.to_dict()


def run_full_custom(md_text, model_name, persona_list, progress_callback=None):
    """自定义指令完整运行: 解析原文 → 写临时 parsed.json → 真跑评测。需 API key。"""
    parsed = parse_custom_instruction(md_text)
    if not parsed.get("atomic_constraints"):
        return {"error": "未能从该指令解析出任何约束,请检查格式(需包含明确的要求/约束条目)。"}

    # run_full_evaluation 要从文件读预解析 JSON,这里落一个临时文件喂给它,跑完删。
    # 放专用目录,配合 sweep_custom_tmp() 启动清扫,避免 daemon 线程被强杀时残留。
    CUSTOM_TMP_DIR.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(suffix=".json", dir=str(CUSTOM_TMP_DIR))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(parsed, f, ensure_ascii=False)
        return run_full_evaluation(
            instruction_path=path,
            instruction_text=md_text,
            instruction_name="custom",
            model_name=model_name,
            persona_list=persona_list,
            progress_callback=progress_callback,
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def missing_key(model_name):
    """完整运行前的预检: 按模型前缀确认对应 API key 是否已配置。返回缺失的变量名或 None。"""
    if model_name.startswith("deepseek"):
        key = "DEEPSEEK_API_KEY"
    elif model_name.startswith(("gpt", "o1", "o3", "o4")):
        key = "OPENAI_API_KEY"
    elif model_name.startswith("claude"):
        key = "ANTHROPIC_API_KEY"
    else:
        return None
    return None if os.environ.get(key) else key


# =====================================================================
# 单通对话质检(评一通已有/模拟的对话,而非评模型)—— 复用 run_pipeline + 通用质检标准
# =====================================================================

GENERIC_RUBRIC_PATH = PROJECT_ROOT / "03_examples" / "generic_qc_rubric.json"
RUBRIC_LABEL = "内置通用外呼质检标准"

# 角色标签 → 统一 role(和原 app.py 一致)
_ASST_LABELS = {"客服", "坐席", "外呼", "外呼员", "助手", "客服专员", "客户经理", "站长",
                "机器人", "ai", "assistant", "a", "agent", "bot", "外呼机器人"}
_USER_LABELS = {"用户", "客户", "对方", "顾客", "骑手", "商家", "user", "u", "customer", "b"}


def _norm_role(label, fallback="user"):
    s = str(label).strip().lower()
    if s in _ASST_LABELS:
        return "assistant"
    if s in _USER_LABELS:
        return "user"
    return fallback


def _normalize_turns(turns):
    """把任意 turns 列表规整成 {turn, role∈{assistant,user}, content}。"""
    out = []
    for i, t in enumerate(turns):
        if not isinstance(t, dict):
            continue
        role = _norm_role(t.get("role", t.get("speaker", "")), fallback="user")
        content = str(t.get("content", t.get("text", ""))).strip()
        if not content:
            continue
        out.append({"turn": t.get("turn", i + 1), "role": role, "content": content})
    return out


def _parse_dialogue_text(text):
    """把「角色: 内容」文本解析成对话(建议格式,非强制)。

    无角色标注(labeled<2)则退化为按行交替猜角色,并打 _weak_format 标记供前端提示。
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return None
    turns, unknown, labeled = [], [], 0
    for line in lines:
        m = re.match(r"^([^:：]{1,12})[:：]\s*(.+)$", line)
        if m:
            labeled += 1
            label, content = m.group(1).strip(), m.group(2).strip()
            s = label.lower()
            if s in _ASST_LABELS:
                role = "assistant"
            elif s in _USER_LABELS:
                role = "user"
            else:
                if s not in unknown:
                    unknown.append(s)
                role = "assistant" if unknown.index(s) == 0 else "user"
            turns.append({"turn": len(turns) + 1, "role": role, "content": content})
        elif turns:
            turns[-1]["content"] = (turns[-1]["content"] + " " + line).strip()
        else:
            turns.append({"turn": 1, "role": "assistant", "content": line})
    if labeled < 2:
        turns = [{"turn": i + 1, "role": "assistant" if i % 2 == 0 else "user", "content": l}
                 for i, l in enumerate(lines)]
        return {"dialogue_id": "user_pasted", "turns": turns, "_weak_format": True}
    return {"dialogue_id": "user_pasted", "turns": turns, "_weak_format": False}


def parse_dialogue(text):
    """把用户输入(粘贴文本 / 上传文件内容)解析成 dialogue dict。

    支持: 整文件 JSON(dict 含 turns 或 turns 列表)、JSONL(取首条含 turns)、「角色: 内容」文本。
    """
    raw = (text or "").strip()
    if not raw:
        return None
    # 整文件 JSON
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and obj.get("turns"):
            return {"dialogue_id": obj.get("dialogue_id", "uploaded"), "turns": _normalize_turns(obj["turns"])}
        if isinstance(obj, list):
            return {"dialogue_id": "uploaded", "turns": _normalize_turns(obj)}
    except (ValueError, TypeError):
        pass
    # JSONL: 取第一条含 turns
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and obj.get("turns"):
                return {"dialogue_id": obj.get("dialogue_id", "uploaded"), "turns": _normalize_turns(obj["turns"])}
        except (ValueError, TypeError):
            continue
    # 兜底: 当成「角色: 内容」文本
    return _parse_dialogue_text(raw)


def _eval_dialogue(dialogue):
    """对一通对话跑 run_pipeline(通用质检标准),附上对话与元信息返回。"""
    has_key = bool(os.environ.get("DEEPSEEK_API_KEY"))
    # 必须在 import 前设 mock/model(verifier import 时读 USE_MOCK);单通固定用 DeepSeek 判官,
    # 避免被前次「评模型」残留的 VERIFIER_LLM_MODEL(可能是 GPT)污染。
    os.environ["VERIFIER_LLM_MOCK"] = "0" if has_key else "1"
    os.environ["VERIFIER_LLM_MODEL"] = "deepseek-v4-flash"

    with open(GENERIC_RUBRIC_PATH, encoding="utf-8") as f:
        rubric = json.load(f)

    from pipeline import run_pipeline  # noqa: E402 — 必须在上面设好 env 之后再 import
    output = run_pipeline(rubric, dialogue)
    if "error" in output:
        return output
    output["report_type"] = "single_dialogue"
    output["rubric_label"] = RUBRIC_LABEL
    output["dialogue"] = dialogue
    output["mock_mode"] = not has_key  # 前端据此提示「mock 预览」
    return output


def run_dialogue_qc(dialogue_text):
    """质检用户给的一通对话。"""
    dialogue = parse_dialogue(dialogue_text)
    if not (dialogue and dialogue.get("turns")):
        return {"error": "没解析出对话内容,请检查粘贴/上传的内容是否为空或格式不对。"}
    return _eval_dialogue(dialogue)


def simulate_dialogue(prompt_text, model="deepseek-v4-flash"):
    """根据大致描述调 LLM 现场生成一通多轮对话。需 API key。"""
    from llm_client import call_llm
    gen_prompt = (
        "根据下面的【描述】生成一段多轮中文对话(外呼/客服场景)。"
        "客服方 role=assistant, 用户方 role=user, 双方交替发言, 6-12 轮, "
        "贴合描述里的人物性格与场景, 自然口语化。\n\n"
        f"【描述】{prompt_text}\n\n"
        '只输出 JSON: {"turns":[{"turn":1,"role":"assistant","content":"..."},'
        '{"turn":2,"role":"user","content":"..."}]}'
    )
    facts = call_llm(gen_prompt, model=model, system="你是对话生成器, 只输出 JSON.", max_tokens=2000)
    turns = facts.get("turns") if isinstance(facts, dict) else None
    if not turns:
        return None
    norm = _normalize_turns(turns)
    return {"dialogue_id": "simulated_from_prompt", "turns": norm} if norm else None


def run_simulate_qc(prompt_text, model="deepseek-v4-flash"):
    """据描述模拟一通对话再质检。需 API key。"""
    try:
        dialogue = simulate_dialogue(prompt_text, model)
    except Exception as e:  # noqa: BLE001 — 生成失败转成可读错误回前端
        return {"error": f"模拟对话失败: {e}"}
    if not (dialogue and dialogue.get("turns")):
        return {"error": "没能生成对话,请换个描述或检查网络 / key。"}
    return _eval_dialogue(dialogue)
