"""共享前端主题 — 单一来源的配色/CSS + 侧边栏品牌 + 页眉。

主页 app.py 与各子页统一调用, 避免配色在多个文件间漂移。
配色: 深蓝 #1a2233 + 克制金 #b8860b + 浅灰底 #f6f7f9 (克制、留白、高级感, 弃用 AI 紫渐变)。
用法(必须在 st.set_page_config 之后):
    import _theme
    _theme.inject_theme()
    _theme.render_sidebar_brand()
    _theme.render_page_header("标题", "副标题")
"""
import streamlit as st

THEME_CSS = """
<style>
    /* ===== 全局: 系统字体 + 浅灰底, 收窄内容宽度增加留白 ===== */
    html, body, [class*="css"] {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                     "Microsoft YaHei", "Source Han Sans SC", sans-serif;
    }
    [data-testid="stAppViewContainer"] { background: #f6f7f9; }
    .block-container { padding-top: 2.0rem; padding-bottom: 3rem; max-width: 1080px; }
    h1, h2, h3, h4, h5 { color: #1a2233; letter-spacing: -0.2px; }
    hr { margin: 1.1rem 0; border-color: #e8ebf0; }

    /* ===== 侧边栏: 干净浅色 + 细分隔线 ===== */
    section[data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #eceff3; }

    /* ===== Metric: 深蓝数字 + 灰标签 ===== */
    [data-testid="stMetricValue"] { font-size: 24px; font-weight: 800; color: #1a2233; }
    [data-testid="stMetricLabel"] { color: #6b7585; font-weight: 600; }

    /* ===== 主按钮: 深蓝(替换默认红, 去"默认感") ===== */
    .stButton > button[kind="primary"], button[data-testid="baseButton-primary"] {
        background: #1a2233; color: #ffffff; border: none; border-radius: 10px;
        font-weight: 600; letter-spacing: 0.3px; box-shadow: 0 2px 10px rgba(26,34,51,0.20);
    }
    .stButton > button[kind="primary"]:hover, button[data-testid="baseButton-primary"]:hover {
        background: #2a3650; color: #ffffff;
    }
    .stButton > button { border-radius: 10px; }
    [data-testid="stExpander"] { border: 1px solid #eceff3; border-radius: 12px; }
</style>
"""

SIDEBAR_BRAND = """
<div style="padding: 4px 2px;">
  <div style="height:3px;width:44px;background:#b8860b;border-radius:2px;margin-bottom:16px;"></div>
  <div style="font-size:20px;font-weight:700;color:#1a2233;line-height:1.35;">外呼指令遵循<br>评测系统</div>
  <div style="font-size:11.5px;color:#8a93a3;letter-spacing:1px;margin-top:8px;">INSTRUCTION-FOLLOWING&nbsp;EVAL</div>

  <div style="margin-top:30px;font-size:13px;color:#7a8499;letter-spacing:1px;font-weight:700;">核心能力</div>
  <div style="margin-top:12px;color:#3d4759;font-size:14.5px;line-height:2.0;">
    5 类 Verifier 分层判定<br>
    8 Persona 用户模拟<br>
    P3 三层评分 · 模型画像<br>
    23 类约束体系
  </div>

  <div style="margin-top:30px;font-size:13px;color:#7a8499;letter-spacing:1px;font-weight:700;">评测可靠性</div>
  <div style="margin-top:14px;display:flex;gap:26px;">
    <div>
      <div style="font-size:28px;font-weight:800;color:#1a2233;line-height:1;">0.81</div>
      <div style="font-size:13px;color:#8a93a3;margin-top:5px;">三路 LLM&nbsp;κ</div>
    </div>
    <div>
      <div style="font-size:28px;font-weight:800;color:#1a2233;line-height:1;">81.8%</div>
      <div style="font-size:13px;color:#8a93a3;margin-top:5px;">人机一致率</div>
    </div>
  </div>

  <div style="margin-top:34px;padding-top:14px;border-top:1px solid #e8ebf0;
              font-size:12.5px;color:#9aa3b2;letter-spacing:0.3px;">美团黑客松 · 命题二</div>
</div>
"""


def inject_theme():
    """注入全局主题 CSS (须在 set_page_config 之后调用)。"""
    st.markdown(THEME_CSS, unsafe_allow_html=True)


def render_sidebar_brand():
    """渲染侧边栏极简品牌看板。"""
    with st.sidebar:
        st.markdown(SIDEBAR_BRAND, unsafe_allow_html=True)


def render_page_header(title, subtitle=""):
    """渲染统一页眉: 细金线 + 大标题 + 副标(克制排版, 替代 emoji st.title)。"""
    sub = (f'<div style="font-size:14px;color:#6b7585;margin-top:9px;">{subtitle}</div>'
           if subtitle else "")
    st.markdown(f"""
    <div style="padding: 6px 0 2px;">
      <div style="height:3px;width:52px;background:#b8860b;border-radius:2px;margin-bottom:14px;"></div>
      <div style="font-size:30px;font-weight:800;color:#1a2233;letter-spacing:-0.6px;line-height:1.2;">{title}</div>
      {sub}
    </div>
    """, unsafe_allow_html=True)
