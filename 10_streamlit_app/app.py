"""
美团对话外呼任务评测系统 - 一站式主入口

跑法: streamlit run app.py

设计: 一条路走到底 —— 选指令 → 选待测模型+场景 → 一键评测 → 模型能力画像
官方要求: "给指令 + 给待测模型 → 出报告", 评的是【模型】不是【单通对话】
"""
import streamlit as st
import json
import sys
import time
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "08_parser"))
sys.path.insert(0, str(PROJECT_ROOT / "09_pipeline"))
sys.path.insert(0, str(PROJECT_ROOT / "07_simulator"))

st.set_page_config(
    page_title="美团对话外呼评测系统",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
    .main { padding-top: 1rem; }
    div[data-testid="stMetricValue"] { font-size: 28px; }
    .step-box {
        background: #f8fafc; border-left: 4px solid #667eea;
        padding: 8px 16px; border-radius: 8px; margin: 8px 0;
    }
</style>
""", unsafe_allow_html=True)


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
# 主流程
# ============================================================
st.title("🎯 评测模型 — 一站式指令遵循能力评估")
st.caption("输入任务指令 + 选择待测模型 → 自动模拟多场景对话并评测 → 产出模型能力画像")
st.markdown("---")

# ---- 第 1 步: 选指令 (预置 / 自定义 二选一, 对齐赛题"用户输入任务指令") ----
st.markdown("### 1️⃣ 选择任务指令")
input_mode = st.radio(
    "指令来源",
    ["📚 从预置指令选择", "✍️ 自己输入 / 📤 上传指令"],
    horizontal=True, label_visibility="collapsed",
)

parsed = None
instr_name = None
has_demo = False

if input_mode.startswith("📚"):
    # 方式 A: 预置指令 (官方 sample / V1-V6)
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
    # 方式 B: 用户自己输入 / 上传指令 → 调后端 parser 现场解析 (只暴露入口, 不改后端)
    up = st.file_uploader("📤 上传指令 Markdown 文件 (.md / .txt)", type=["md", "txt"])
    pasted = st.text_area(
        "✍️ 或直接粘贴任务指令 (Markdown)", height=240,
        placeholder="粘贴你的外呼任务指令...\n支持 # Role / # Task / # Constraints / # Knowledge Points (FAQ) / # Call Flow 等 Markdown 结构",
    )
    # 文件优先。两个 Streamlit 重跑语义下的坑必须规避:
    #  1) 用 getvalue() 而非 read(): read() 依赖缓冲区读指针, 多次 rerun 可能读到空串;
    #  2) 不把文件内容塞进 text_area 的 value=: text_area 首次渲染后会忽略变化的 value,
    #     会导致上传的文件内容进不了输入框/被旧 widget 状态覆盖。故让文件内容直接作 md_text。
    if up is not None:
        md_text = up.getvalue().decode("utf-8", errors="replace")   # 容错非 UTF-8, 不崩
        st.caption(f"📎 已读取上传文件「{up.name}」({len(md_text)} 字符 / {md_text.count(chr(10)) + 1} 行)"
                   " · 如需改用粘贴文本请先移除该文件")
    else:
        md_text = pasted

    if md_text.strip():
        instr_name = "custom_instruction"
        has_demo = False   # 自定义指令无预置数据, 只走完整模式真跑
        try:
            parse_instruction = _load_parse_instruction()
            with st.spinner("正在解析指令、拆解约束清单…"):
                parsed_obj = parse_instruction(
                    md_text, instruction_id="CUSTOM",
                    instruction_name="自定义指令", mock=True,   # 启发式分类: 即时、离线、无需额外 key
                )
                parsed = parsed_obj.to_dict()
            if not parsed.get("atomic_constraints"):
                st.warning("⚠️ 没能从这段文本解析出任何约束，请确认是结构化的外呼指令"
                           "(建议含 # Constraints / # Call Flow 等 Markdown 段落)。")
                parsed = None
            else:
                # 落临时文件: 完整模式 run_full_evaluation 按路径读取
                tmp = Path(tempfile.gettempdir())
                p_path = tmp / "custom_instruction_parsed.json"
                m_path = tmp / "custom_instruction.md"
                p_path.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
                m_path.write_text(md_text, encoding="utf-8")
                st.session_state["me_instruction_parsed_path"] = str(p_path)
                st.session_state["me_instruction_md_path"] = str(m_path)
                st.session_state["me_instruction_name"] = instr_name
        except Exception as e:
            st.error(f"❌ 指令解析失败: {e}")
            parsed = None
    else:
        st.info("👆 粘贴指令文本或上传 .md 文件后, 系统会用解析器自动拆出约束清单")

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

# ---- 第 2 步: 选待测模型 + 场景 ----
st.markdown("### 2️⃣ 选择待测模型 + 测试场景")
col_a, col_b = st.columns([1, 2])
with col_a:
    st.markdown("**待测模型** (被评测的对象)")
    tested_model = st.selectbox("待测模型",
        ["deepseek-v4-flash", "deepseek-v4-pro", "gpt-4o-mini", "gpt-5-mini"],
        label_visibility="collapsed")
with col_b:
    st.markdown("**测试场景** (勾几个跑几通,模拟不同用户)")
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

st.markdown("---")

# ---- 第 3 步: 模式 + 运行 ----
st.markdown("### 3️⃣ 运行评测")
col_m, col_run = st.columns([2, 1])
with col_m:
    # has_demo 已在第 1 步按指令来源设定 (预置读配置 / 自定义恒为 False); 不再依赖 instr_cfg
    mode_options = ["🔬 完整运行 (真跑, 需 API key, 几分钟)"]
    if has_demo:
        mode_options = ["⚡ 快速演示 (预置真实结果, 秒出)"] + mode_options
    mode = st.radio("评测模式", mode_options, label_visibility="collapsed")
    is_fast = "快速演示" in mode

    if not has_demo and not is_fast:
        st.caption(f"ℹ️ {instr_name} 无预置演示数据,将真实调用 {tested_model} (本地需设 API key)")
    elif is_fast:
        st.caption("ℹ️ 快速演示读取 Day 9 用 deepseek-flash 真实跑出的评测结果 (非 mock)")

with col_run:
    st.markdown("<br>", unsafe_allow_html=True)
    run_clicked = st.button("🚀 开始评测模型", type="primary", use_container_width=True)

# 运行逻辑
if run_clicked:
    if not selected_personas:
        st.error("请至少勾选一个测试场景")
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
