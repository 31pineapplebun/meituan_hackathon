"""美团对话外呼任务评测系统 - 一站式主入口"""
import json
import os
from collections import Counter
from pathlib import Path

import streamlit as st

from bootstrap import setup_paths
from config.instructions import INSTRUCTIONS
from config.labels import DIM_SHORT, PERSONAS, VERIFIER_SHORT
from state.session_keys import (
    DETAIL_DIALOGUES,
    INSTRUCTION_MD_PATH,
    INSTRUCTION_PARSED_PATH,
    MODEL_REPORT,
    set_instruction_state,
)
from ui.report import render_model_report
from ui.styles import GLOBAL_CSS

setup_paths()

st.set_page_config(page_title="美团对话外呼评测系统", page_icon="🎯", layout="wide", initial_sidebar_state="expanded")
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


def load_parsed(instr_cfg):
    p = instr_cfg["parsed"]
    if p and Path(p).exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return None


def render_instruction_panel(instr_name: str, instr_cfg: dict):
    parsed = load_parsed(instr_cfg)
    if not parsed:
        st.warning(f"⚠️ 未找到预解析文件,请确认 {instr_cfg['parsed']}")
        return []

    constraints = parsed.get("atomic_constraints", [])
    n_crit = sum(1 for c in constraints if c.get("is_critical"))
    dim_dist = Counter(DIM_SHORT.get(c.get("scoring_dimension", ""), "?").split()[0] for c in constraints)
    dim_summary = " / ".join(f"{v}{k}" for k, v in sorted(dim_dist.items()))
    st.success(f"✓ 已自动识别 **{len(constraints)} 条约束** ({n_crit} 条关键) · 维度分布: {dim_summary}")

    with st.expander("📋 查看约束清单 + 分布图"):
        import pandas as pd
        df = pd.DataFrame([
            {
                "ID": c["id"],
                "关键": "🔴" if c.get("is_critical") else "",
                "Verifier": VERIFIER_SHORT.get(c["verifier"], c["verifier"]),
                "维度": DIM_SHORT.get(c.get("scoring_dimension", ""), "?"),
                "约束名": c["name"][:60],
            }
            for c in constraints
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)
        try:
            import plotly.express as px
            vc = Counter(VERIFIER_SHORT.get(c["verifier"], c["verifier"]) for c in constraints)
            fig = px.pie(
                names=list(vc.keys()),
                values=list(vc.values()),
                hole=0.4,
                color_discrete_sequence=px.colors.qualitative.Set2,
            )
            fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        except ImportError:
            pass

    set_instruction_state(st, str(instr_cfg["parsed"]), str(instr_cfg["md"]), instr_name)
    return constraints


st.title("🎯 评测模型 — 一站式指令遵循能力评估")
st.caption("输入任务指令 + 选择待测模型 → 自动模拟多场景对话并评测 → 产出模型能力画像")
st.markdown("---")

st.markdown("### 1️⃣ 选择任务指令")
instr_label = st.selectbox("任务指令", list(INSTRUCTIONS.keys()), label_visibility="collapsed")
instr_cfg = INSTRUCTIONS[instr_label]
instr_name = instr_cfg["name"]
constraints = render_instruction_panel(instr_name, instr_cfg)

st.markdown("---")
st.markdown("### 2️⃣ 选择待测模型 + 测试场景")
col_a, col_b = st.columns([1, 2])
with col_a:
    st.markdown("**待测模型** (被评测的对象)")
    tested_model = st.selectbox(
        "待测模型", ["deepseek-v4-flash", "deepseek-v4-pro", "gpt-4o-mini", "gpt-5-mini"], label_visibility="collapsed"
    )
with col_b:
    st.markdown("**测试场景** (勾几个跑几通,模拟不同用户)")
    persona_cols = st.columns(4)
    selected_personas = []
    fast_avail = {"cooperative", "refuse_persistent", "out_of_scope", "interruption"}
    for i, (pid, pname) in enumerate(PERSONAS.items()):
        with persona_cols[i % 4]:
            default = pid in ("cooperative", "out_of_scope")
            label = pname if pid in fast_avail else f"{pname}*"
            if st.checkbox(label, value=default, key=f"persona_{pid}"):
                selected_personas.append(pid)
    st.caption("标 * 的场景仅完整运行支持(快速演示只含 4 个核心场景)")

st.markdown("---")
st.markdown("### 3️⃣ 运行评测")
col_m, col_run = st.columns([2, 1])
with col_m:
    has_demo = instr_cfg["has_demo"]
    mode_options = ["🔬 完整运行 (真跑, 需 API key, 几分钟)"]
    if has_demo:
        mode_options = ["⚡ 快速演示 (预置真实结果, 秒出)"] + mode_options
    mode = st.radio("评测模式", mode_options, label_visibility="collapsed")
    is_fast = "快速演示" in mode
with col_run:
    st.markdown("<br>", unsafe_allow_html=True)
    run_clicked = st.button("🚀 开始评测模型", type="primary", use_container_width=True)

if run_clicked:
    if not selected_personas:
        st.error("请至少勾选一个测试场景")
    elif not constraints:
        st.error("指令未成功解析,无法评测")
    else:
        from model_evaluation import aggregate_model_report, run_fast_demo, run_full_evaluation

        if is_fast:
            with st.spinner("读取预置结果..."):
                report = run_fast_demo(instr_name, tested_model)
                if not report.get("error"):
                    avail = set(r.get("persona_id") for r in report["per_dialogue_results"])
                    sel = set(selected_personas)
                    matched = sel & avail
                    missing = sel - avail
                    if missing:
                        miss_names = ", ".join(PERSONAS.get(p, p) for p in missing)
                        st.warning(f"⚠️ 快速演示无 [{miss_names}] 预置数据,已跳过。")
                    use = matched if matched else avail
                    report["per_dialogue_results"] = [r for r in report["per_dialogue_results"] if r.get("persona_id") in use]
                    report = aggregate_model_report(report["instruction_name"], report["model_name"], report["per_dialogue_results"])
                st.session_state[MODEL_REPORT] = report
                st.session_state[DETAIL_DIALOGUES] = report.get("per_dialogue_results", []) if not report.get("error") else []
        else:
            need_key, key_name = None, None
            if tested_model.startswith("deepseek"):
                need_key, key_name = os.getenv("DEEPSEEK_API_KEY"), "DEEPSEEK_API_KEY"
            elif tested_model.startswith("gpt"):
                need_key, key_name = os.getenv("OPENAI_API_KEY"), "OPENAI_API_KEY"

            if not need_key:
                st.error(f"❌ 完整运行需 `{key_name}`，请先配置环境变量后重启。")
            else:
                md_text = Path(st.session_state[INSTRUCTION_MD_PATH]).read_text(encoding="utf-8")
                progress = st.progress(0.0)
                status = st.empty()

                def cb(cur, total, msg):
                    progress.progress(min(cur / max(total, 1), 1.0))
                    status.text(f"[{cur + 1}/{total}] {msg}")

                try:
                    report = run_full_evaluation(
                        instruction_path=st.session_state[INSTRUCTION_PARSED_PATH],
                        instruction_text=md_text,
                        instruction_name=instr_name,
                        model_name=tested_model,
                        persona_list=selected_personas,
                        progress_callback=cb,
                    )
                    empty = all(d.get("n_turns", 0) == 0 for d in report.get("per_dialogue_results", []))
                    if empty:
                        st.error("❌ 对话生成失败,所有场景为空。请检查 API key/余额/网络。")
                    else:
                        st.session_state[MODEL_REPORT] = report
                        st.session_state[DETAIL_DIALOGUES] = report.get("per_dialogue_results", [])
                except Exception as e:
                    st.error(f"完整运行失败: {e}")
                    st.exception(e)
                finally:
                    progress.empty()
                    status.empty()

if MODEL_REPORT in st.session_state:
    st.markdown("---")
    st.markdown("## 📈 模型能力画像")
    render_model_report(st, st.session_state[MODEL_REPORT])