"""
美团对话外呼任务评测系统 - 一站式主入口

跑法: streamlit run app.py

设计: 一条路走到底 —— 选指令 → 选待测模型+场景 → 一键评测 → 模型能力画像
官方要求: "给指令 + 给待测模型 → 出报告", 评的是【模型】不是【单通对话】
"""
import streamlit as st
import json
import os
import re
import sys
import time
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))   # 本目录: 供 import _theme
sys.path.insert(0, str(PROJECT_ROOT / "08_parser"))
sys.path.insert(0, str(PROJECT_ROOT / "09_pipeline"))
sys.path.insert(0, str(PROJECT_ROOT / "07_simulator"))

import _theme  # 共享主题(配色/CSS/侧边栏/页眉单一来源)

# verifier 的 mock 开关在 verifier 模块 import 时被读取(USE_MOCK 常量), 之后改不动。
# 这里在任何 verifier 被 import 前定个稳健默认: 有 key → 真实判定, 无 key → mock 预览。
# 用 setdefault 尊重用户已显式设置的环境变量。
os.environ.setdefault(
    "VERIFIER_LLM_MOCK",
    "0" if (os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")) else "1",
)

st.set_page_config(
    page_title="美团对话外呼评测系统",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

_theme.inject_theme()


# ============================================================
# 配置: 指令清单
# ============================================================
INSTRUCTIONS = {
    "🏢 官方 Sample 1 - 飞毛腿合同": {
        "name": "official_1_feimaotui",
        "md": PROJECT_ROOT / "03_examples" / "official" / "official_1_feimaotui.md",
        "parsed": PROJECT_ROOT / "08_parser" / "parsed_examples" / "official_1_feimaotui_parsed.json",
        "has_demo": True,
    },
    "🏢 官方 Sample 2 - 课程发布升级": {
        "name": "official_2_kecheng",
        "md": PROJECT_ROOT / "03_examples" / "official" / "official_2_kecheng.md",
        "parsed": PROJECT_ROOT / "08_parser" / "parsed_examples" / "official_2_kecheng_parsed.json",
        "has_demo": True,
    },
    "V1 - 骑手安全培训通知": {"name": "V1", "md": PROJECT_ROOT/"03_examples"/"variants"/"V1.md",
        "parsed": PROJECT_ROOT/"08_parser"/"parsed_examples"/"v1_parsed.json", "has_demo": True},
    "V2 - APP 强制更新通知": {"name": "V2", "md": PROJECT_ROOT/"03_examples"/"variants"/"V2.md",
        "parsed": PROJECT_ROOT/"08_parser"/"parsed_examples"/"v2_parsed.json", "has_demo": True},
    "V4 - 商家出餐慢核实": {"name": "V4", "md": PROJECT_ROOT/"03_examples"/"variants"/"V4.md",
        "parsed": PROJECT_ROOT/"08_parser"/"parsed_examples"/"v4_parsed.json", "has_demo": True},
    "V5 - 商家差评回访": {"name": "V5", "md": PROJECT_ROOT/"03_examples"/"variants"/"V5.md",
        "parsed": PROJECT_ROOT/"08_parser"/"parsed_examples"/"v5_parsed.json", "has_demo": True},
}

PERSONAS = {
    "cooperative": "🤝 合作型",
    "adversarial": "⚔️ 对抗型",
    "out_of_scope": "🌀 越界提问型",
    "interruption": "✋ 打断型",
    "refuse_persistent": "😤 坚持拒绝型",
    "state_busy": "🚗 状态型(忙/开车)",
    "ambiguous": "🤔 模糊型",
    "probing": "❓ 提问型",
}

DIM_SHORT = {
    "D1_flow_compliance": "D1 流程",
    "D2_task_completion": "D2 任务",
    "D3_constraint_compliance": "D3 约束",
    "D4_knowledge_accuracy": "D4 知识",
    "D5_dialogue_quality": "D5 对话",
}

VERIFIER_SHORT = {
    "rule": "📏 规则", "rule_pattern": "🔤 模式匹配",
    "state_tracker": "🔄 流程追踪", "llm_extract_then_rule": "🤖 LLM抽取",
    "llm_judge": "⚖️ LLM判定",
}


# ============================================================
# 工具函数
# ============================================================
def load_parsed(instr_cfg):
    """加载预解析指令; 上传的指令现场解析"""
    p = instr_cfg["parsed"]
    if p and Path(p).exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def _load_parse_instruction():
    """按文件路径加载 08_parser/parser.py 的 parse_instruction。

    用 importlib 而非 `import parser`: Python 3.9 有内置 `parser` 模块会遮蔽本地
    parser.py(3.10 起移除), 按路径加载可在任意 Python 版本下稳定拿到本地解析器。
    后端解析能力本就支持任意指令, 此处只是把它暴露到前端(不改后端逻辑)。
    """
    import importlib.util
    if "meituan_parser_mod" in sys.modules:
        return sys.modules["meituan_parser_mod"].parse_instruction
    pp = PROJECT_ROOT / "08_parser" / "parser.py"
    spec = importlib.util.spec_from_file_location("meituan_parser_mod", str(pp))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["meituan_parser_mod"] = mod
    spec.loader.exec_module(mod)
    return mod.parse_instruction


def grade_color(score):
    if score >= 85: return "#16a34a", "#22c55e", "优秀"
    if score >= 70: return "#f59e0b", "#fbbf24", "良好"
    if score >= 50: return "#ea580c", "#fb923c", "需改进"
    return "#dc2626", "#f87171", "不合格"


def render_model_report(report):
    """渲染模型级报告"""
    if report.get("error"):
        st.error(report["error"])
        return

    summary = report["summary"]
    score = summary["avg_score"]
    c1, c2, grade = grade_color(score)

    # 大字评分卡 - 主语是【模型】
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, {c1} 0%, {c2} 100%);
                padding: 36px; border-radius: 20px; text-align: center; color: white;
                box-shadow: 0 8px 32px rgba(0,0,0,0.2);">
        <div style="font-size: 18px; opacity: 0.92;">{report['model_name']}</div>
        <div style="font-size: 15px; opacity: 0.82; margin: 4px 0 12px;">
            在「{report['instruction_name']}」任务上的指令遵循能力</div>
        <div style="font-size: 72px; font-weight: 900; line-height: 1;">{score}<span style="font-size: 28px;"> / 100</span></div>
        <div style="display: inline-block; padding: 5px 22px; background: rgba(255,255,255,0.25);
                    border-radius: 20px; font-size: 16px; margin-top: 12px;">{grade}</div>
        <div style="font-size: 13px; opacity: 0.85; margin-top: 14px;">
            {summary['n_dialogues']} 个场景平均 · 范围 {summary['min_score']} - {summary['max_score']}
            {f" · {summary.get('n_unevaluable',0)} 个场景因对话异常未纳入" if summary.get('n_unevaluable', 0) > 0 else ""}</div>
    </div>
    """, unsafe_allow_html=True)

    # 自动诊断
    st.info(f"💡 **诊断**: {summary['diagnosis']}")

    st.markdown("---")

    # 5 维度雷达图 + 各场景表现
    col_l, col_r = st.columns([1, 1])

    with col_l:
        st.markdown("##### 📊 5 维度能力 (跨场景平均)")
        try:
            import plotly.graph_objects as go
            dim_avg = report["dim_avg"]
            keys = list(DIM_SHORT.keys())
            labels = [DIM_SHORT[k].replace(" ", "<br>") for k in keys]
            vals = [dim_avg.get(k) or 0 for k in keys]
            fig = go.Figure()
            fig.add_trace(go.Scatterpolar(
                r=vals + [vals[0]], theta=labels + [labels[0]],
                fill="toself", line_color="rgb(102,126,234)",
                fillcolor="rgba(102,126,234,0.3)"))
            fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                              showlegend=False, height=340, margin=dict(l=60, r=60, t=30, b=30))
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            st.write(report["dim_avg"])

    with col_r:
        st.markdown("##### 🎭 各场景表现 (最弱在前)")
        for p in report["persona_breakdown"]:
            pid = p["persona_id"]
            pscore = p["final_score"]
            pname = PERSONAS.get(pid, pid)
            bar_color = "#16a34a" if pscore >= 85 else "#f59e0b" if pscore >= 70 else "#ea580c" if pscore >= 50 else "#dc2626"
            pct = int(pscore)
            st.markdown(f"""
            <div style="margin: 6px 0;">
                <div style="display: flex; justify-content: space-between; font-size: 14px;">
                    <span>{pname}</span><span style="font-weight: 700; color: {bar_color};">{pscore}</span>
                </div>
                <div style="background: #e2e8f0; border-radius: 6px; height: 10px; overflow: hidden;">
                    <div style="background: {bar_color}; width: {pct}%; height: 100%;"></div>
                </div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # 最弱约束
    weak = report.get("weak_constraints", [])
    if weak:
        st.markdown("##### 🔴 最常违反的约束 (跨场景聚合)")
        import pandas as pd
        df = pd.DataFrame([{
            "约束 ID": w["constraint_id"],
            "约束名": w["constraint_name"],
            "失败率": f"{w['fail_rate']:.0f}%",
            "失败/总数": f"{w['fail_count']}/{w['total_count']}",
        } for w in weak])
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")

    # 下载 + 下钻
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📥 下载模型评测报告 (JSON)",
            json.dumps(report, ensure_ascii=False, indent=2),
            file_name=f"model_report_{report['instruction_name']}_{report['model_name']}.json",
            mime="application/json", use_container_width=True)
    with col2:
        st.session_state["detail_dialogues"] = report.get("per_dialogue_results", [])
        st.page_link("pages/1_📂_单通详查.py", label="📂 查看某一通对话的细节 →", use_container_width=True)


# ============================================================
# 单通对话评测 (评一通已有对话, 而非评模型) —— 复用后端 run_pipeline, 不改后端
# ============================================================
GENERIC_RUBRIC_PATH = PROJECT_ROOT / "03_examples" / "generic_qc_rubric.json"

# 对话角色标签 → 统一 role
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


def _load_generic_rubric():
    with open(GENERIC_RUBRIC_PATH, encoding="utf-8") as f:
        return json.load(f)


def _normalize_turns(turns):
    """把任意 turns 列表规整成 {turn, role∈{assistant,user}, content}"""
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
    """把"角色: 内容"文本解析成对话 dict (建议格式, 非强制)。
    - 有"角色:"标注: 客服/用户/未知标签(按出现顺序兜底, 外呼场景先开口的=客服)。无标签行并入上一轮。
    - 几乎无标注: 退化为"按行交替猜测角色", 并打 _weak_format 标记供前端提示(不强制, 仅劝诫)。
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines:
        return None
    turns = []
    unknown = []
    labeled = 0
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
    # 几乎没有"角色:"标注 → 退化为按行交替猜测(不强制, 但前端会提示可能影响质量)
    if labeled < 2:
        turns = [{"turn": i + 1, "role": "assistant" if i % 2 == 0 else "user", "content": l}
                 for i, l in enumerate(lines)]
        return {"dialogue_id": "user_pasted", "turns": turns, "_weak_format": True}
    return {"dialogue_id": "user_pasted", "turns": turns, "_weak_format": False}


def _load_dialogue_from_upload(file):
    """从上传文件解析对话: 支持系统原生 jsonl(一行一个含 turns 的对话)、整文件 JSON、或纯文本。"""
    raw = file.getvalue().decode("utf-8", errors="replace").strip()
    if not raw:
        return None
    # 整文件 JSON: 一个 dialogue dict 或 turns 列表
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and obj.get("turns"):
            return {"dialogue_id": obj.get("dialogue_id", "uploaded"), "turns": _normalize_turns(obj["turns"])}
        if isinstance(obj, list):
            return {"dialogue_id": "uploaded", "turns": _normalize_turns(obj)}
    except Exception:
        pass
    # JSONL: 取第一条含 turns 的对话
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict) and obj.get("turns"):
                return {"dialogue_id": obj.get("dialogue_id", "uploaded"), "turns": _normalize_turns(obj["turns"])}
        except Exception:
            continue
    # 兜底: 当成"角色: 内容"文本
    return _parse_dialogue_text(raw)


_VERDICT_CN = {"pass": "✅ pass", "fail": "❌ fail", "na": "➖ na",
               "not_implemented": "⚪ 未判定", "error": "⚠️ error"}


def render_single_dialogue(output, rubric_label, dialogue):
    """渲染单通对话评测结果: P3 分 + 5 维 + 逐约束判定 + 对话回放"""
    sr = output.get("score_report", {})
    vds = output.get("verdict_details", [])
    score = sr.get("final_score")
    st.markdown("---")
    st.markdown("## 📋 这通对话的评测结果")

    if score is None:
        st.error("无法对这通对话评分(可能对话为空, 或全部约束 na/未判定)。"
                 "若用的是内置通用标准, 多数约束需真实 LLM 判定 → 请设置 DEEPSEEK_API_KEY 后重跑。")
    else:
        c1, c2, grade = grade_color(score)
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, {c1} 0%, {c2} 100%);
                    padding: 30px; border-radius: 18px; text-align: center; color: white;
                    box-shadow: 0 8px 32px rgba(0,0,0,0.2);">
            <div style="font-size: 14px; opacity: 0.85;">评分标尺: {rubric_label}</div>
            <div style="font-size: 64px; font-weight: 900; line-height: 1.1;">{score}<span style="font-size: 24px;"> / 100</span></div>
            <div style="display: inline-block; padding: 4px 20px; background: rgba(255,255,255,0.25);
                        border-radius: 18px; font-size: 15px; margin-top: 8px;">{grade}</div>
        </div>
        """, unsafe_allow_html=True)

    # 5 维度
    dims = sr.get("dim_scores", {})
    cols = st.columns(5)
    for i, (k, label) in enumerate(DIM_SHORT.items()):
        with cols[i]:
            v = dims.get(k)
            st.metric(label, "—" if v is None else f"{v:.0f}")

    # 逐约束判定分布 + 表
    from collections import Counter
    dist = Counter(v.get("verdict") for v in vds)
    st.caption("逐约束判定: " + " · ".join(f"{_VERDICT_CN.get(k, k)}×{n}" for k, n in dist.items()))
    import pandas as pd
    rows = [{
        "约束": (v.get("constraint_name", "") or "")[:34],
        "判定": _VERDICT_CN.get(v.get("verdict"), v.get("verdict")),
        "Verifier": VERIFIER_SHORT.get(v.get("verifier_type"), v.get("verifier_type")),
        "理由/证据": (str(v.get("reason", "")) + " " + str(v.get("evidence", ""))).strip()[:100],
    } for v in vds]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    st.caption("说明: na=约束在该对话未触发; 未判定=mock 模式下主观约束无法离线判(设 key 真跑可消除)。")

    with st.expander("💬 查看这通对话原文"):
        for t in dialogue.get("turns", []):
            who = "🧑‍💼 客服" if t.get("role") == "assistant" else "🙋 用户"
            st.markdown(f"**{who}**(turn{t.get('turn')}): {t.get('content', '')}")

    st.download_button("📥 下载评测结果 (JSON)",
                       json.dumps(output, ensure_ascii=False, indent=2),
                       file_name="single_dialogue_eval.json", mime="application/json")


def _simulate_dialogue_from_prompt(prompt_text, model="deepseek-v4-flash"):
    """根据用户的大致描述, 调 LLM 现场生成一段多轮对话(供'大致描述'路径)。需 API key。"""
    from llm_client import call_llm
    gen_prompt = (
        "根据下面的【描述】生成一段多轮中文对话(外呼/客服场景)。"
        "客服方 role=assistant, 用户方 role=user, 双方交替发言, 6-12 轮, "
        "贴合描述里的人物性格与场景, 自然口语化。\n\n"
        f"【描述】{prompt_text}\n\n"
        '只输出 JSON: {"turns":[{"turn":1,"role":"assistant","content":"..."},'
        '{"turn":2,"role":"user","content":"..."}]}'
    )
    try:
        facts = call_llm(gen_prompt, model=model, system="你是对话生成器, 只输出 JSON.", max_tokens=2000)
    except Exception:
        return None
    turns = facts.get("turns") if isinstance(facts, dict) else None
    if not turns:
        return None
    norm = _normalize_turns(turns)
    return {"dialogue_id": "simulated_from_prompt", "turns": norm} if norm else None


def _eval_single_dialogue(dialogue, instruction, rubric_label, status_box=None):
    """对一通对话跑 run_pipeline 并存结果到 session(自定义对话/大致描述共用)。"""
    has_key = bool(os.getenv("DEEPSEEK_API_KEY"))
    os.environ["VERIFIER_LLM_MOCK"] = "0" if has_key else "1"
    os.environ.setdefault("VERIFIER_LLM_MODEL", "deepseek-v4-flash")
    if not has_key:
        st.warning("未检测到 DEEPSEEK_API_KEY → mock 预览: 通用约束(llm_judge)多会显示“未判定”。"
                   "设好 key 再重跑可拿到完整逐约束判定。")
    try:
        from pipeline import run_pipeline
        t0 = time.time()
        output = run_pipeline(instruction, dialogue)
        st.session_state["sd_output"] = output
        st.session_state["sd_rubric_label"] = rubric_label
        st.session_state["sd_dialogue"] = dialogue
        if status_box is not None:
            status_box.update(label=f"✅ 完成 · 用时 {int(time.time() - t0)}s", state="complete", expanded=False)
    except Exception as e:
        if status_box is not None:
            status_box.update(label="❌ 评测失败", state="error", expanded=True)
        st.error(f"评测失败: {e}")
        st.exception(e)


def _render_dialogue_input(key_prefix):
    """对话输入控件(上传 或 粘贴), 返回解析后的 dialogue dict 或 None。格式为【建议非强制】。"""
    with st.expander("💡 建议的对话格式 (非强制 · 点开看示例)", expanded=False):
        st.markdown("**推荐**: 每行 `角色: 内容`,角色用「客服 / 用户」(也认 坐席/客户/assistant/user 等):")
        st.code("客服: 喂您好，是张师傅吗？我是美团客服小王，跟您说个事\n"
                "用户: 是的，啥事\n"
                "客服: 您那个订单超时了，咱核实下原因哈\n"
                "用户: 对，店里太忙了", language="text")
        st.markdown("也支持**上传系统原生 `.jsonl`**(含 turns 字段)。")
        st.caption("⚠️ 不按此格式也能评:系统会按行交替猜测「客服/用户」。但角色可能猜不准 → "
                   "**影响评测质量**,建议尽量按上面格式标好角色。")
    up_d = st.file_uploader("上传对话 (.jsonl/.json)", type=["jsonl", "json", "txt"], key=f"{key_prefix}_up")
    pasted_d = st.text_area(
        "或直接粘贴对话 (建议每行 “客服: …” / “用户: …”,不标也能评)", height=200, key=f"{key_prefix}_text",
        placeholder="客服: 喂您好，是张师傅吗？我是美团客服小王，跟您说个事…\n用户: 是的，啥事\n客服: 就是…",
    )
    dialogue = None
    if up_d is not None:
        dialogue = _load_dialogue_from_upload(up_d)
    elif pasted_d.strip():
        dialogue = _parse_dialogue_text(pasted_d)
    if dialogue and dialogue.get("turns"):
        n = len(dialogue["turns"])
        na = sum(1 for t in dialogue["turns"] if t["role"] == "assistant")
        st.success(f"✓ 已解析 **{n} 轮**对话 (客服 {na} 轮 / 用户 {n - na} 轮)")
        if dialogue.get("_weak_format"):
            st.warning("⚠️ 没检测到「角色:」标注,已**按行交替猜测**角色(客服/用户/客服…)。"
                       "若猜得不对会影响评测质量,建议用「客服: / 用户:」标好角色再评。")
        with st.expander("预览解析结果 (确认角色分对了)"):
            for t in dialogue["turns"][:14]:
                who = "🧑‍💼客服" if t["role"] == "assistant" else "🙋用户"
                st.caption(f"{t['turn']}. {who}: {t['content'][:90]}")
    elif (up_d is not None) or pasted_d.strip():
        st.warning("没解析出对话内容,请检查粘贴的文本或上传的文件是否为空。")
    return dialogue


def render_custom_dialogue_flow():
    """自定义→💬自定义对话: 用户直接给一通对话 → 用内置通用质检标准直接评(不生成)。"""
    st.markdown("#### 💬 直接给一通对话 → 评测")
    st.caption("你已经有一通对话(真实通话转写/自己写的), 直接评它。用**内置通用外呼质检标准**"
               "(开场身份/礼貌/口语化/避免重复/准确回应/推进/让出话轮/收尾)评通话质量, 不再生成对话。")
    dialogue = _render_dialogue_input("cd")
    st.markdown("##### 运行评测")
    if st.button("🔍 评测这通对话", type="primary", use_container_width=True, key="cd_run"):
        if not (dialogue and dialogue.get("turns")):
            st.error("请先给一通可解析的对话。")
            return
        with st.status("正在逐约束评测这通对话…", expanded=True) as box:
            _eval_single_dialogue(dialogue, _load_generic_rubric(), "内置通用外呼质检标准", status_box=box)
    if "sd_output" in st.session_state:
        render_single_dialogue(st.session_state["sd_output"],
                               st.session_state.get("sd_rubric_label", ""),
                               st.session_state.get("sd_dialogue", {}))


def render_rough_sim_flow():
    """自定义→✏️大致描述: 用户给大概意思 → 据此模拟一通对话 → 用内置通用质检标准评。"""
    st.markdown("#### ✏️ 给个大致描述 → 系统模拟对话 → 评测")
    st.caption("用一句话描述你想要的对话, 系统据此**自动模拟生成一通对话**, 再用内置通用质检标准评。"
               "例: 「生成一段易怒型用户和数字人客服关于外卖超时的对话」。需 DEEPSEEK_API_KEY。")
    prompt_text = st.text_area("大致描述 / 场景 prompt", height=120, key="rs_text",
                               placeholder="例: 生成一段易怒型用户和数字人客服关于外卖超时的对话")
    if st.button("🎬 模拟对话并评测", type="primary", use_container_width=True, key="rs_run"):
        if not prompt_text.strip():
            st.error("请先输入大致描述。")
            return
        if not os.getenv("DEEPSEEK_API_KEY"):
            st.error("模拟对话需调用 LLM, 但未检测到 DEEPSEEK_API_KEY。"
                     "请在启动 streamlit 的终端设好 key 再重跑。")
            return
        os.environ["VERIFIER_LLM_MOCK"] = "0"
        os.environ.setdefault("VERIFIER_LLM_MODEL", "deepseek-v4-flash")
        with st.status("正在根据描述模拟对话…", expanded=True) as box:
            dialogue = _simulate_dialogue_from_prompt(prompt_text)
            if not (dialogue and dialogue.get("turns")):
                box.update(label="❌ 模拟失败", state="error", expanded=True)
                st.error("没能生成对话, 请换个描述或检查 key/网络。")
                return
            st.write(f"✓ 已模拟 {len(dialogue['turns'])} 轮对话, 开始逐约束评测…")
            _eval_single_dialogue(dialogue, _load_generic_rubric(), "内置通用外呼质检标准", status_box=box)
    if "sd_output" in st.session_state:
        render_single_dialogue(st.session_state["sd_output"],
                               st.session_state.get("sd_rubric_label", ""),
                               st.session_state.get("sd_dialogue", {}))


def _parse_custom_instruction_for_modeleval():
    """自定义→📋完整任务指令: 上传/粘贴指令 → 现场解析(mock 启发式) → 落临时文件 →
    供下方"模型评测流程"使用(8 Persona 多场景模拟 + 逐约束评测 + 模型画像)。
    返回 (parsed_dict, instr_name, has_demo) 或 (None, None, False)。复用后端 parser, 不改后端。"""
    up = st.file_uploader("📤 上传任务指令 (.md / .txt)", type=["md", "txt"], key="mi_up")
    pasted = st.text_area(
        "✍️ 或直接粘贴任务指令 (Markdown)", height=240, key="mi_text",
        placeholder="# Role ...\n# Task ...\n# Constraints ...\n# Knowledge Points (FAQ) ...\n# Call Flow ...",
    )
    md_text = up.getvalue().decode("utf-8", errors="replace") if up is not None else pasted
    if up is not None:
        st.caption(f"📎 已读取「{up.name}」({len(md_text)} 字符 / {md_text.count(chr(10)) + 1} 行)")
    if not md_text.strip():
        st.info("👆 粘贴任务指令或上传 .md 后, 系统会解析出约束清单, 再用 8 Persona 模拟多场景对话并评测该模型。")
        return None, None, False
    try:
        parse_instruction = _load_parse_instruction()
        with st.spinner("正在解析指令、拆解约束清单…"):
            parsed_obj = parse_instruction(md_text, instruction_id="CUSTOM",
                                           instruction_name="自定义指令", mock=True)
            parsed = parsed_obj.to_dict()
    except Exception as e:
        st.error(f"❌ 指令解析失败: {e}")
        return None, None, False
    if not parsed.get("atomic_constraints"):
        st.warning("⚠️ 没能从这段文本解析出约束, 请确认是结构化外呼指令(建议含 # Constraints / # Call Flow 段)。")
        return None, None, False
    tmp = Path(tempfile.gettempdir())
    p_path = tmp / "custom_instruction_parsed.json"
    m_path = tmp / "custom_instruction.md"
    p_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
    m_path.write_text(md_text, encoding="utf-8")
    st.session_state["me_instruction_parsed_path"] = str(p_path)
    st.session_state["me_instruction_md_path"] = str(m_path)
    st.session_state["me_instruction_name"] = "custom_instruction"
    return parsed, "custom_instruction", False


# ============================================================
# 主流程
# ============================================================
# ---- 侧边栏: 极简高级品牌看板 (共享主题) ----
_theme.render_sidebar_brand()

# ---- 主页 Hero (共享主题) ----
_theme.render_page_header(
    "对话外呼指令遵循 · 自动评测系统",
    "输入任务指令或对话 &nbsp;→&nbsp; 自动模拟 / 评测 &nbsp;→&nbsp; 可解释的模型能力画像")

# ---- 能力数字条: 干净白卡 ----
st.markdown("""
<div style="display:flex;gap:12px;margin:22px 0 8px;">
  <div style="flex:1;background:#fff;border:1px solid #eceff3;border-radius:12px;padding:14px 16px;">
    <div style="font-size:22px;font-weight:800;color:#1a2233;">23<span style="font-size:13px;font-weight:600;color:#6b7585;"> 类</span></div>
    <div style="font-size:12px;color:#9aa3b2;margin-top:3px;">约束分类体系</div></div>
  <div style="flex:1;background:#fff;border:1px solid #eceff3;border-radius:12px;padding:14px 16px;">
    <div style="font-size:22px;font-weight:800;color:#1a2233;">5<span style="font-size:13px;font-weight:600;color:#6b7585;"> 类</span></div>
    <div style="font-size:12px;color:#9aa3b2;margin-top:3px;">Verifier 分层</div></div>
  <div style="flex:1;background:#fff;border:1px solid #eceff3;border-radius:12px;padding:14px 16px;">
    <div style="font-size:22px;font-weight:800;color:#1a2233;">8<span style="font-size:13px;font-weight:600;color:#6b7585;"> 种</span></div>
    <div style="font-size:12px;color:#9aa3b2;margin-top:3px;">用户模拟 Persona</div></div>
  <div style="flex:1;background:#fff;border:1px solid #eceff3;border-radius:12px;padding:14px 16px;">
    <div style="font-size:22px;font-weight:800;color:#b8860b;">0.81</div>
    <div style="font-size:12px;color:#9aa3b2;margin-top:3px;">三路 LLM 互查 κ</div></div>
</div>
""", unsafe_allow_html=True)
st.markdown("---")

# ---- 第 1 步: 选择任务指令来源 ----
st.markdown("### 1️⃣ 选择任务指令")
input_mode = st.radio(
    "指令来源",
    ["📚 从预置指令选择", "✍️ 自定义输入"],
    horizontal=True, label_visibility="collapsed",
)

parsed = None
instr_name = None
has_demo = False

if input_mode.startswith("📚"):
    # ===== 预置指令 → 模型评测流程 =====
    instr_label = st.selectbox("任务指令", list(INSTRUCTIONS.keys()), label_visibility="collapsed")
    instr_cfg = INSTRUCTIONS[instr_label]
    instr_name = instr_cfg["name"]
    has_demo = instr_cfg["has_demo"]
    parsed = load_parsed(instr_cfg)
    if parsed:
        st.session_state["me_instruction_parsed_path"] = str(instr_cfg["parsed"])
        st.session_state["me_instruction_md_path"] = str(instr_cfg["md"])
        st.session_state["me_instruction_name"] = instr_name
    else:
        st.warning(f"⚠️ 未找到预解析文件,请确认 {instr_cfg['parsed']}")
else:
    # ===== 自定义输入: 三个子选项 =====
    custom_mode = st.radio(
        "自定义方式",
        ["📋 我有完整任务指令 (解析 → 多场景模拟 → 评模型)",
         "💬 我直接给一通对话 (直接评测, 不生成对话)",
         "✏️ 我给个大致描述 (据此模拟一通对话再评测)"],
        key="custom_mode",
    )
    st.markdown("---")
    if custom_mode.startswith("💬"):
        # 单通: 给对话 → 通用质检, 独立流程
        render_custom_dialogue_flow()
        st.stop()
    elif custom_mode.startswith("✏️"):
        # 单通: 大致描述 → 模拟一通 → 通用质检, 独立流程
        render_rough_sim_flow()
        st.stop()
    else:
        # 📋 完整任务指令 → 解析 → 落入下方"模型评测流程"(不 st.stop, 与预置共用 Step2/3)
        st.markdown("#### 📋 输入完整任务指令 → 评测模型")
        st.caption("粘贴/上传你自己的外呼任务指令(像官方样本那样含 Role / Task / Constraints / FAQ / Call Flow), "
                   "系统解析出约束清单, 再用 8 Persona 模拟多场景对话, 评测该模型对这份指令的遵循能力 → 模型画像。")
        parsed, instr_name, has_demo = _parse_custom_instruction_for_modeleval()
        if not parsed:
            st.stop()

# ---- 解析结果展示 (两种来源通用) ----
constraints = []
if parsed:
    constraints = parsed.get("atomic_constraints", [])
    n_crit = sum(1 for c in constraints if c.get("is_critical"))
    from collections import Counter
    dim_dist = Counter(DIM_SHORT.get(c.get("scoring_dimension",""), "?").split()[0] for c in constraints)
    dim_summary = " / ".join(f"{v}{k}" for k, v in sorted(dim_dist.items()))
    st.success(f"✓ 已自动识别 **{len(constraints)} 条约束** ({n_crit} 条关键) · 维度分布: {dim_summary}")

    with st.expander("📋 查看约束清单 + 分布图", expanded=not input_mode.startswith("📚")):
        import pandas as pd
        df = pd.DataFrame([{
            "ID": c["id"], "关键": "🔴" if c.get("is_critical") else "",
            "Verifier": VERIFIER_SHORT.get(c["verifier"], c["verifier"]),
            "维度": DIM_SHORT.get(c.get("scoring_dimension",""), "?"),
            "约束名": c["name"][:60],
        } for c in constraints])
        st.dataframe(df, use_container_width=True, hide_index=True)
        try:
            import plotly.express as px
            vc = Counter(VERIFIER_SHORT.get(c["verifier"], c["verifier"]) for c in constraints)
            fig = px.pie(names=list(vc.keys()), values=list(vc.values()), hole=0.4,
                         color_discrete_sequence=px.colors.qualitative.Set2)
            fig.update_layout(height=280, margin=dict(l=10,r=10,t=10,b=10))
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            pass

st.markdown("---")

# ---- 第 2 步: 运行评测 ----
# 设计: 粘完/选完指令, 下一步直接就是"运行评测"。选模型+选场景折叠进可选设置,
# 默认值即可, 不再当成挡路的独立步骤(对齐用户反馈)。
st.markdown("### 2️⃣ 运行评测")

with st.expander("⚙️ 模拟与评测设置 (可选, 默认即可)", expanded=False):
    tested_model = st.selectbox(
        "待测模型 (让哪个模型来演「客服」生成模拟对话)",
        ["deepseek-v4-flash", "deepseek-v4-pro", "gpt-4o-mini", "gpt-5-mini"])
    st.markdown("**模拟哪些用户场景** (勾几个 = 根据指令模拟生成几通不同用户的对话)")
    persona_cols = st.columns(4)
    selected_personas = []
    persona_items = list(PERSONAS.items())
    # 快速演示有真实数据的 4 个核心场景
    FAST_AVAIL = {"cooperative", "refuse_persistent", "out_of_scope", "interruption"}
    for i, (pid, pname) in enumerate(persona_items):
        with persona_cols[i % 4]:
            default = pid in ("cooperative", "out_of_scope")
            label = pname if pid in FAST_AVAIL else f"{pname}*"
            if st.checkbox(label, value=default, key=f"persona_{pid}"):
                selected_personas.append(pid)
    st.caption("标 * 的场景仅 **完整运行** 模式支持(快速演示只含 4 个核心场景的真实数据)")

# 模式: 预置指令才有「快速演示」; 自定义/上传指令只有「完整运行」(真模拟生成对话)
mode_options = ["🔬 完整运行 (根据指令自动模拟对话 + 评测, 需 API key, 几分钟)"]
if has_demo:
    mode_options = ["⚡ 快速演示 (读预置真实结果, 秒出)"] + mode_options
mode = st.radio("评测模式", mode_options, label_visibility="collapsed")
is_fast = "快速演示" in mode

if is_fast:
    st.caption("ℹ️ 快速演示读取用 deepseek-flash 真实跑出的历史评测结果 (非 mock, 不重新模拟)")
else:
    st.caption(f"▶️ 点下面按钮 → 系统会**根据上面这份任务指令, 用 {tested_model} 自动模拟 "
               f"{len(selected_personas)} 个用户场景的对话**, 再逐约束评测 → 出模型能力画像。"
               f"(想换模型/场景点上方 ⚙️ 设置)")

run_clicked = st.button(
    "🚀 运行评测 (读预置结果)" if is_fast else "🚀 运行评测 (根据指令自动模拟对话并评测)",
    type="primary", use_container_width=True)

# 运行逻辑
if run_clicked:
    if not selected_personas:
        st.error("请展开「⚙️ 模拟与评测设置」至少勾选一个用户场景(默认已勾合作型/越界型)")
    elif not constraints:
        st.error("指令未成功解析,无法评测")
    else:
        from model_evaluation import run_fast_demo, run_full_evaluation

        if is_fast:
            with st.spinner("读取预置结果并聚合..."):
                report = run_fast_demo(instr_name, tested_model)
                if tested_model != "deepseek-v4-flash" and not report.get("error"):
                    st.info(f"ℹ️ 快速演示回放的是 **deepseek-v4-flash** 的真实历史评测数据，"
                            f"与你选的「{tested_model}」无关；要真正评测「{tested_model}」请改用 **完整运行**。")
                if not report.get("error"):
                    # 预置数据实际覆盖的场景
                    avail = set(r.get("persona_id") for r in report["per_dialogue_results"])
                    sel = set(selected_personas)
                    matched = sel & avail
                    missing = sel - avail
                    if missing:
                        miss_names = ", ".join(PERSONAS.get(p, p) for p in missing)
                        st.warning(f"⚠️ 快速演示只含 4 个核心场景的真实数据。"
                                   f"勾选的 [{miss_names}] 无预置数据,已跳过。"
                                   f"如需评测这些场景,请用 **完整运行** 模式真跑。")
                    # 按匹配到的场景筛选 (若一个都没匹配, 用全部预置场景兜底)
                    use = matched if matched else avail
                    report["per_dialogue_results"] = [
                        r for r in report["per_dialogue_results"]
                        if r.get("persona_id") in use]
                    from model_evaluation import aggregate_model_report
                    report = aggregate_model_report(report["instruction_name"],
                                                     report["model_name"],
                                                     report["per_dialogue_results"])
            st.session_state["me_model_report"] = report
            st.session_state["me_report_sig"] = (instr_name, tested_model,
                                                 tuple(sorted(selected_personas)), is_fast)
        else:
            # 完整模式真跑 —— 先检查 API key, 缺了直接拦下, 不跑垃圾报告
            import os
            need_key, key_name = None, None
            if tested_model.startswith("deepseek"):
                need_key, key_name = os.getenv("DEEPSEEK_API_KEY"), "DEEPSEEK_API_KEY"
            elif tested_model.startswith("gpt"):
                need_key, key_name = os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY"

            if not need_key:
                st.error(
                    f"❌ 完整运行需要调用 **{tested_model}** 生成对话,但未检测到 `{key_name}`。\n\n"
                    f"**解决办法**: 在启动 streamlit 的终端里先设置环境变量,再重启:\n"
                    f"```bash\nexport {key_name}=你的key\nstreamlit run app.py\n```\n"
                    f"或者选择 **⚡ 快速演示** 模式(用 V1-V5 预置的真实结果,无需 key)。"
                )
            else:
                md_text = Path(st.session_state["me_instruction_md_path"]).read_text(encoding="utf-8")
                t0 = time.time()
                # st.status: 自带客户端旋转动画(评测阻塞期间仍会转, 消除"像卡死了"的观感) + 可展开滚动日志
                with st.status(f"🔬 正在评测模型「{tested_model}」…", expanded=True) as status_box:
                    st.write(f"将对 **{len(selected_personas)} 个场景**逐一真跑「对话生成 + 逐约束评测」，"
                             f"每个场景需真调模型生成多轮对话再判定，**单场景约数十秒**。"
                             f"生成对话期间进度条会短暂停顿(属正常)，请勿关闭页面。")
                    progress = st.progress(0.0)

                    def cb(cur, total, msg):
                        # 两段式进度: 同一场景内"生成对话"占前 70%、"评测"占后 30%, 让进度在场景内部也推进
                        if "聚合" in msg:
                            frac = 1.0
                        else:
                            phase = 0.7 if "评测" in msg else 0.0
                            frac = min((cur + phase) / max(total, 1), 1.0)
                        progress.progress(frac)
                        st.write(f"[{min(cur + 1, total)}/{total}] {msg}　·　已用 {int(time.time() - t0)}s")

                    try:
                        report = run_full_evaluation(
                            instruction_path=st.session_state["me_instruction_parsed_path"],
                            instruction_text=md_text,
                            instruction_name=instr_name,
                            model_name=tested_model,
                            persona_list=selected_personas,
                            progress_callback=cb,
                        )
                        took = int(time.time() - t0)
                        results = report.get("per_dialogue_results", [])
                        # 全部空对话(API 跑挂) → 报错而非展示垃圾分
                        if results and all(d.get("n_turns", 0) == 0 for d in results):
                            err_msgs = set()
                            for d in results:
                                e = d.get("error") or d.get("dialogue", {}).get("metadata", {}).get("error")
                                if e:
                                    err_msgs.add(str(e)[:100])
                            status_box.update(label="❌ 评测失败：所有场景对话为空", state="error", expanded=True)
                            st.error(
                                "❌ 对话生成失败,所有场景都是空对话(因此分数无意义)。\n\n"
                                f"底层报错: {' / '.join(err_msgs) if err_msgs else '未知'}\n\n"
                                "通常是 API key 无效、余额不足或网络问题。请检查后重试,或用快速演示模式。"
                            )
                        else:
                            # 部分场景失败(空对话/报错) → 提示, 避免 0 分被误读成"模型很差"(CLAUDE.md 坑#3)
                            failed = [d.get("persona_id", "?") for d in results
                                      if d.get("n_turns", 0) == 0 or d.get("error")]
                            if failed:
                                names = ", ".join(PERSONAS.get(p, p) for p in failed)
                                st.warning(f"⚠️ 有 {len(failed)} 个场景对话生成失败([{names}])，已记 0 分并拉低均分——"
                                           "这是报错而非模型真实能力，建议重试这些场景。")
                            st.session_state["me_model_report"] = report
                            st.session_state["me_report_sig"] = (instr_name, tested_model,
                                                                 tuple(sorted(selected_personas)), is_fast)
                            status_box.update(label=f"✅ 评测完成 · 共用时 {took}s · {len(results)} 个场景",
                                              state="complete", expanded=False)
                    except Exception as e:
                        status_box.update(label="❌ 完整运行失败", state="error", expanded=True)
                        st.error(f"完整运行失败: {e}")
                        st.exception(e)

# ---- 结果展示 ----
if "me_model_report" in st.session_state:
    cur_sig = (instr_name, tested_model, tuple(sorted(selected_personas)), is_fast)
    stale = st.session_state.get("me_report_sig") != cur_sig
    st.markdown("---")
    st.markdown("## 📈 模型能力画像")
    if stale:
        st.warning("⚠️ 下方是**上一次运行**的模型画像；当前的指令/模型/场景已改动。"
                   "如需评测当前配置，请重新点击「🚀 开始评测模型」。")
    render_model_report(st.session_state["me_model_report"])
