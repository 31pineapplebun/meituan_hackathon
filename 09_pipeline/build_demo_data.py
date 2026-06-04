"""
生成预置演示数据: 把真实的 flash 评测结果 (batch_verdicts_flash.jsonl)
聚合成模型级报告, 存到 model_demo/ 供"快速演示"秒读。

数据真实性: 这些 verdict 是 Day 9 用 deepseek-v4-flash 真实跑出来的,
不是 mock, 不是手工编的。pass 率 68-79%, 分数真实可信。
"""
import json
import sys
from pathlib import Path
from collections import defaultdict

PIPELINE_DIR = Path(__file__).parent
sys.path.insert(0, str(PIPELINE_DIR))

from model_evaluation import aggregate_model_report

# 复用 P3 评分
from pipeline import compute_p3_score


def load_flash_verdicts():
    """读真实 flash 评测 verdicts, 按 dialogue 分组"""
    by_dialogue = defaultdict(list)
    path = PIPELINE_DIR / "batch_results" / "batch_verdicts_flash.jsonl"
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            v = json.loads(line)
            by_dialogue[v["dialogue_id"]].append(v)
    return by_dialogue


def load_parsed_instruction(instr_name):
    """加载预解析指令 (拿 constraints 元数据)"""
    path = PIPELINE_DIR.parent / "08_parser" / "parsed_examples" / f"{instr_name.lower()}_parsed.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class _V:
    """把 dict verdict 包成有属性的对象 (compute_p3_score 需要)"""
    def __init__(self, d):
        self.verdict = d.get("verdict", "na")
        self.constraint_id = d.get("constraint_id", "")
        self.constraint_name = d.get("constraint_name", "")
        self.verifier_type = d.get("verifier_type", "")
        self.evidence = d.get("evidence", "")
        self.reason = d.get("reason", "")
        self.confidence = d.get("confidence", 1.0)
    @property
    def passed(self):
        return self.verdict == "pass"
    def to_dict(self):
        return {"verdict": self.verdict, "constraint_id": self.constraint_id,
                "constraint_name": self.constraint_name, "verifier_type": self.verifier_type,
                "evidence": self.evidence, "reason": self.reason, "confidence": self.confidence}


def parse_persona(dialogue_id):
    """从 dialogue_id 提取 persona (V1_cooperative_xxx → cooperative)"""
    parts = dialogue_id.split("_")
    # V1_cooperative_1779... → cooperative
    # V1_out_of_scope_xxx → out_of_scope
    # V1_refuse_persistent_xxx → refuse_persistent
    if "out_of_scope" in dialogue_id:
        return "out_of_scope"
    if "refuse_persistent" in dialogue_id:
        return "refuse_persistent"
    if len(parts) >= 2:
        return parts[1]
    return "unknown"


def build_demo_for_instruction(instr_name):
    """为一个指令构建模型级演示报告"""
    by_dialogue = load_flash_verdicts()
    instruction = load_parsed_instruction(instr_name)
    constraints = instruction.get("atomic_constraints", [])

    # 找出该指令的所有对话
    instr_dialogues = {did: vs for did, vs in by_dialogue.items()
                       if did.startswith(instr_name + "_")}

    if not instr_dialogues:
        print(f"  ⚠️ {instr_name}: 没有真实评测数据")
        return None

    per_dialogue_results = []
    for did, verdicts in sorted(instr_dialogues.items()):
        # 包成对象算 P3 分
        v_objs = [_V(v) for v in verdicts]
        score_report = compute_p3_score(v_objs, constraints)
        per_dialogue_results.append({
            "dialogue_id": did,
            "persona_id": parse_persona(did),
            "score_report": score_report,
            "verdict_details": verdicts,
            "n_turns": 0,  # 真实对话轮数 csv 里没存, 留 0
        })

    report = aggregate_model_report(instr_name, "deepseek-v4-flash", per_dialogue_results)
    return report


def main():
    out_dir = PIPELINE_DIR / "model_demo"
    out_dir.mkdir(exist_ok=True)

    print("=== 生成模型级演示报告 (基于真实 flash 评测数据) ===\n")
    for instr in ["V1", "V2", "V4", "V5"]:
        report = build_demo_for_instruction(instr)
        if report:
            out_path = out_dir / f"{instr}_model_report.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
            s = report["summary"]
            print(f"  ✓ {instr}: 综合 {s['avg_score']} ({s['grade']}), "
                  f"{s['n_dialogues']} 通, 范围 {s['min_score']}-{s['max_score']}")
            print(f"     诊断: {s['diagnosis']}")

    print("\n✅ 预置演示数据生成完成")


if __name__ == "__main__":
    main()
