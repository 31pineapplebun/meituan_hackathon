"""
Tab 4: 报告 - 漂亮的评分可视化报告 (B4 升级版)

升级点:
- 接入 detailed_suggestions (来自 suggestion_generator)
- 直接嵌入 HTML 报告 (来自 html_report)
- 三种导出格式: JSON / Markdown / HTML
"""
import streamlit as st
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "09_pipeline"))

st.set_page_config(page_title="报告", page_icon="📊", layout="wide")

st.title("📊 评分报告")
st.markdown("---")

if "last_pipeline_output" not in st.session_state and "last_score_report" not in st.session_state:
    st.warning("⚠️ 请先在 **🧪 评测** 页跑一次评测, 或点下面加载示例")
    
    if st.button("📂 加载 V4 示例报告 (违规对话)", type="primary"):
        sample_path = PROJECT_ROOT / "09_pipeline" / "example_reports" / "v4_violation_dialogue.json"
        if sample_path.exists():
            with open(sample_path, encoding="utf-8") as f:
                data = json.load(f)
            st.session_state["last_pipeline_output"] = data
            st.session_state["last_score_report"] = data.get("score_report", {})
            st.rerun()
    st.stop()

pipeline_output = st.session_state.get("last_pipeline_output", {})
score_report = pipeline_output.get("score_report") or st.session_state.get("last_score_report", {})
verdict_details = pipeline_output.get("verdict_details", [])
detailed_suggestions = pipeline_output.get("detailed_suggestions", [])

if not score_report:
    st.error("数据缺失")
    st.stop()

# 大字评分
final_score = score_report.get("final_score", 0)
if final_score >= 90:
    color1, color2 = "#4ade80", "#16a34a"
    grade = "优秀"
elif final_score >= 70:
    color1, color2 = "#fbbf24", "#d97706"
    grade = "良好"
elif final_score >= 50:
    color1, color2 = "#fb923c", "#ea580c"
    grade = "需改进"
else:
    color1, color2 = "#f87171", "#dc2626"
    grade = "不合格"

st.markdown(f"""
<div style="background: linear-gradient(135deg, {color1} 0%, {color2} 100%); 
            padding: 40px; border-radius: 20px; text-align: center; color: white;
            box-shadow: 0 8px 32px rgba(0,0,0,0.2);">
    <h1 style="font-size: 80px; margin: 0;">{final_score}/100</h1>
    <h2 style="margin: 10px 0; font-weight: normal;">{grade}</h2>
    <p style="margin: 0; font-size: 16px; opacity: 0.9;">
        原始分: {score_report.get('raw_score', 0):.1f} | 
        上限: {score_report.get('ceiling', '-')} | 
        Critical 通过率: {score_report.get('critical_pass_rate', 0)*100:.0f}%
    </p>
</div>
""", unsafe_allow_html=True)

st.markdown("---")

# 雷达图
st.subheader("📐 5 维度评分")
col1, col2 = st.columns([2, 1])
dim_scores = score_report.get("dim_scores", {})

try:
    import plotly.graph_objects as go
    categories = ["D1<br>流程遵循", "D2<br>任务完成", "D3<br>约束遵循", "D4<br>知识准确", "D5<br>对话质量"]
    keys = ["D1_flow_compliance", "D2_task_completion", "D3_constraint_compliance",
            "D4_knowledge_accuracy", "D5_dialogue_quality"]
    values = [dim_scores.get(k) or 0 for k in keys]
    fig = go.Figure()
    fig.add_trace(go.Scatterpolar(
        r=values + [values[0]],
        theta=categories + [categories[0]],
        fill='toself',
        line_color='rgb(102,126,234)',
        fillcolor='rgba(102,126,234,0.3)'
    ))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                       showlegend=False, height=400, margin=dict(l=80, r=80, t=20, b=20))
    col1.plotly_chart(fig, use_container_width=True)
except ImportError:
    col1.warning("plotly 未安装")

with col2:
    st.markdown("**维度分明细**")
    short_names = {
        "D1_flow_compliance": "D1 流程",
        "D2_task_completion": "D2 任务",
        "D3_constraint_compliance": "D3 约束",
        "D4_knowledge_accuracy": "D4 知识",
        "D5_dialogue_quality": "D5 对话"
    }
    for k, name in short_names.items():
        v = dim_scores.get(k)
        if v is None:
            st.markdown(f"- **{name}**: 无")
        else:
            emoji = "🟢" if v >= 80 else "🟡" if v >= 60 else "🔴"
            st.markdown(f"- {emoji} **{name}**: {v:.1f}")

st.markdown("---")

# 优化建议 (B4 核心)
if detailed_suggestions:
    st.subheader(f"💡 优化建议 ({len(detailed_suggestions)} 条)")
    for i, s in enumerate(detailed_suggestions, 1):
        priority = s.get("priority", "P3_LOW")
        p_short = priority.replace("P0_", "").replace("P1_", "").replace("P2_", "").replace("P3_", "")
        with st.expander(
            f"#{i} [{p_short}] {s.get('constraint_id', '')} - {(s.get('problem') or '')[:50]}",
            expanded=(priority.startswith("P0") or priority == "P1_HIGH")
        ):
            col_a, col_b, col_c = st.columns([2, 1, 1])
            col_a.markdown(f"**约束**: {(s.get('constraint_name') or '')[:60]}")
            col_b.markdown(f"**类别**: {s.get('category', '-')}")
            col_c.markdown(f"**严重度**: {s.get('severity', '-')}")
            if s.get("evidence"):
                st.markdown("**📌 具体证据**")
                st.code(s["evidence"][:200])
            if s.get("how_to_fix"):
                st.markdown("**🔧 改进方法**")
                st.markdown(s["how_to_fix"])
            if s.get("example"):
                st.markdown("**💚 改写示例**")
                st.info(s["example"])
            if s.get("expected_impact"):
                st.success(f"📈 **{s['expected_impact']}**")
    st.markdown("---")
elif verdict_details:
    fails = [v for v in verdict_details if v.get("verdict") == "fail"]
    if fails:
        st.subheader(f"🔴 检测到 {len(fails)} 处违规")
        for f in fails:
            with st.expander(f"❌ {f.get('constraint_id')}: {(f.get('constraint_name') or '')[:60]}"):
                st.markdown(f"**Evidence**: {f.get('evidence', '-')}")
                st.markdown(f"**Reason**: {f.get('reason', '-')}")
    else:
        st.success("🎉 没有违规!")

# 详细判定表
if verdict_details:
    st.subheader("📋 详细判定")
    from collections import Counter
    verdict_dist = Counter(v.get("verdict") for v in verdict_details)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("总约束", len(verdict_details))
    c2.metric("Pass", verdict_dist.get("pass", 0))
    c3.metric("Fail", verdict_dist.get("fail", 0))
    c4.metric("N/A", verdict_dist.get("na", 0))
    c5.metric("Not Impl", verdict_dist.get("not_implemented", 0))
    
    filter_v = st.multiselect("筛选 Verdict", ["pass", "fail", "na", "not_implemented"],
                                default=["fail", "pass"])
    filtered = [v for v in verdict_details if v.get("verdict") in filter_v]
    
    import pandas as pd
    df = pd.DataFrame([
        {
            "ID": v.get("constraint_id", ""),
            "类型": (v.get("verifier_type") or "")[:14],
            "Verdict": v.get("verdict", ""),
            "名称": (v.get("constraint_name") or "")[:50],
            "Evidence": (v.get("evidence") or "")[:80],
        }
        for v in filtered
    ])
    
    def color_verdict(val):
        if val == "pass": return "background-color: #d4edda; color: #155724"
        if val == "fail": return "background-color: #f8d7da; color: #721c24"
        if val == "na": return "background-color: #e2e3e5; color: #383d41"
        return "background-color: #fff3cd; color: #856404"
    
    st.dataframe(df.style.applymap(color_verdict, subset=["Verdict"]),
                 use_container_width=True, hide_index=True, height=400)

# 下载
st.markdown("---")
st.subheader("⬇️ 下载报告")
col1, col2, col3 = st.columns(3)
with col1:
    json_data = pipeline_output if pipeline_output else {"score_report": score_report, "verdict_details": verdict_details}
    st.download_button(
        "📄 下载 JSON",
        json.dumps(json_data, ensure_ascii=False, indent=2),
        file_name="score_report.json",
        mime="application/json",
        use_container_width=True
    )
with col2:
    # 用 pipeline 的完整 markdown 生成器,不要简化
    try:
        from pipeline import render_markdown_report
        # 拼 instruction (Tab4 可能没有完整指令对象)
        instr_obj = {"atomic_constraints": [], "meta": {}}
        if pipeline_output:
            # 从 pipeline_output 反推一个能用的 instruction
            instr_obj["meta"] = {"instruction_id": pipeline_output.get("instruction_id", "?")}
        # dialogue 也可能没有,给个 stub
        dlg_obj = {"dialogue_id": pipeline_output.get("dialogue_id", "?"), "turns": []}
        md_content = render_markdown_report(pipeline_output, instr_obj, dlg_obj)
    except Exception as e:
        # 兜底: 用简版 (不应该走到这里)
        md_content = f"""# 评分报告

## 最终评分: {final_score}/100 ({grade})

- 原始分: {score_report.get('raw_score', 0):.1f}
- 上限: {score_report.get('ceiling', '-')}
- Critical 通过率: {score_report.get('critical_pass_rate', 0)*100:.0f}%

## 5 维度分

{chr(10).join(f"- {k}: {v if v is not None else 'N/A'}" for k, v in dim_scores.items())}

## 详细判定

{chr(10).join(f"- {v.get('constraint_id', '?')}: {v.get('verdict', '?')} - {(v.get('evidence') or v.get('reason') or '')[:80]}" for v in verdict_details)}

_(完整 markdown 生成失败: {e}, 已退化到简版)_
"""
    
    st.download_button("📝 下载 Markdown", md_content, file_name="score_report.md",
                       mime="text/markdown", use_container_width=True)
with col3:
    try:
        from html_report import generate_html_report
        html_content = generate_html_report(pipeline_output)
        st.download_button("🎨 下载 HTML", html_content, file_name="score_report.html",
                            mime="text/html", use_container_width=True)
    except Exception as e:
        st.button("🎨 HTML (不可用)", disabled=True, use_container_width=True, help=str(e))
