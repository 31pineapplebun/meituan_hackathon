import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "09_pipeline"))

from pipeline import run_pipeline  # noqa: E402


def _load_json(path: Path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _load_first_jsonl(path: Path):
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                return json.loads(line)
    raise RuntimeError("jsonl 为空")


def main():
    os.environ["VERIFIER_LLM_MOCK"] = "1"
    os.environ["PIPELINE_MAX_WORKERS"] = "2"

    instruction = _load_json(ROOT / "08_parser" / "parsed_examples" / "v1_parsed.json")
    dialogue = _load_first_jsonl(ROOT / "09_pipeline" / "official_demo" / "official_1_feimaotui_cooperative_demo.jsonl")

    output = run_pipeline(instruction, dialogue, max_workers=2)

    assert "score_report" in output
    assert "verdict_details" in output
    assert "stats" in output
    assert isinstance(output["verdict_details"], list)
    assert output["stats"]["total_constraints"] == len(instruction.get("atomic_constraints", []))

    score_report = output["score_report"]
    assert score_report["final_score"] is not None
    assert 0 <= score_report["final_score"] <= 100

    # 关键结构快照断言（避免评测主输出结构被破坏）
    expected_dim_keys = {
        "D1_flow_compliance",
        "D2_task_completion",
        "D3_constraint_compliance",
        "D4_knowledge_accuracy",
        "D5_dialogue_quality",
    }
    assert set(score_report["dim_scores"].keys()) == expected_dim_keys

    print("pipeline snapshot test passed")


if __name__ == "__main__":
    main()

