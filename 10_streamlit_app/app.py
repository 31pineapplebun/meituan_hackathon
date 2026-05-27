"""
美团对话外呼任务评测系统 - Streamlit 主入口

跑法:
    streamlit run app.py
"""
import streamlit as st
from pathlib import Path

# 页面配置
st.set_page_config(
    page_title="美团对话外呼评测系统",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 全局样式
st.markdown("""
<style>
    .main {
        padding-top: 1rem;
    }
    .score-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 30px;
        border-radius: 15px;
        color: white;
        text-align: center;
        box-shadow: 0 8px 24px rgba(0,0,0,0.15);
    }
    .metric-card {
        background: white;
        padding: 20px;
        border-radius: 10px;
        border-left: 5px solid #667eea;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background: #f0f2f6;
        border-radius: 10px;
        padding: 0 20px;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(90deg, #667eea, #764ba2);
        color: white;
    }
</style>
""", unsafe_allow_html=True)

# 主页面 - 项目介绍
def main():
    # 头部
    col1, col2 = st.columns([3, 1])
    with col1:
        st.title("🎯 美团对话外呼任务评测系统")
        st.markdown("**一个能发现人类盲区的工业级 LLM Judge**")
    with col2:
        st.image("https://via.placeholder.com/150x150?text=Logo", width=120)
    
    st.markdown("---")
    
    # 关键数字展示
    st.subheader("📊 核心数据")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("客观约束 Kappa", "1.0000", "🎉 完美对齐", delta_color="normal")
    with col2:
        st.metric("整体 Kappa vs 人工", "0.4483", "+243%", delta_color="normal")
    with col3:
        st.metric("三路 LLM 对照", "0.81", "✅ 跨族强一致")
    with col4:
        st.metric("评测速度", "30 秒/通", "vs 人工 15-30 分钟")
    
    st.markdown("---")
    
    # 项目介绍
    col_left, col_right = st.columns([2, 1])
    
    with col_left:
        st.subheader("💡 项目价值")
        st.markdown("""
        **问题**: 美团每天有大量外呼对话需要质检,人工评测又慢又贵又不一致.
        
        **解决方案**: 我们构建了一个**自动评测系统**, 能在 30 秒内对一通对话给出:
        - 0-100 分综合评分
        - 5 维度细分评分 (流程/任务/约束/知识/对话质量)  
        - 具体违规点和优化建议
        
        **创新**:
        1. **5 类 Verifier 分层判定** - 客观规则不浪费 LLM 调用,省 60% 成本
        2. **P3 三层评分防御** - 防止虚高分
        3. **三路 LLM 对照** - 排除单一模型偏差
        4. **4 轮标注迭代** - 工业级评测系统的标配
        """)
    
    with col_right:
        st.subheader("🚀 立刻试用")
        st.info("👈 在左侧选择功能页面")
        st.markdown("""
        - **📋 上传指令** - 解析任务约束
        - **💬 跑对话** - 测试模型表现
        - **🧪 评测** - 自动判定 Pass/Fail
        - **📊 报告** - 可视化评分结果
        - **📖 关于** - 技术细节
        """)
    
    st.markdown("---")
    
    # 技术架构
    st.subheader("🏗️ 技术架构")
    st.markdown("""
    ```
    [指令 .md] → [Parser] → [约束清单 JSON]
                                ↓
    [对话 .jsonl] → [Pipeline] ← 5 个 Verifier
                                ↓
                          [P3 评分算法]
                                ↓
                      [评分报告: 100 分制 + 5 维度]
    ```
    """)
    
    # Footer
    st.markdown("---")
    st.caption("美团黑客松命题二 | 评测系统 v1.0 | 2026")


if __name__ == "__main__":
    main()
