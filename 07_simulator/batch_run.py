"""
批量运行模拟器 - 一次跑多个 persona × 多个指令

用法:
    # 最小测试: 2 条指令 × 2 persona × 1 通 = 4 通(mock)
    python batch_run.py --quick_test --mock
    
    # Day 4 标准批量: 4 条指令(主推) × 4 persona × 2 通 = 32 通
    python batch_run.py --instructions V1,V2,V3,V4 --personas all --num_per_combo 2
    
    # 自定义
    python batch_run.py --instructions V1,V4 --personas cooperative,refuse_persistent \\
                        --num_per_combo 3 --mock
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path


# 默认配置
# 智能查找指令目录: 适配 day4/ 和 project_v1/07_simulator/ 两种位置
_HERE = Path(__file__).resolve().parent
_CANDIDATES = [
    _HERE.parent / "03_examples" / "variants",
    _HERE.parent.parent / "project_v1" / "03_examples" / "variants",
    _HERE.parent / "project_v1" / "03_examples" / "variants",
    Path("/home/claude/project_v1/03_examples/variants"),  # 绝对路径兜底
]
DEFAULT_INSTRUCTIONS_DIR = next((p for p in _CANDIDATES if p.exists()), _CANDIDATES[0])

_EX1_CANDIDATES = [
    _HERE.parent / "03_examples" / "example_1",
    _HERE.parent.parent / "project_v1" / "03_examples" / "example_1",
    _HERE.parent / "project_v1" / "03_examples" / "example_1",
    Path("/home/claude/project_v1/03_examples/example_1"),
]
DEFAULT_EXAMPLE1_PATH = next((p for p in _EX1_CANDIDATES if p.exists()), _EX1_CANDIDATES[0])

SIMULATOR_PATH = _HERE / "simulator_v2.py"
if not SIMULATOR_PATH.exists():
    SIMULATOR_PATH = _HERE / "simple_simulator.py"  # fallback to v1 if v2 not present

OUTPUT_DIR = _HERE / "dialogues_output"

ALL_PERSONAS = ["cooperative", "refuse_persistent", "out_of_scope", "interruption"]


def resolve_instruction(name: str) -> Path:
    """根据名字找指令文件"""
    # 先在 variants/ 找
    p = DEFAULT_INSTRUCTIONS_DIR / f"{name}.md"
    if p.exists():
        return p
    
    # 再在 example_1 找
    p = DEFAULT_EXAMPLE1_PATH / f"{name}.md"
    if p.exists():
        return p
    
    raise FileNotFoundError(f"找不到指令: {name}.md (在 variants/ 和 example_1/ 都没有)")


def run_batch(instructions, personas, num_per_combo, mock, tested_model, user_model):
    """执行批量任务"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    total_combos = len(instructions) * len(personas)
    total_dialogues = total_combos * num_per_combo
    
    print("=" * 70)
    print(f"批量任务计划")
    print("=" * 70)
    print(f"  指令数: {len(instructions)} ({', '.join(instructions)})")
    print(f"  Persona 数: {len(personas)} ({', '.join(personas)})")
    print(f"  每组合通数: {num_per_combo}")
    print(f"  总组合数: {total_combos}")
    print(f"  总对话数: {total_dialogues}")
    print(f"  模式: {'MOCK(零成本)' if mock else 'LIVE(真实API)'}")
    print(f"  被测模型: {tested_model}")
    print(f"  用户模型: {user_model}")
    print(f"  输出目录: {OUTPUT_DIR}")
    
    if not mock:
        # 估算成本
        avg_token_per_dialogue = 3000  # 粗略估算
        total_tokens = total_dialogues * avg_token_per_dialogue * 2  # x2 for assistant+user
        
        # 不同模型的成本 (单位: USD per M tokens, 输入输出粗均)
        cost_table = {
            "gpt-4o-mini": 0.5,
            "gpt-4o": 5.0,
            "deepseek-v4-flash": 0.20,    # 折后约 ~0.2 USD/M
            "deepseek-v4-pro": 0.85,      # 折后约 ~0.85 USD/M (输入0.42+输出0.83平均)
            "claude-3-5-sonnet": 6.0,
        }
        # 找匹配
        cost_per_M = 1.0  # 默认
        for k, v in cost_table.items():
            if k in tested_model.lower():
                cost_per_M = v
                break
        
        est_cost = total_tokens / 1_000_000 * cost_per_M
        print(f"\n  ⚠️ 预估成本: ${est_cost:.2f}")
        print(f"     基于 {total_dialogues} 通 × 6000 token × ${cost_per_M}/M ({tested_model})")
        
        ans = input("\n  确认开始? [y/N]: ").strip().lower()
        if ans != "y":
            print("已取消")
            return
    
    # 执行
    print(f"\n开始执行...\n")
    t_start = time.time()
    success = 0
    failed = 0
    
    for idx, instr_name in enumerate(instructions, 1):
        try:
            instr_path = resolve_instruction(instr_name)
        except FileNotFoundError as e:
            print(f"❌ 指令 {instr_name}: {e}")
            failed += len(personas) * num_per_combo
            continue
        
        for persona in personas:
            output_file = OUTPUT_DIR / f"{instr_name}_{persona}.jsonl"
            
            print(f"\n[{idx}/{len(instructions)}] {instr_name} × {persona} → {output_file.name}")
            print("-" * 70)
            
            cmd = [
                sys.executable, str(SIMULATOR_PATH),
                "--instruction", str(instr_path),
                "--persona", persona,
                "--tested_model", tested_model,
                "--user_model", user_model,
                "--num_dialogues", str(num_per_combo),
                "--output", str(output_file),
            ]
            if mock:
                cmd.append("--mock")
            
            try:
                result = subprocess.run(cmd, capture_output=False)
                if result.returncode == 0:
                    success += num_per_combo
                else:
                    failed += num_per_combo
            except KeyboardInterrupt:
                print("\n用户中断")
                break
            except Exception as e:
                print(f"❌ 失败: {e}")
                failed += num_per_combo
    
    elapsed = time.time() - t_start
    print("\n" + "=" * 70)
    print(f"批量完成")
    print("=" * 70)
    print(f"  耗时: {elapsed:.1f}s")
    print(f"  成功: {success} 通")
    print(f"  失败: {failed} 通")
    print(f"  输出: {OUTPUT_DIR}")
    
    # 汇总所有文件到一个 jsonl
    all_path = OUTPUT_DIR / "all_dialogues.jsonl"
    with open(all_path, "w", encoding="utf-8") as fout:
        for f in sorted(OUTPUT_DIR.glob("*.jsonl")):
            if f.name == all_path.name:
                continue
            with open(f, encoding="utf-8") as fin:
                fout.write(fin.read())
    
    # 统计总通数
    with open(all_path, encoding="utf-8") as f:
        total = sum(1 for _ in f)
    print(f"  汇总: {all_path} ({total} 通对话)")


def main():
    parser = argparse.ArgumentParser(description="批量运行模拟器")
    parser.add_argument("--instructions", help="逗号分隔的指令名 如 V1,V2,V3")
    parser.add_argument("--personas", help="逗号分隔的 persona 或 'all'", default="cooperative")
    parser.add_argument("--num_per_combo", type=int, default=1, help="每个组合跑几通")
    parser.add_argument("--tested_model", default="gpt-4o-mini")
    parser.add_argument("--user_model", default="gpt-4o-mini")
    parser.add_argument("--mock", action="store_true", help="Mock模式")
    parser.add_argument("--quick_test", action="store_true",
                        help="快速测试: V1+V4 × cooperative+refuse_persistent × 1通")
    args = parser.parse_args()
    
    if args.quick_test:
        instructions = ["V1", "V4"]
        personas = ["cooperative", "refuse_persistent"]
        num = 1
    else:
        if not args.instructions:
            print("错误: 需要 --instructions 或 --quick_test")
            sys.exit(1)
        instructions = args.instructions.split(",")
        if args.personas == "all":
            personas = ALL_PERSONAS
        else:
            personas = args.personas.split(",")
        num = args.num_per_combo
    
    run_batch(
        instructions=instructions,
        personas=personas,
        num_per_combo=num,
        mock=args.mock,
        tested_model=args.tested_model,
        user_model=args.user_model,
    )


if __name__ == "__main__":
    main()
