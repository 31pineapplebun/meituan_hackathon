"""
Tab 2: 💬 用户模拟器 - 自动生成对话用于测试

调用 07_simulator/simulator_v2.py 的 run_one_dialogue
"""
import streamlit as st
import json
import sys
from pathlib import Path
import time

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "07_simulator"))

st.set_page_config(page_title="用户模拟器", page_icon="💬", layout="wide")


# ============================================================
# 函数定义
# ============================================================

def load_persona_info():
    """Persona 说明 - 8 个完整框架"""
    return {
        # 核心 4 个
        "cooperative": {
            "name": "🤝 合作型",
            "desc": "配合任务推进, 测 happy path 主流程",
            "max_turns": "8-15 轮",
        },
        "refuse_persistent": {
            "name": "😤 坚持拒绝型",
            "desc": "坚决拒绝, 测助手能否礼貌挂断",
            "max_turns": "4-10 轮",
        },
        "out_of_scope": {
            "name": "🌀 越界提问型",
            "desc": "问任务外问题, 测助手能否守住边界",
            "max_turns": "8-12 轮",
        },
        "interruption": {
            "name": "✋ 打断型",
            "desc": "中途打断话题, 测助手能否优雅恢复",
            "max_turns": "10-15 轮",
        },
        # 扩展 4 个
        "state_busy": {
            "name": "🚗 状态型(忙/开车)",
            "desc": "用户在忙/开车, 测助手识别状态 + 规定话术",
            "max_turns": "4-8 轮",
        },
        "ambiguous": {
            "name": "🤔 模糊型",
            "desc": "回答含糊不清, 测助手能否推动对话",
            "max_turns": "10-14 轮",
        },
        "adversarial": {
            "name": "⚔️ 对抗型",
            "desc": "用户挑刺/抱怨/试图诱使承诺, 测助手守边界",
            "max_turns": "10-14 轮",
        },
        "probing": {
            "name": "❓ 提问型",
            "desc": "用户狂问细节, 测助手 FAQ 知识覆盖度",
            "max_turns": "12-16 轮",
        },
    }


def run_simulator(instr_name, persona_id, tested_model, user_model, mock):
    """跑一通对话"""
    # 加载指令文本
    # 自动找指令文件 (可能在 variants/ 或 official/)
    instr_path = None
    for sub in ["variants", "official"]:
        p = PROJECT_ROOT / "03_examples" / sub / f"{instr_name}.md"
        if p.exists():
            instr_path = p
            break
    if instr_path is None:
        st.error(f"指令文件不存在: {instr_name}.md (找过 variants/ 和 official/)")
        return None
    
    instruction_text = instr_path.read_text(encoding="utf-8")
    
    # 加载变量并替换占位符
    var_path = PROJECT_ROOT / "03_examples" / "variants" / "variable_values.json"
    if var_path.exists():
        with open(var_path, encoding="utf-8") as f:
            all_vars = json.load(f)
        var_values = all_vars.get(instr_name, {}).get("default", {})
        for k, v in var_values.items():
            instruction_text = instruction_text.replace(f"${{{k}}}", str(v))
    
    # 调用模拟器
    try:
        import simulator_v2
    except ImportError as e:
        st.error(f"模拟器模块加载失败: {e}")
        return None
    
    # 生成对话 ID
    dialogue_id = f"{instr_name}_{persona_id}_{int(time.time())}_demo"
    
    with st.spinner(f"正在跑对话 ({persona_id} persona)..."):
        try:
            dialogue = simulator_v2.run_one_dialogue(
                instruction_text=instruction_text,
                instruction_name=instr_name,
                persona_id=persona_id,
                tested_model=tested_model,
                user_model=user_model,
                dialogue_id=dialogue_id,
                mock=mock,
            )
        except Exception as e:
            st.error(f"模拟失败: {e}")
            st.exception(e)
            return None
    
    return dialogue


def display_dialogue(dialogue):
    """展示对话内容"""
    if not dialogue:
        return
    
    # 转 dict (Dialogue 是 dataclass)
    if hasattr(dialogue, "__dict__"):
        d = dialogue.__dict__
    else:
        d = dialogue
    
    # 元信息
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("对话 ID", d.get("dialogue_id", "?")[:20] + "...")
    col2.metric("轮数", len(d.get("turns", [])))
    col3.metric("Persona", d.get("persona_id", "?"))
    col4.metric("被测模型", d.get("tested_model", "?")[:20])
    
    # 对话内容
    st.markdown("---")
    st.subheader("💬 对话内容")
    
    turns = d.get("turns", [])
    for t in turns:
        # 兼容 DialogueTurn 对象 / dict
        if hasattr(t, "__dict__"):
            t = t.__dict__
        role = t.get("role", "?")
        content = t.get("content", "")
        turn_num = t.get("turn", "?")
        
        if role == "assistant":
            st.markdown(
                f"🤖 **T{turn_num} 助手 ({len(content)}字)**: {content}"
            )
        else:
            st.markdown(
                f"👤 **T{turn_num} 用户 ({len(content)}字)**: {content}"
            )
    
    # 检查元信息
    metadata = d.get("metadata", {})
    if metadata.get("error"):
        st.error(f"对话出错: {metadata['error']}")
    if metadata.get("end_reason"):
        st.info(f"结束原因: {metadata['end_reason']}")


def dialogue_to_dict(dialogue):
    """把 Dialogue 对象转 dict 用于下载/传递"""
    if hasattr(dialogue, "__dict__"):
        d = dict(dialogue.__dict__)
    else:
        d = dict(dialogue)
    
    # turns 里的 DialogueTurn 也要转
    turns = d.get("turns", [])
    new_turns = []
    for t in turns:
        if hasattr(t, "__dict__"):
            new_turns.append(dict(t.__dict__))
        else:
            new_turns.append(t)
    d["turns"] = new_turns
    return d


# ============================================================
# 页面 UI
# ============================================================

st.title("💬 用户模拟器 - 自动生成对话")
st.markdown("---")

st.markdown("""
**功能**: 选指令 + 选用户类型 (Persona) → 自动跑出一通对话

- 🤖 助手模型扮演"被测对象"(美团客服/站长)
- 👤 用户模型扮演不同性格的用户 (4 种 Persona)
- ⚡ Mock 模式: 不调 API, 秒出 (调试用)
- 💰 LLM 模式: ~¥0.05/通 (DeepSeek-Flash)
""")

# 三列输入
col1, col2, col3 = st.columns(3)

with col1:
    st.subheader("1️⃣ 选指令")
    instr_options = {
        "🏢 官方 Sample 1 - 飞毛腿合同": "official_1_feimaotui",
        "🏢 官方 Sample 2 - 课程发布升级": "official_2_kecheng",
        "V1 - 骑手培训通知": "V1",
        "V2 - APP 强制更新": "V2",
        "V3 - 恶劣天气提醒": "V3",
        "V4 - 商家出餐慢核实": "V4",
        "V5 - 商家差评回访": "V5",
        "V6 - 复杂多步流程": "V6",
    }
    selected_instr = st.selectbox("任务指令", list(instr_options.keys()))
    instr_name = instr_options[selected_instr]

with col2:
    st.subheader("2️⃣ 选用户类型")
    personas = load_persona_info()
    persona_options = {info["name"]: pid for pid, info in personas.items()}
    selected_persona = st.selectbox("Persona", list(persona_options.keys()))
    persona_id = persona_options[selected_persona]
    
    # 展示该 persona 的说明
    info = personas[persona_id]
    st.caption(f"📝 {info['desc']}")
    st.caption(f"⏱️ 最大轮数: {info['max_turns']}")

with col3:
    st.subheader("3️⃣ 选模型")
    mode = st.radio(
        "运行模式",
        ["⚡ Mock (秒出, 调试用)", "🤖 LLM (真实跑, ¥0.05/通)"],
        index=0,
    )
    mock = "Mock" in mode
    
    if not mock:
        tested_model = st.selectbox(
            "被测模型 (扮演助手)",
            ["deepseek-v4-flash", "deepseek-v4-pro", "gpt-4o-mini", "gpt-5-mini"],
            index=0,
        )
        user_model = st.selectbox(
            "用户模型 (扮演用户)",
            ["deepseek-v4-flash", "deepseek-v4-pro", "gpt-4o-mini"],
            index=0,
        )
    else:
        tested_model = "mock-tested"
        user_model = "mock-user"

# 跑按钮
st.markdown("---")

if st.button("🚀 开始跑对话", type="primary", use_container_width=True):
    dialogue = run_simulator(instr_name, persona_id, tested_model, user_model, mock)
    
    if dialogue:
        st.success("✅ 对话生成完成!")
        
        # 保存到 session, 可以一键发到评测页
        dialogue_dict = dialogue_to_dict(dialogue)
        st.session_state["simulator_last_dialogue"] = dialogue_dict
        
        display_dialogue(dialogue)
        
        # 下载 + 跳转评测
        st.markdown("---")
        st.subheader("⬇️ 下一步")
        
        col_a, col_b = st.columns(2)
        
        with col_a:
            st.download_button(
                "📥 下载对话 JSONL",
                json.dumps(dialogue_dict, ensure_ascii=False) + "\n",
                file_name=f"{dialogue_dict.get('dialogue_id', 'dialogue')}.jsonl",
                mime="application/jsonl",
                use_container_width=True,
            )
        
        with col_b:
            st.info("💡 切到 **🧪 评测** 页, 上传刚下载的 jsonl 即可评测这通对话")

# 显示上次生成的(防止 streamlit 刷新丢失)
elif "simulator_last_dialogue" in st.session_state:
    st.markdown("---")
    st.markdown("**上次生成的对话:**")
    display_dialogue(st.session_state["simulator_last_dialogue"])
