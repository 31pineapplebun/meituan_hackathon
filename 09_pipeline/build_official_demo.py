"""
为 official sample 生成「持久化对话 + 可复现评测报告」。

背景 (2026-06-06): 完整模式 live 评测分数不可复现 —— 对话每次重新生成 (simulator
走自己的 dispatch, 不经 llm_client 的 seed/缓存, deepseek 非确定), 导致同配置
多次跑分 55→90→83 乱跳, 写报告/演示拿不到稳定数字。

方案 (与 build_demo_data.py 同思路):
  对话只 live 生成一次并落盘 (official_demo/*_live.jsonl); 之后评测固定对话。
  评测侧 (run_pipeline → llm_judge/llm_extract/state_tracker 的 LLM 兜底) 全部走
  llm_client (seed=42 + 结果缓存), 对固定对话是确定的 → 报告数字稳定可复现。

  这也是 official sample 能进「快速演示」的前提 (model_demo/{name}_model_report.json)。

用法:
  python build_official_demo.py --generate   # 真跑: 生成对话+落盘+评测+存报告 (需 API, 跑一次)
  python build_official_demo.py              # 复现: 读已落盘对话重新评测+存报告 (验证可复现)
  可选: --instruction official_1_feimaotui  --personas cooperative,out_of_scope,refuse_persistent,interruption
"""
import os
import sys
import json
import argparse
from pathlib import Path

PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent
sys.path.insert(0, str(PIPELINE_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "07_simulator"))

DEMO_DIR = PIPELINE_DIR / "official_demo"
REPORT_DIR = PIPELINE_DIR / "model_demo"

# official sample 配置
INSTR_CFG = {
    "official_1_feimaotui": {
        "md": PROJECT_ROOT / "03_examples" / "official" / "official_1_feimaotui.md",
        "parsed": PROJECT_ROOT / "08_parser" / "parsed_examples" / "official_1_feimaotui_parsed.json",
    },
    "official_2_kecheng": {
        "md": PROJECT_ROOT / "03_examples" / "official" / "official_2_kecheng.md",
        "parsed": PROJECT_ROOT / "08_parser" / "parsed_examples" / "official_2_kecheng_parsed.json",
    },
}

DEFAULT_PERSONAS = ["cooperative", "out_of_scope", "refuse_persistent", "interruption"]


def _load_dotenv_silent():
    """在常见位置找 .env 并静默载入 os.environ (绝不打印 key 值, 不写文件)。"""
    for p in [PROJECT_ROOT / ".env", PROJECT_ROOT.parent / ".env", Path.cwd() / ".env"]:
        if p.exists():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            return True
    return False


def _persisted_path(instr_name, persona):
    return DEMO_DIR / f"{instr_name}_{persona}_live.jsonl"


def generate_dialogues(instr_name, personas, model):
    """live 生成对话并落盘 (含变量替换 + 关闭 mock)。需要 API key。"""
    import simulator_v2
    cfg = INSTR_CFG[instr_name]
    md_text = cfg["md"].read_text(encoding="utf-8")

    # 变量替换: 喂给被测模型的指令必须是具体值, 否则模型复读/瞎编占位符
    variables = simulator_v2.load_variable_values(instr_name)
    if variables:
        for k, v in variables.items():
            md_text = md_text.replace(f"${{{k}}}", str(v))
        print(f"  变量替换: {list(variables.keys())}")

    DEMO_DIR.mkdir(exist_ok=True)
    for persona in personas:
        did = f"{instr_name}_{persona}_live"
        print(f"  [{persona}] 生成对话中 (live)...", flush=True)
        dlg = simulator_v2.run_one_dialogue(
            instruction_text=md_text, instruction_name=instr_name,
            persona_id=persona, tested_model=model, user_model=model,
            dialogue_id=did, mock=False,
        )
        d = dlg.__dict__ if hasattr(dlg, "__dict__") else dict(dlg)
        d["turns"] = [t.__dict__ if hasattr(t, "__dict__") else t for t in d.get("turns", [])]
        with open(_persisted_path(instr_name, persona), "w", encoding="utf-8") as f:
            f.write(json.dumps(d, ensure_ascii=False))
        print(f"      落盘: {_persisted_path(instr_name, persona).name} ({len(d['turns'])} 轮)")


def load_persisted(instr_name, personas):
    """读已落盘对话。缺失的 persona 跳过并提示。"""
    dialogues = {}
    for persona in personas:
        p = _persisted_path(instr_name, persona)
        if p.exists():
            dialogues[persona] = json.loads(p.read_text(encoding="utf-8").strip())
        else:
            print(f"  ⚠️ 缺少落盘对话: {p.name} (请先 --generate)")
    return dialogues


def evaluate(instr_name, dialogues, model):
    """对固定对话评测 + 聚合。verifier 侧 seed+缓存 → 可复现。"""
    from pipeline import run_pipeline
    from model_evaluation import aggregate_model_report
    instruction = json.loads(INSTR_CFG[instr_name]["parsed"].read_text(encoding="utf-8"))

    per_dialogue_results = []
    for persona, dlg in dialogues.items():
        print(f"  [{persona}] 评测中 ({len(dlg.get('turns', []))} 轮)...", flush=True)
        out = run_pipeline(instruction, dlg)
        per_dialogue_results.append({
            "dialogue_id": dlg.get("dialogue_id", f"{instr_name}_{persona}_live"),
            "persona_id": persona,
            "score_report": out["score_report"],
            "verdict_details": out["verdict_details"],
            "detailed_suggestions": out.get("detailed_suggestions", []),
            "n_turns": len(dlg.get("turns", [])),
            "dialogue": dlg,
        })
    return aggregate_model_report(instr_name, model, per_dialogue_results)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--generate", action="store_true", help="重新 live 生成对话 (需 API)")
    ap.add_argument("--instruction", default="official_1_feimaotui")
    ap.add_argument("--personas", default=",".join(DEFAULT_PERSONAS))
    ap.add_argument("--model", default="deepseek-v4-flash")
    args = ap.parse_args()

    instr_name = args.instruction
    personas = [p.strip() for p in args.personas.split(",") if p.strip()]

    # 完整评测必须关 mock + 指定 verifier 模型 (在 import pipeline 前设)
    os.environ["VERIFIER_LLM_MOCK"] = "0"
    os.environ["VERIFIER_LLM_MODEL"] = args.model
    os.environ.setdefault("LLM_SEED", "42")
    os.environ.setdefault("LLM_SELF_CONSISTENCY", "1")

    if not _load_dotenv_silent():
        print("⚠️ 未找到 .env; 依赖环境变量里已有 DEEPSEEK_API_KEY")
    if not os.environ.get("DEEPSEEK_API_KEY") and args.model.startswith("deepseek"):
        print("❌ 缺少 DEEPSEEK_API_KEY, 无法真跑"); sys.exit(2)

    print(f"=== build_official_demo: {instr_name} / {args.model} / {personas} ===")
    print(f"模式: {'GENERATE(live生成+评测)' if args.generate else 'EVALUATE(读落盘对话, 验证可复现)'}\n")

    if args.generate:
        generate_dialogues(instr_name, personas, args.model)
        print()

    dialogues = load_persisted(instr_name, personas)
    if not dialogues:
        print("❌ 没有可评测的落盘对话"); sys.exit(1)

    report = evaluate(instr_name, dialogues, args.model)
    if report.get("error"):
        print("聚合 error:", report["error"]); sys.exit(1)

    REPORT_DIR.mkdir(exist_ok=True)
    out_path = REPORT_DIR / f"{instr_name}_model_report.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    s = report["summary"]
    print(f"\n综合得分: {s['avg_score']} ({s['grade']})  范围 {s['min_score']}~{s['max_score']}  可评测 {s['n_dialogues']}/{s['n_total']}")
    for p in report["persona_breakdown"]:
        print(f"  {p['persona_id']:16s} {p['final_score']:6}  critical={p['critical_pass_rate']}  轮数={p['n_turns']}")
    from collections import Counter
    overall = Counter()
    for r in report["per_dialogue_results"]:
        overall.update(v["verdict"] for v in r.get("verdict_details", []))
    print(f"verdict 汇总: {dict(overall)}  | error={overall.get('error',0)}")
    print(f"报告已存: {out_path}")
    print("BUILD_OFFICIAL_DEMO_DONE")


if __name__ == "__main__":
    main()
