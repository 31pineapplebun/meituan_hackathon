"""
模型级评测 (Model-Level Evaluation)

赛题核心: 官方要求"给指令 + 给待测模型 → 出报告",评的是【模型】不是【单通对话】。

本模块把"单通评测"聚合成"模型能力画像":
- 输入: 指令 + 待测模型 + N 个 persona
- 流程: 对每个 persona 跑一通对话 → 评测 → 聚合
- 输出: 模型在该任务上的综合得分 + 各 persona 分解 + 整体诊断

两种模式:
- fast (快速演示): 读取预置的真实评测结果, 秒出 (评委演示用)
- full (完整运行): 实时调 simulator + pipeline 真跑 (需 API key)
"""
import json
import sys
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

PIPELINE_DIR = Path(__file__).parent
sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(PIPELINE_DIR.parent / "07_simulator"))


# =====================================================================
# 聚合核心: 把多通对话的评测结果聚成模型画像
# =====================================================================

def aggregate_model_report(
    instruction_name: str,
    model_name: str,
    per_dialogue_results: list,
) -> dict:
    """把 N 通对话的评测结果聚合成模型级报告

    Args:
        instruction_name: 指令名 (如 V1 / official_1_feimaotui)
        model_name: 被测模型名 (如 deepseek-v4-flash)
        per_dialogue_results: [{dialogue_id, persona_id, score_report, verdict_details}, ...]

    Returns:
        模型级聚合报告 dict
    """
    if not per_dialogue_results:
        return {"error": "没有评测结果可聚合"}

    n_total = len(per_dialogue_results)

    # 分离: 可评测 vs 无法评测(空对话/API失败)
    evaluable = [r for r in per_dialogue_results
                 if r["score_report"].get("final_score") is not None]
    n_unevaluable = n_total - len(evaluable)

    if not evaluable:
        return {
            "error": f"全部 {n_total} 个场景都无法评测(对话为空或 API 调用失败)。"
                     f"请检查 API key 是否有效、模型是否正常响应。"
        }

    n_dialogues = len(evaluable)

    # 1. 综合得分 = 可评测场景平均
    scores = [r["score_report"]["final_score"] for r in evaluable]
    avg_score = round(sum(scores) / len(scores), 1)
    min_score = min(scores)
    max_score = max(scores)

    # 2. 各 persona 表现分解 (只含可评测的)
    persona_breakdown = []
    for r in evaluable:
        sr = r["score_report"]
        persona_breakdown.append({
            "persona_id": r.get("persona_id", "?"),
            "dialogue_id": r.get("dialogue_id", "?"),
            "final_score": sr["final_score"],
            "critical_pass_rate": sr.get("critical_pass_rate", 0),
            "ceiling": sr.get("ceiling"),
            "n_turns": r.get("n_turns", 0),
        })
    # 按分数排序, 最差的在前 (方便定位短板)
    persona_breakdown.sort(key=lambda x: x["final_score"])

    # 3. 维度平均分 (5 个维度跨可评测对话平均)
    dim_keys = ["D1_flow_compliance", "D2_task_completion", "D3_constraint_compliance",
                "D4_knowledge_accuracy", "D5_dialogue_quality"]
    dim_avg = {}
    for k in dim_keys:
        vals = [r["score_report"].get("dim_scores", {}).get(k) for r in evaluable]
        vals = [v for v in vals if v is not None]
        dim_avg[k] = round(sum(vals) / len(vals), 1) if vals else None

    # 4. 约束级聚合: 哪些约束最常 fail (跨所有对话)
    constraint_fail_count = defaultdict(int)
    constraint_total_count = defaultdict(int)
    constraint_name_map = {}
    for r in evaluable:
        for v in r.get("verdict_details", []):
            cid = v.get("constraint_id", "?")
            constraint_name_map[cid] = v.get("constraint_name", "")
            if v.get("verdict") == "fail":
                constraint_fail_count[cid] += 1
            if v.get("verdict") in ("pass", "fail"):  # 排除 na/not_impl
                constraint_total_count[cid] += 1

    # 计算每条约束的失败率, 排序
    weak_constraints = []
    for cid, total in constraint_total_count.items():
        n_fail = constraint_fail_count.get(cid, 0)
        if n_fail > 0:
            weak_constraints.append({
                "constraint_id": cid,
                "constraint_name": constraint_name_map.get(cid, "")[:50],
                "fail_count": n_fail,
                "total_count": total,
                "fail_rate": round(n_fail / total * 100, 0),
            })
    weak_constraints.sort(key=lambda x: (-x["fail_rate"], -x["fail_count"]))

    # 5. 整体诊断结论 (自动生成一句话评语)
    if avg_score >= 85:
        grade = "优秀"
        diagnosis = f"模型在「{instruction_name}」任务上表现优秀,各场景稳定,可投入生产。"
    elif avg_score >= 70:
        grade = "良好"
        worst = persona_breakdown[0]
        diagnosis = f"模型整体良好,但在「{_persona_cn(worst['persona_id'])}」场景较弱(得分 {worst['final_score']}),建议针对性优化。"
    elif avg_score >= 50:
        grade = "需改进"
        diagnosis = f"模型存在明显短板,在多个场景未达标,需重点优化流程遵循与约束执行。"
    else:
        grade = "不合格"
        diagnosis = f"模型在「{instruction_name}」任务上不合格,建议重新设计 prompt 或更换模型。"

    if n_unevaluable > 0:
        diagnosis += f" (注: {n_unevaluable}/{n_total} 个场景因对话异常未纳入评分)"

    return {
        "report_type": "model_level",
        "instruction_name": instruction_name,
        "model_name": model_name,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": {
            "avg_score": avg_score,
            "min_score": min_score,
            "max_score": max_score,
            "n_dialogues": n_dialogues,
            "n_unevaluable": n_unevaluable,
            "n_total": n_total,
            "grade": grade,
            "diagnosis": diagnosis,
        },
        "dim_avg": dim_avg,
        "persona_breakdown": persona_breakdown,
        "weak_constraints": weak_constraints[:10],  # 最弱的 10 条
        "per_dialogue_results": per_dialogue_results,  # 保留明细供下钻
    }


def _persona_cn(persona_id: str) -> str:
    """persona 中文名"""
    return {
        "cooperative": "合作型",
        "refuse_persistent": "坚持拒绝型",
        "out_of_scope": "越界提问型",
        "interruption": "打断型",
        "state_busy": "状态型(忙/开车)",
        "ambiguous": "模糊型",
        "adversarial": "对抗型",
        "probing": "提问型",
    }.get(persona_id, persona_id)


# =====================================================================
# 快速模式: 从预置的真实评测结果聚合 (评委演示秒出)
# =====================================================================

def run_fast_demo(instruction_name: str, model_name: str = "deepseek-v4-flash") -> dict:
    """快速演示: 读取预置的真实评测结果聚合成模型报告

    数据来源: 09_pipeline/model_demo/{instruction_name}_model_report.json (预生成)
    """
    demo_path = PIPELINE_DIR / "model_demo" / f"{instruction_name}_model_report.json"
    if demo_path.exists():
        with open(demo_path, encoding="utf-8") as f:
            return json.load(f)
    return {"error": f"没有 {instruction_name} 的预置演示数据,请用完整模式真跑"}


# =====================================================================
# 完整模式: 实时跑 simulator + pipeline
# =====================================================================

def run_full_evaluation(
    instruction_path: str,
    instruction_text: str,
    instruction_name: str,
    model_name: str,
    persona_list: list,
    user_model: str = "deepseek-v4-flash",
    progress_callback=None,
) -> dict:
    """完整模式: 对每个 persona 真跑对话 + 评测, 聚合成模型报告

    Args:
        instruction_path: 预解析 JSON 路径 (用于评测)
        instruction_text: 指令原文 (用于模拟器)
        instruction_name: 指令名
        model_name: 被测模型
        persona_list: 要测的 persona 列表
        user_model: 模拟用户的模型
        progress_callback: fn(current, total, msg) 进度回调
    """
    # 关键: 完整模式必须关闭 verifier 的 mock (默认是开的)。
    # USE_MOCK 是 verifier 模块 import 时读取的常量, 所以必须在 import 前设环境变量。
    import os
    os.environ["VERIFIER_LLM_MOCK"] = "0"
    os.environ["VERIFIER_LLM_MODEL"] = model_name

    import simulator_v2
    from pipeline import run_pipeline

    # 加载预解析指令
    with open(instruction_path, encoding="utf-8") as f:
        instruction = json.load(f)

    per_dialogue_results = []
    total = len(persona_list)

    for i, persona_id in enumerate(persona_list):
        if progress_callback:
            progress_callback(i, total, f"[{persona_id}] 生成对话中...")

        # 1. 跑对话
        dialogue_id = f"{instruction_name}_{persona_id}_full"
        try:
            dlg = simulator_v2.run_one_dialogue(
                instruction_text=instruction_text,
                instruction_name=instruction_name,
                persona_id=persona_id,
                tested_model=model_name,
                user_model=user_model,
                dialogue_id=dialogue_id,
                mock=False,
            )
            # 转 dict
            dlg_dict = _dialogue_to_dict(dlg)
        except Exception as e:
            per_dialogue_results.append({
                "dialogue_id": dialogue_id,
                "persona_id": persona_id,
                "error": str(e),
                "score_report": {"final_score": 0, "dim_scores": {}},
                "verdict_details": [],
                "n_turns": 0,
            })
            continue

        if progress_callback:
            progress_callback(i, total, f"[{persona_id}] 评测中...")

        # 2. 评测
        try:
            output = run_pipeline(instruction, dlg_dict)
            per_dialogue_results.append({
                "dialogue_id": dialogue_id,
                "persona_id": persona_id,
                "score_report": output["score_report"],
                "verdict_details": output["verdict_details"],
                "detailed_suggestions": output.get("detailed_suggestions", []),
                "n_turns": len(dlg_dict.get("turns", [])),
                "dialogue": dlg_dict,
            })
        except Exception as e:
            per_dialogue_results.append({
                "dialogue_id": dialogue_id,
                "persona_id": persona_id,
                "error": str(e),
                "score_report": {"final_score": 0, "dim_scores": {}},
                "verdict_details": [],
                "n_turns": len(dlg_dict.get("turns", [])),
            })

    if progress_callback:
        progress_callback(total, total, "聚合报告中...")

    return aggregate_model_report(instruction_name, model_name, per_dialogue_results)


def _dialogue_to_dict(dlg):
    """Dialogue dataclass → dict"""
    if hasattr(dlg, "__dict__"):
        d = dict(dlg.__dict__)
    else:
        d = dict(dlg)
    turns = d.get("turns", [])
    new_turns = []
    for t in turns:
        if hasattr(t, "__dict__"):
            new_turns.append(dict(t.__dict__))
        else:
            new_turns.append(t)
    d["turns"] = new_turns
    return d


if __name__ == "__main__":
    # 自测: 用 mock 数据测聚合逻辑
    mock_results = [
        {"dialogue_id": "V1_coop", "persona_id": "cooperative", "n_turns": 11,
         "score_report": {"final_score": 92, "critical_pass_rate": 1.0, "ceiling": None,
                          "dim_scores": {"D1_flow_compliance": 95, "D2_task_completion": 100,
                                         "D3_constraint_compliance": 90, "D4_knowledge_accuracy": 85,
                                         "D5_dialogue_quality": 88}},
         "verdict_details": [{"constraint_id": "V1_C01", "constraint_name": "字数", "verdict": "pass"},
                             {"constraint_id": "V1_C03", "constraint_name": "口语化", "verdict": "fail"}]},
        {"dialogue_id": "V1_adv", "persona_id": "adversarial", "n_turns": 14,
         "score_report": {"final_score": 65, "critical_pass_rate": 0.8, "ceiling": 65,
                          "dim_scores": {"D1_flow_compliance": 60, "D2_task_completion": 70,
                                         "D3_constraint_compliance": 65, "D4_knowledge_accuracy": 80,
                                         "D5_dialogue_quality": 55}},
         "verdict_details": [{"constraint_id": "V1_C01", "constraint_name": "字数", "verdict": "pass"},
                             {"constraint_id": "V1_C03", "constraint_name": "口语化", "verdict": "fail"}]},
    ]
    report = aggregate_model_report("V1", "deepseek-v4-flash", mock_results)
    print("=== 模型级聚合报告自测 ===")
    print(f"综合得分: {report['summary']['avg_score']} ({report['summary']['grade']})")
    print(f"诊断: {report['summary']['diagnosis']}")
    print(f"分数范围: {report['summary']['min_score']} - {report['summary']['max_score']}")
    print(f"维度平均: {report['dim_avg']}")
    print(f"persona 分解 (最弱在前):")
    for p in report["persona_breakdown"]:
        print(f"  {_persona_cn(p['persona_id'])}: {p['final_score']}")
    print(f"最弱约束:")
    for c in report["weak_constraints"]:
        print(f"  {c['constraint_id']} ({c['constraint_name']}): 失败率 {c['fail_rate']}% ({c['fail_count']}/{c['total_count']})")
    print()
    print("✅ 聚合逻辑自测通过" if report['summary']['avg_score'] == 78.5 else "❌ 聚合分数异常")