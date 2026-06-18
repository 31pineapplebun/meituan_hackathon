"""配置空间(单一事实来源)。

前端通过 GET /api/config 拉取这里的选项来动态渲染配置表单 —— 内置指令 / 待测模型 /
persona / 评分维度都集中在这里定义,口径必须和评测引擎(09_pipeline/model_evaluation.py)
保持一致。把它放在后端,前端就不用硬编码这些业务常量。
"""
from pathlib import Path

# 仓库根目录: 12_api/config.py -> parent=12_api -> parent=仓库根
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---- 内置任务指令 ----
# md     = 指令原文(完整模式下喂给被测模型当 system prompt)
# parsed = 预解析的约束 JSON(评测打分用)
# has_demo = 是否有预置的真实评测结果(有则"快速演示"可秒出)
# 注意: variants 的 parsed 文件名是小写(v1_parsed.json),官方样例保留全名。
INSTRUCTIONS = {
    "official_1_feimaotui": {
        "label": "🏢 官方 Sample 1 - 飞毛腿合同",
        "md": PROJECT_ROOT / "03_examples" / "official" / "official_1_feimaotui.md",
        "parsed": PROJECT_ROOT / "08_parser" / "parsed_examples" / "official_1_feimaotui_parsed.json",
        "has_demo": True,
    },
    "official_2_kecheng": {
        "label": "🏢 官方 Sample 2 - 课程发布升级",
        "md": PROJECT_ROOT / "03_examples" / "official" / "official_2_kecheng.md",
        "parsed": PROJECT_ROOT / "08_parser" / "parsed_examples" / "official_2_kecheng_parsed.json",
        "has_demo": True,
    },
    "V1": {
        "label": "V1 - 骑手安全培训通知",
        "md": PROJECT_ROOT / "03_examples" / "variants" / "V1.md",
        "parsed": PROJECT_ROOT / "08_parser" / "parsed_examples" / "v1_parsed.json",
        "has_demo": True,
    },
    "V2": {
        "label": "V2 - APP 强制更新通知",
        "md": PROJECT_ROOT / "03_examples" / "variants" / "V2.md",
        "parsed": PROJECT_ROOT / "08_parser" / "parsed_examples" / "v2_parsed.json",
        "has_demo": True,
    },
    "V4": {
        "label": "V4 - 商家出餐慢核实",
        "md": PROJECT_ROOT / "03_examples" / "variants" / "V4.md",
        "parsed": PROJECT_ROOT / "08_parser" / "parsed_examples" / "v4_parsed.json",
        "has_demo": True,
    },
    "V5": {
        "label": "V5 - 商家差评回访",
        "md": PROJECT_ROOT / "03_examples" / "variants" / "V5.md",
        "parsed": PROJECT_ROOT / "08_parser" / "parsed_examples" / "v5_parsed.json",
        "has_demo": True,
    },
}

# ---- 待测模型(让哪个模型来演「客服」)----
MODELS = ["deepseek-v4-flash", "deepseek-v4-pro", "gpt-4o-mini", "gpt-5-mini"]

# ---- 8 类模拟用户(persona)----
# default: 前端默认勾选; fast: 是否有快速演示预置数据(只有这 4 个有真实预置结果)
PERSONAS = [
    {"id": "cooperative",       "label": "🤝 合作型",          "default": True,  "fast": True},
    {"id": "refuse_persistent", "label": "😤 坚持拒绝型",       "default": False, "fast": True},
    {"id": "out_of_scope",      "label": "🌀 越界提问型",       "default": True,  "fast": True},
    {"id": "interruption",      "label": "✋ 打断型",           "default": False, "fast": True},
    {"id": "state_busy",        "label": "🚗 状态型(忙/开车)", "default": False, "fast": False},
    {"id": "ambiguous",         "label": "🤔 模糊型",           "default": False, "fast": False},
    {"id": "adversarial",       "label": "⚔️ 对抗型",           "default": False, "fast": False},
    {"id": "probing",           "label": "❓ 提问型",           "default": False, "fast": False},
]

# ---- 5 个评分维度(key 与引擎 dim_scores / dim_avg 的键一一对应)----
DIMENSIONS = [
    {"key": "D1_flow_compliance",       "short": "D1 流程", "name": "流程遵循度", "weight": 25},
    {"key": "D2_task_completion",       "short": "D2 任务", "name": "任务完成度", "weight": 25},
    {"key": "D3_constraint_compliance", "short": "D3 约束", "name": "约束遵循度", "weight": 20},
    {"key": "D4_knowledge_accuracy",    "short": "D4 知识", "name": "知识准确性", "weight": 15},
    {"key": "D5_dialogue_quality",      "short": "D5 对话", "name": "对话质量",   "weight": 15},
]
