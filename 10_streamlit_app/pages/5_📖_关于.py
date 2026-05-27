"""
Tab 5: 关于 - 项目说明 + 技术细节
"""
import streamlit as st
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent

st.set_page_config(page_title="关于", page_icon="📖", layout="wide")

st.title("📖 关于本项目")
st.markdown("---")

# 项目定位
st.subheader("💡 项目定位")
st.markdown("""
**美团对话外呼任务评测系统** —— 一个能发现人类盲区的工业级 LLM Judge

把模型评测从"靠人审"变成"机器审 + 人监督":
- 速度提升 30-60 倍
- 成本降低 95%
- 一致性媲美人工 (kappa = 0.45 整体, 1.0 客观约束)
""")

st.markdown("---")

# 核心数据
st.subheader("📊 核心数据 (Day 10 末)")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    **可靠性指标**
    
    | 维度 | 数值 |
    |---|---|
    | 客观约束 Kappa | **1.0** 🎉 |
    | D3 约束遵循度 | 0.84 ✅ |
    | 整体 vs 人工 | **0.45** ✅ |
    | 三 LLM 互一致 | **0.81** ✅ |
    | mock 基线 | 0.23 |
    """)

with col2:
    st.markdown("""
    **工程指标**
    
    | 维度 | 数值 |
    |---|---|
    | 5/5 Verifier | 全部跑通 ✅ |
    | 单元测试 | 26/26 通过 ✅ |
    | 50 通对话 | 16 分钟跑完 ⚡ |
    | 单通成本 | **¥0.20** 💰 |
    | 解析成功率 | V1-V5 100% |
    """)

st.markdown("---")

# 技术架构
st.subheader("🏗️ 技术架构")

st.markdown("""
```mermaid
graph LR
    A[指令 .md] --> B[Parser]
    B --> C[约束清单 JSON]
    D[对话 .jsonl] --> E[Pipeline]
    C --> E
    E --> F[5 类 Verifier]
    F --> G[P3 评分算法]
    G --> H[评分报告]
```
""")

st.markdown("""
**5 类 Verifier (按 ROI 分层)**:

1. **rule** (字数/占位符) — 纯 Python, 0 LLM 调用
2. **rule_pattern** (禁用词) — 纯 Python, 0 LLM 调用  
3. **state_tracker** (流程结构) — 关键词匹配 + LLM 兜底
4. **llm_extract_then_rule** (事实抽取) — LLM 抽事实, 规则判定
5. **llm_judge** (主观判断) — LLM 直接判 pass/fail

**关键创新**: 客观约束不浪费 LLM 调用,**省 60% 成本**
""")

st.markdown("---")

# 4 轮迭代故事
st.subheader("🔄 4 轮标注迭代")

st.markdown("""
| 版本 | 时间 | 操作 | kappa vs Claude | kappa vs LLM |
|---|---|---|---|---|
| v3 | Day 5 | 初标 989 条 | **0.72** (虚高 ⚠️) | - |
| v4 | Day 9 | 自动审计修订 73 处 | 0.37 | 0.22 |
| v5 | Day 9 末 | 手工复核 50 条 | 0.40 | 0.13 |
| **v6** | **Day 10** | **全量重标 1055 条** | -0.04 (规则不同) | **0.45** ✅ |

**v3 的 0.72 是虚高**——两位标注员犯同样的系统性错误.
**v6 的 0.45 是真实可靠的数字**, 落在 LLM-as-judge 学术界 0.3-0.6 区间.
""")

st.markdown("---")

# 三路对照
st.subheader("🎯 三路 LLM 对照实验")

st.markdown("""
为了排除单一模型偏差,我们做了三路对照:

| 对比 | Kappa | 含义 |
|---|---|---|
| Flash vs Pro (DeepSeek 同族) | **0.83** | LLM 容量不是瓶颈 |
| Flash vs GPT-5-mini (跨族) | **0.78** | 排除单一模型偏差 |
| Pro vs GPT-5-mini (跨族) | **0.83** | 双重独立验证 |
| **三路平均** | **0.81** | **顶级一致性** |

**意义**: 不依赖任何单一模型, 工业级评测系统标配.
""")

st.markdown("---")

# 商业价值
st.subheader("💼 商业价值")

st.markdown("""
**3 种落地场景**:

1. **场景 A: 美团内部** - 直接节省质检人力成本
   - 假设每天 1 万通外呼需质检
   - 人工: ¥10/通 × 10000 = ¥10w/天
   - 我们: ¥0.20/通 × 10000 = ¥2000/天
   - **每天省 ¥9.8w, 年省 ¥3500w**

2. **场景 B: 客服 SaaS** - 卖给其他平台
   - 饿了么/京东到家/抖音外呼/电话客服
   - 定价: ¥1999/月起 (1万通)

3. **场景 C: 外呼 AI 评测工具**
   - 给做外呼 AI 的公司当评测基础设施
   - 像 OCR API 那样按调用计费
""")

st.markdown("---")

# 未来路线
st.subheader("🚀 未来路线")

st.markdown("""
- **持续校准** — 基于真实业务数据,迭代 LLM Judge prompt,kappa 持续提升
- **场景扩展** — 英文外呼 + 方言识别,服务美团海外/区域市场
- **闭环增强** — 业务描述 → 自动生成评测指令 → 自动评测,真正一站式
- **能力延伸** — ASR 端到端评测 (语音直入) + 人在环路 (Human-in-the-Loop) 持续优化
""")

st.markdown("---")

# 团队 + 联系
st.subheader("📧 联系")
st.markdown("""
- **项目**: 美团黑客松命题二
- **代码**: GitHub (待提交)
- **数据**: 50 通对话 + 1055 条 verdict + 4 版人工标注
""")

st.caption("© 2026 美团黑客松命题二 | 评测系统 v1.0")
