"""
单通详查 - 看某一通对话的逐约束判定细节

数据来源: 主页评测后,session 里的 per_dialogue_results
"""
import streamlit as st
import json

st.set_page_config(page_title="单通详查", page_icon="📂", layout="wide")

PERSONAS = {
    "cooperative": "🤝 合作型", "adversarial": "⚔️ 对抗型",
    "out_of_scope": "🌀 越界提问型", "interruption": "✋ 打断型",
    "refuse_persistent": "😤 坚持拒绝型", "state_busy": "🚗 状态型",
    "ambiguous": "🤔 模糊型", "probing": "❓ 提问型",
}

st.title("📂 单通对话详查")
st.caption("查看某一通对话的完整内容 + 逐约束判定 + 证据")
st.markdown("---")

dialogues = st.session_state.get("detail_dialogues", [])

if not dialogues:
    st.warning("⚠️ 还没有可查看的对话。请先在 **🎯 评测模型** 主页跑一次评测。")
    st.page_link("app.py", label="← 回到评测主页")
    st.stop()

# 选一通
options = {}
for r in dialogues:
    pid = r.get("persona_id", "?")
    score = r.get("score_report", {}).get("final_score", "?")
    label = f"{PERSONAS.get(pid, pid)} — {score} 分 ({r.get('dialogue_id','?')[:30]})"
    options[label] = r

sel_label = st.selectbox("选择对话", list(options.keys()))
r = options[sel_label]

# 该通概览
sr = r.get("score_report", {})
c1, c2, c3, c4 = st.columns(4)
c1.metric("本通得分", f"{sr.get('final_score','?')}/100")
c2.metric("场景", PERSONAS.get(r.get("persona_id"), r.get("persona_id", "?")))
c3.metric("Critical 通过率", f"{sr.get('critical_pass_rate',0)*100:.0f}%")
c4.metric("轮数", r.get("n_turns", "?"))

st.markdown("---")

col_l, col_r = st.columns([1, 1])

# 左: 对话内容
with col_l:
    st.markdown("##### 💬 对话内容")
    dlg = r.get("dialogue", {})
    turns = dlg.get("turns", [])
    if turns:
        for t in turns:
            role = t.get("role", "?")
            content = t.get("content", "")
            turn = t.get("turn", "?")
            if role == "assistant":
                st.markdown(f"🤖 **T{turn}** ({len(content)}字): {content}")
            else:
                st.markdown(f"👤 **T{turn}** ({len(content)}字): {content}")
    else:
        st.caption("(此对话来自预置演示数据,未保存逐轮内容;完整模式真跑会有完整对话)")

# 右: 逐约束判定
with col_r:
    st.markdown("##### 📋 逐约束判定")
    verdicts = r.get("verdict_details", [])
    if verdicts:
        import pandas as pd
        def color_v(val):
            return {"pass": "background-color:#d4edda", "fail": "background-color:#f8d7da",
                    "na": "background-color:#e2e3e5"}.get(val, "background-color:#fff3cd")
        df = pd.DataFrame([{
            "ID": v.get("constraint_id",""),
            "判定": v.get("verdict",""),
            "证据": (v.get("evidence") or v.get("reason") or "")[:60],
        } for v in verdicts])
        st.dataframe(df.style.map(color_v, subset=["判定"]),
                     use_container_width=True, hide_index=True, height=500)
    else:
        st.caption("无判定明细")

# 该通优化建议
suggestions = r.get("detailed_suggestions", [])
if suggestions:
    st.markdown("---")
    st.markdown("##### 💡 本通优化建议")
    for s in suggestions:
        with st.expander(f"[{s.get('priority','')}] {s.get('constraint_id','')} - {(s.get('problem') or '')[:50]}"):
            if s.get("how_to_fix"):
                st.markdown(f"**改进**: {s['how_to_fix']}")
            if s.get("example"):
                st.info(s["example"])

st.markdown("---")
st.page_link("app.py", label="← 回到评测主页")
