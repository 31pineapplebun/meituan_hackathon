import json
from config.labels import DIM_SHORT, PERSONAS


def grade_color(score):
    if score >= 85:
        return "#16a34a", "#22c55e", "优秀"
    if score >= 70:
        return "#f59e0b", "#fbbf24", "良好"
    if score >= 50:
        return "#ea580c", "#fb923c", "需改进"
    return "#dc2626", "#f87171", "不合格"


def render_model_report(st, report):
    if report.get("error"):
        st.error(report["error"])
        return

    summary = report["summary"]
    score = summary["avg_score"]
    c1, c2, grade = grade_color(score)

    st.markdown(
        f"""
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
    """,
        unsafe_allow_html=True,
    )

    st.info(f"💡 **诊断**: {summary['diagnosis']}")
    st.markdown("---")

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
            fig.add_trace(
                go.Scatterpolar(
                    r=vals + [vals[0]],
                    theta=labels + [labels[0]],
                    fill="toself",
                    line_color="rgb(102,126,234)",
                    fillcolor="rgba(102,126,234,0.3)",
                )
            )
            fig.update_layout(
                polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                showlegend=False,
                height=340,
                margin=dict(l=60, r=60, t=30, b=30),
            )
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
            st.markdown(
                f"""
            <div style="margin: 6px 0;">
                <div style="display: flex; justify-content: space-between; font-size: 14px;">
                    <span>{pname}</span><span style="font-weight: 700; color: {bar_color};">{pscore}</span>
                </div>
                <div style="background: #e2e8f0; border-radius: 6px; height: 10px; overflow: hidden;">
                    <div style="background: {bar_color}; width: {pct}%; height: 100%;"></div>
                </div>
            </div>
            """,
                unsafe_allow_html=True,
            )

    st.markdown("---")
    weak = report.get("weak_constraints", [])
    if weak:
        st.markdown("##### 🔴 最常违反的约束 (跨场景聚合)")
        import pandas as pd

        df = pd.DataFrame(
            [
                {
                    "约束 ID": w["constraint_id"],
                    "约束名": w["constraint_name"],
                    "失败率": f"{w['fail_rate']:.0f}%",
                    "失败/总数": f"{w['fail_count']}/{w['total_count']}",
                }
                for w in weak
            ]
        )
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            "📥 下载模型评测报告 (JSON)",
            json.dumps(report, ensure_ascii=False, indent=2),
            file_name=f"model_report_{report['instruction_name']}_{report['model_name']}.json",
            mime="application/json",
            use_container_width=True,
        )
    with col2:
        st.page_link("pages/1_dialogue_detail.py", label="📂 查看某一通对话的细节 →", use_container_width=True)

