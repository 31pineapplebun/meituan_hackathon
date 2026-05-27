"""
Tab 3: 评测 - 自动判定每条约束的 Pass/Fail
"""
import streamlit as st
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

st.set_page_config(page_title="评测", page_icon="🧪", layout="wide")


# ============================================================
# 函数定义 (必须先定义后调用)
# ============================================================

def run_evaluation(dialogue, instr_key, use_mock):
    """跑评测 - 调用 pipeline"""
    import os
    os.environ["VERIFIER_LLM_MOCK"] = "1" if use_mock else "0"
    
    # 加载指令
    instr_path = PROJECT_ROOT / "08_parser" / "parsed_examples" / f"{instr_key.lower()}_parsed.json"
    if not instr_path.exists():
        st.error(f"指令未找到: {instr_path}")
        return
    
    with open(instr_path, encoding="utf-8") as f:
        instruction = json.load(f)
    
    constraints = instruction.get("atomic_constraints", [])
    
    # 调用 pipeline
    sys.path.insert(0, str(PROJECT_ROOT / "09_pipeline"))
    
    try:
        from verifier_base import dispatch
        import verifiers
        import verifier_state_tracker
        import verifier_llm_extract
        import verifier_llm_judge
        from pipeline import compute_p3_score
    except ImportError as e:
        st.error(f"Pipeline 模块加载失败: {e}")
        return
    
    # 进度条
    progress = st.progress(0)
    status = st.empty()
    results = []
    
    for i, c in enumerate(constraints):
        status.text(f"评测 {c['id']}: {c['name'][:40]}...")
        progress.progress((i+1) / len(constraints))
        try:
            v = dispatch(c, dialogue, instruction)
            results.append(v)
        except Exception as e:
            st.warning(f"约束 {c['id']} 评测失败: {e}")
    
    status.empty()
    progress.empty()
    
    # 算分
    score_report = compute_p3_score(results, constraints)
    
    # B2/B3 集成: 生成详细建议 + 完整 pipeline output
    try:
        from suggestion_generator import generate_suggestions, suggestions_to_dict
        detailed = generate_suggestions(results, constraints, dialogue, score_report)
        detailed_dict = suggestions_to_dict(detailed)
    except Exception as e:
        st.warning(f"详细建议生成失败 (不影响评分): {e}")
        detailed_dict = []
    
    pipeline_output = {
        "dialogue_id": dialogue.get("dialogue_id"),
        "instruction_id": instr_key,
        "score_report": score_report,
        "detailed_suggestions": detailed_dict,
        "verdict_details": [
            {
                "constraint_id": r.constraint_id,
                "constraint_name": r.constraint_name,
                "verifier_type": r.verifier_type,
                "verdict": r.verdict,
                "evidence": r.evidence,
                "reason": r.reason,
                "confidence": r.confidence,
            }
            for r in results
        ],
        "stats": {
            "total_constraints": len(constraints),
            "pass": sum(1 for r in results if r.verdict == "pass"),
            "fail": sum(1 for r in results if r.verdict == "fail"),
            "na": sum(1 for r in results if r.verdict == "na"),
            "not_implemented": sum(1 for r in results if r.verdict == "not_implemented"),
        }
    }
    
    # 保存到 session
    st.session_state["last_pipeline_output"] = pipeline_output
    st.session_state["last_score_report"] = score_report
    st.session_state["last_results"] = results
    st.session_state["last_constraints"] = constraints
    
    # 即时展示
    st.success(f"✅ 评测完成! 评分 = **{score_report['final_score']}/100**")
    st.balloons()
    
    # 概览
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("最终评分", f"{score_report['final_score']}/100")
    col2.metric("原始分", f"{score_report['raw_score']:.1f}")
    col3.metric("上限钳制", score_report.get("ceiling", "-"))
    col4.metric("Critical 通过率", f"{score_report['critical_pass_rate']*100:.0f}%")
    
    # 维度分
    st.subheader("📊 5 维度分")
    dim_scores = score_report.get("dim_scores", {})
    dim_cols = st.columns(5)
    for i, (k, v) in enumerate(dim_scores.items()):
        if v is None:
            dim_cols[i].metric(k[:6], "N/A")
        else:
            dim_cols[i].metric(k[:6], f"{v:.1f}")
    
    # 详细 verdict
    st.subheader("📋 详细 Verdict")
    import pandas as pd
    df = pd.DataFrame([
        {
            "ID": v.constraint_id,
            "Verifier": v.verifier_type,
            "Verdict": v.verdict,
            "Evidence": (v.evidence or "")[:80],
            "Reason": (v.reason or "")[:80],
        }
        for v in results
    ])
    
    # 配色: pass 绿, fail 红, na 灰
    def color_verdict(val):
        if val == "pass":
            return "background-color: #d4edda"
        elif val == "fail":
            return "background-color: #f8d7da"
        elif val == "na":
            return "background-color: #e2e3e5"
        return ""
    
    st.dataframe(df.style.applymap(color_verdict, subset=["Verdict"]), 
                 use_container_width=True, hide_index=True, height=400)
    
    st.info("👉 切到 **📊 报告** 页查看更详细的可视化")


# ============================================================
# 页面 UI (函数定义之后)
# ============================================================

st.title("🧪 评测 - 自动判定")
st.markdown("---")

st.markdown("""
**功能**: 上传/选择一通对话, 调用 Pipeline 5 个 Verifier 自动评测.
- ⚡ 15-30 秒/通
- 💰 ¥0.20/通
- 📊 5 维度评分 + 100 分制
""")

# 三栏选择
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("1️⃣ 选指令")
    instruction = st.selectbox(
        "任务指令",
        [
            "🏢 official_1_feimaotui - 飞毛腿合同",
            "🏢 official_2_kecheng - 课程发布升级",
            "V1 - 培训通知", "V2 - APP更新", "V3 - 天气提醒",
            "V4 - 出餐核实", "V5 - 差评回访", "V6 - 复杂多步"
        ]
    )
    # 官方 sample 用文件名,V*用首字段
    if "official_" in instruction:
        # 提取 "official_X_xxx"
        for part in instruction.split():
            if part.startswith("official_"):
                instr_key = part
                break
        else:
            instr_key = "V1"  # fallback
    else:
        instr_key = instruction.split(" ")[0]

with col2:
    st.subheader("2️⃣ 选对话")
    
    # 数据源: 模拟器/Gold Set/官方Demo/上传
    source_options = ["📁 从 Gold Set 选", "📤 上传 .jsonl"]
    
    # 如果选的是官方 sample, 加上"官方 Demo 对话"选项
    if "official_" in instr_key:
        source_options = ["🏢 用官方 Demo 对话"] + source_options
    
    # 如果模拟器跑过对话, 加上选项
    if "simulator_last_dialogue" in st.session_state:
        source_options = ["💬 用模拟器刚生成的"] + source_options
    
    source = st.radio("对话来源", source_options, horizontal=True)
    
    selected_dialogue = None
    if source == "💬 用模拟器刚生成的":
        selected_dialogue = st.session_state["simulator_last_dialogue"]
        st.success(f"✓ 使用对话 {selected_dialogue.get('dialogue_id', '?')[:35]}...")
        sim_instr = selected_dialogue.get("instruction_name")
        if sim_instr and sim_instr != instr_key:
            st.warning(f"⚠️ 模拟器对话用的是 **{sim_instr}** 指令, 但你选了 **{instr_key}**. 建议把指令也改成 {sim_instr}")
    
    elif source == "🏢 用官方 Demo 对话":
        # 加载官方 demo 对话
        demo_dir = PROJECT_ROOT / "09_pipeline" / "official_demo"
        demo_files = list(demo_dir.glob(f"{instr_key}*.jsonl")) if demo_dir.exists() else []
        
        if demo_files:
            demo_labels = {}
            for f in demo_files:
                # 解析文件名识别违规/完美/合作 等
                name = f.stem
                if "violation" in name:
                    label = f"❌ {name} (含违规, 适合演示扣分)"
                elif "cooperative" in name:
                    label = f"✅ {name} (合作对话, 适合演示流程)"
                else:
                    label = name
                demo_labels[label] = f
            
            selected_label = st.selectbox("Demo 对话", list(demo_labels.keys()))
            demo_path = demo_labels[selected_label]
            with open(demo_path, encoding="utf-8") as f:
                line = f.readline().strip()
                if line:
                    selected_dialogue = json.loads(line)
        else:
            st.warning(f"没找到 {instr_key} 的 Demo 对话")
    
    elif source == "📁 从 Gold Set 选":
        gold_path = PROJECT_ROOT / "06_gold_annotation" / "gold_set" / "gold_set_50.jsonl"
        if gold_path.exists():
            dialogues = []
            with open(gold_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        d = json.loads(line)
                        if d["instruction_name"] == instr_key:
                            dialogues.append(d)
            
            if dialogues:
                dlg_options = [
                    f"{d['dialogue_id'][:40]}... ({d['persona_id']})"
                    for d in dialogues
                ]
                selected_idx = st.selectbox(
                    "对话", range(len(dlg_options)),
                    format_func=lambda i: dlg_options[i]
                )
                selected_dialogue = dialogues[selected_idx]
            else:
                st.warning(f"Gold Set 里没有 {instr_key} 的对话 (V3/V6 没采样过 Gold Set, 请先去模拟器跑一通)")
        else:
            st.error(f"Gold Set 文件不存在: {gold_path}")
    else:
        uploaded = st.file_uploader("上传对话 .jsonl", type=["jsonl", "json"])
        if uploaded:
            try:
                content = uploaded.read().decode("utf-8").strip()
                # 兼容 jsonl (每行一个JSON) 和 单JSON
                if "\n" in content:
                    selected_dialogue = json.loads(content.split("\n")[0])
                else:
                    selected_dialogue = json.loads(content)
            except Exception as e:
                st.error(f"解析失败: {e}")

with col3:
    st.subheader("3️⃣ Verifier 模式")
    mode = st.radio(
        "评测模式",
        ["🤖 LLM (deepseek-flash, 准确)", "⚡ Mock (启发式, 秒出)"],
        index=0
    )
    use_mock = "Mock" in mode

# 展示对话预览
if selected_dialogue:
    st.markdown("---")
    st.subheader("👀 对话预览")
    
    with st.expander(f"对话 ID: {selected_dialogue['dialogue_id']}", expanded=True):
        col_l, col_r = st.columns(2)
        col_l.write(f"**Persona**: {selected_dialogue.get('persona_id', '-')}")
        col_r.write(f"**轮数**: {len(selected_dialogue['turns'])}")
        
        for t in selected_dialogue["turns"][:10]:
            role = t.get("role", "?")
            content = t.get("content", "")
            turn = t.get("turn", "?")
            
            if role == "assistant":
                st.markdown(f"🤖 **T{turn} ({len(content)}字)**: {content}")
            else:
                st.markdown(f"👤 **T{turn} ({len(content)}字)**: {content}")
        
        if len(selected_dialogue["turns"]) > 10:
            st.caption(f"...还有 {len(selected_dialogue['turns']) - 10} 轮未显示")

# 评测按钮 (在函数定义之后,可以正常调用)
if selected_dialogue:
    st.markdown("---")
    if st.button("🚀 开始评测", type="primary", use_container_width=True):
        run_evaluation(selected_dialogue, instr_key, use_mock)
