"""
Tab 1: 上传指令 - 解析任务约束
"""
import streamlit as st
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "08_parser"))

st.set_page_config(page_title="上传指令", page_icon="📋", layout="wide")


# ============================================================
# 函数定义 (必须先定义后调用)
# ============================================================

def show_parsed_result(result):
    """展示解析结果"""
    constraints = result.get("atomic_constraints", [])
    critical = sum(1 for c in constraints if c.get("is_critical"))
    
    col1, col2, col3 = st.columns(3)
    col1.metric("总约束数", len(constraints))
    col2.metric("Critical 约束", critical, f"占 {critical*100/max(1,len(constraints)):.0f}%")
    col3.metric("FAQ 条数", len(result.get("faq_items", [])))
    
    # 约束表
    st.subheader("📑 约束清单")
    
    # 约束清单 - 美化版
    import pandas as pd
    
    # 简化 verifier 名 + 维度 emoji
    verifier_short = {
        "rule": "📏 规则",
        "rule_pattern": "🔤 模式匹配",
        "state_tracker": "🔄 流程追踪",
        "llm_extract_then_rule": "🤖 LLM抽取",
        "llm_judge": "⚖️ LLM判定",
    }
    dim_short = {
        "D1_flow_compliance": "D1 流程",
        "D2_task_completion": "D2 任务",
        "D3_constraint_compliance": "D3 约束",
        "D4_knowledge_accuracy": "D4 知识",
        "D5_dialogue_quality": "D5 对话",
    }
    
    df = pd.DataFrame([
        {
            "ID": c["id"],
            "关键": "🔴" if c.get("is_critical") else "",
            "Verifier 类型": verifier_short.get(c["verifier"], c["verifier"]),
            "维度": dim_short.get(c.get("scoring_dimension", ""), c.get("scoring_dimension", "?")),
            "权重": c.get("weight", 1),
            "约束名": c["name"][:80]
        }
        for c in constraints
    ])
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "ID": st.column_config.TextColumn("ID", width="small"),
            "关键": st.column_config.TextColumn("关键", width="small"),
            "Verifier 类型": st.column_config.TextColumn("Verifier 类型", width="medium"),
            "维度": st.column_config.TextColumn("维度", width="small"),
            "权重": st.column_config.NumberColumn("权重", width="small"),
            "约束名": st.column_config.TextColumn("约束名", width="large"),
        }
    )
    
    # 饼图 + 柱状图 (用 plotly, 更美观)
    st.markdown("---")
    col1, col2 = st.columns(2)
    
    try:
        import plotly.express as px
        from collections import Counter
        
        with col1:
            st.subheader("📊 按 Verifier 类型")
            verifier_dist = Counter(verifier_short.get(c["verifier"], c["verifier"]) for c in constraints)
            df_v = pd.DataFrame({"类型": list(verifier_dist.keys()), "数量": list(verifier_dist.values())})
            fig = px.pie(df_v, names="类型", values="数量", hole=0.4,
                         color_discrete_sequence=px.colors.qualitative.Set2)
            fig.update_traces(textposition='outside', textinfo='label+value')
            fig.update_layout(height=320, margin=dict(l=20, r=20, t=20, b=20),
                              showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("📊 按维度")
            dim_dist = Counter(dim_short.get(c.get("scoring_dimension", ""), "?") for c in constraints)
            df_d = pd.DataFrame({"维度": list(dim_dist.keys()), "数量": list(dim_dist.values())})
            df_d = df_d.sort_values("维度")
            fig = px.bar(df_d, x="维度", y="数量", color="维度",
                         color_discrete_sequence=px.colors.qualitative.Pastel,
                         text="数量")
            fig.update_traces(textposition='outside')
            fig.update_layout(height=320, margin=dict(l=20, r=20, t=20, b=20),
                              showlegend=False, xaxis_title="", yaxis_title="")
            st.plotly_chart(fig, use_container_width=True)
    except ImportError:
        # plotly 不可用时回退
        from collections import Counter
        with col1:
            st.subheader("📊 按 Verifier 类型")
            st.bar_chart(Counter(verifier_short.get(c["verifier"], c["verifier"]) for c in constraints))
        with col2:
            st.subheader("📊 按维度")
            st.bar_chart(Counter(dim_short.get(c.get("scoring_dimension", ""), "?") for c in constraints))
    
    # JSON 下载
    st.markdown("---")
    st.subheader("⬇️ 下载解析结果")
    st.download_button(
        "下载 JSON",
        json.dumps(result, ensure_ascii=False, indent=2),
        file_name=f"{result.get('instruction_name', 'parsed')}.json",
        mime="application/json"
    )


def show_mock_result(name):
    """没有真实 parser 时显示样本"""
    sample_path = PROJECT_ROOT / "08_parser" / "parsed_examples" / f"{name.lower()}_parsed.json"
    if sample_path.exists():
        with open(sample_path, encoding="utf-8") as f:
            result = json.load(f)
        show_parsed_result(result)
    else:
        st.info(f"示例指令 V1/V2/V4/V5 已预解析, 选 V1-V5 任一查看 (找不到: {sample_path})")


# ============================================================
# 页面 UI
# ============================================================

st.title("📋 上传指令 - 解析任务约束")
st.markdown("---")

st.markdown("""
**功能**: 上传你的外呼任务指令 (Markdown 格式),系统自动:
- 解析约束清单 (16-26 条)
- 识别 5 类约束类型
- 标记 Critical 关键约束
- 生成可被 Pipeline 评测的 JSON
""")

# 数据源选择
data_source = st.radio(
    "数据源",
    ["📄 选择示例指令", "📤 上传你自己的 .md 文件", "✏️ 粘贴 markdown"],
    horizontal=True
)

instruction_text = ""
instruction_name = "Custom"

if data_source == "📄 选择示例指令":
    examples = {
        "🏢 官方 Sample 1 - 飞毛腿合同 (脱敏)": PROJECT_ROOT / "03_examples" / "official" / "official_1_feimaotui.md",
        "🏢 官方 Sample 2 - 课程发布升级 (脱敏)": PROJECT_ROOT / "03_examples" / "official" / "official_2_kecheng.md",
        "V1 - 骑手安全培训通知": PROJECT_ROOT / "03_examples" / "variants" / "V1.md",
        "V2 - APP 强制更新通知": PROJECT_ROOT / "03_examples" / "variants" / "V2.md",
        "V3 - 恶劣天气提醒": PROJECT_ROOT / "03_examples" / "variants" / "V3.md",
        "V4 - 商家出餐慢核实": PROJECT_ROOT / "03_examples" / "variants" / "V4.md",
        "V5 - 商家差评回访": PROJECT_ROOT / "03_examples" / "variants" / "V5.md",
        "V6 - 复杂多步流程": PROJECT_ROOT / "03_examples" / "variants" / "V6.md",
    }
    selected = st.selectbox("选择指令", list(examples.keys()))
    selected_path = examples[selected]
    # 用文件名 stem 作 instruction_name (兼容带 emoji 的 label)
    instruction_name = selected_path.stem  # 如 "V1" / "official_1_feimaotui"
    if selected_path.exists():
        instruction_text = selected_path.read_text(encoding="utf-8")
        with st.expander("📄 查看原文"):
            st.markdown(instruction_text)
    else:
        st.warning(f"示例文件不存在: {selected_path}")

elif data_source == "📤 上传你自己的 .md 文件":
    uploaded = st.file_uploader("上传指令文件", type=["md", "txt"])
    if uploaded:
        instruction_text = uploaded.read().decode("utf-8")
        instruction_name = Path(uploaded.name).stem
        with st.expander("📄 查看原文"):
            st.markdown(instruction_text)

else:  # 粘贴
    instruction_text = st.text_area("粘贴 markdown 指令", height=300)
    instruction_name = st.text_input("指令名称", value="Custom")

# 解析按钮
if instruction_text:
    st.markdown("---")
    if st.button("🔍 开始解析", type="primary", use_container_width=True):
        with st.spinner("解析中..."):
            try:
                # 优先用预解析的 JSON (V1-V6 + 官方 sample 都已经预解析过)
                preparsed = ["V1", "V2", "V3", "V4", "V5", "V6",
                             "official_1_feimaotui", "official_2_kecheng"]
                if instruction_name in preparsed:
                    show_mock_result(instruction_name)
                else:
                    # 自定义指令: 尝试调用 parser
                    try:
                        from parser import parse_instruction
                        result = parse_instruction(instruction_text, instruction_name)
                        st.success("✅ 解析成功!")
                        show_parsed_result(result)
                    except ImportError:
                        st.warning("⚠️ Parser 模块未找到, 展示示例数据")
                        show_mock_result("V1")  # fallback
            except Exception as e:
                st.error(f"❌ 解析失败: {e}")
                st.exception(e)
