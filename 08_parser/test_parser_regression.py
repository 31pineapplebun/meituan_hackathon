"""
Parser 回归测试 - 确保解析能覆盖多种 markdown 格式

测试用例:
- V1-V6 (我们的): 数字编号 Constraints + → 分隔 FAQ
- 官方 sample 1 (飞毛腿): 短横线 Constraints + : 分隔 FAQ
- 官方 sample 2 (课程发布): 多级 Step 流程 + 短横线 Constraints
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from parser import parse_instruction, extract_constraints_raw, extract_faq_raw


PROJECT_ROOT = Path(__file__).parent.parent


def test_v1_v6_regression():
    """确保 V1-V6 没有解析回归"""
    expected = {
        "V1": {"constraints_min": 16, "faq_min": 3, "steps_min": 4},
        "V2": {"constraints_min": 16, "faq_min": 3, "steps_min": 4},
        "V3": {"constraints_min": 19, "faq_min": 5, "steps_min": 4},
        "V4": {"constraints_min": 26, "faq_min": 6, "steps_min": 7},
        "V5": {"constraints_min": 25, "faq_min": 6, "steps_min": 7},
        "V6": {"constraints_min": 36, "faq_min": 8, "steps_min": 7},
    }
    
    print("\n=== V1-V6 回归测试 ===")
    passed = 0
    for v, exp in expected.items():
        path = PROJECT_ROOT / "03_examples" / "variants" / f"{v}.md"
        if not path.exists():
            print(f"  ⚠️ {v}: 文件不存在")
            continue
        try:
            md_text = path.read_text(encoding="utf-8")
            d_obj = parse_instruction(md_text, v, mock=True)
            # ParsedInstruction 是 dataclass
            from dataclasses import asdict
            d = asdict(d_obj) if hasattr(d_obj, "__dataclass_fields__") else d_obj
            n_constraints = len(d.get("atomic_constraints", []))
            n_faq = len(d.get("faq_items", []))
            n_steps = sum(1 for c in d.get("atomic_constraints", []) 
                          if c.get("verifier") == "state_tracker")
            
            ok = (n_constraints >= exp["constraints_min"] 
                  and n_faq >= exp["faq_min"]
                  and n_steps >= exp["steps_min"])
            
            mark = "✓" if ok else "✗"
            print(f"  {mark} {v}: 约束={n_constraints} (期望≥{exp['constraints_min']}), "
                  f"FAQ={n_faq} (≥{exp['faq_min']}), state_tracker={n_steps} (≥{exp['steps_min']})")
            if ok:
                passed += 1
        except Exception as e:
            print(f"  ✗ {v}: 解析失败 - {e}")
    
    return passed, len(expected)


def test_official_sample_1():
    """官方 sample 1 - 飞毛腿合同"""
    # 这是从 docx 提取的官方原文
    sample_md = """# Role

你是美团外卖骑手的站长。

# Task

致电"飞毛腿"骑手，通知他们今天合同已成功签署，并提醒他们完成配送任务。

# Opening Line

你好，请问是${rider_name}吗？我是站长。我看到你已报名飞毛腿。请记住，午餐和晚餐高峰期需要上线。

# Call Flow

1. 告知骑手今天飞毛腿合同已生效，并询问他们是否可以开始配送。
2. 说明单日飞毛腿合同需要**连续 Y 天**完成配送；否则合同将受到影响。
3. 尽量挽留不想配送的骑手，鼓励能配送的骑手，并提醒他们注意安全。
4. 说明飞毛腿报名是按排名进行的，并非站长干预。

# Knowledge Points (FAQ)

- 目前，许多骑手正在申请飞毛腿。如果你无法连续配送 **Y 天**，你的名额可能会被他人占用。
- 单日合同：在生效当天必须完成 **X 单**，否则合同及派单可能受到影响。
- 多日合同：每天必须完成 **Y 单**，否则后续合同及派单可能受到影响。
- 如需退出飞毛腿，必须在前一天 **Z 点之前**在 App 的"飞毛腿报名"中取消；次日生效。
- 连续完成 **W 天**多日合同，且每天完成 **Y 单**，将获得额外奖励。

# Constraints

- 遵循对话流程和常见问题解答。
- 如被问及超出职责范围的问题，回复："我向同事确认后再回电给你。我现在能回答的先回答。"
- 保持语气随意，像打电话一样自然。
- 每次回复控制在**约 30 个字以内**。
- 避免重复回复；如需重申，请换种方式礼貌表达。
- 如果骑手坚持确实无法配送，安慰他们后挂断电话。
"""
    
    print("\n=== 官方 sample 1 (飞毛腿) 测试 ===")
    
    # 测 Constraints 抽取
    constraints = extract_constraints_raw(sample_md)
    print(f"  Constraints 数: {len(constraints)} (期望 ≥ 6)")
    assert len(constraints) >= 6, f"应解析出 ≥6 条 Constraints, 实际 {len(constraints)}"
    
    # 测 FAQ 抽取
    faqs = extract_faq_raw(sample_md)
    print(f"  FAQ 数: {len(faqs)} (期望 ≥ 5)")
    assert len(faqs) >= 5, f"应解析出 ≥5 条 FAQ, 实际 {len(faqs)}"
    
    # 检查关键 FAQ 内容
    faq_text = "\n".join(f"{q}|{a}" for q, a in faqs)
    if "单日合同" in faq_text and "X 单" in faq_text:
        print(f"  ✓ FAQ 含'单日合同/X 单'关键字段")
    
    # 测完整解析(因 parse_instruction_file 需要文件路径,这里只测核心抽取函数)
    print(f"  ✓ 官方 sample 1 通过")
    return 1, 1


def test_official_sample_2():
    """官方 sample 2 - 课程发布平台升级"""
    sample_md = """# Role: Customer Support Specialist for Course Publishing Platform

## Task: 告知机构客户，课程发布页面将新增"标准直播"和"低延迟直播"两个独立选项。

# Constraints:

- 每次回复极简——最多15-20个字
- 使用简短、自然的口语化表达，符合电话沟通风格
- 频繁给商家发言和提问的机会
- 若对话被打断，使用简短过渡语
- 不说"好的"、"哈哈"、"嘿嘿"等语气词
- 不能承诺给商家折扣券或优惠券
- 若老板说忙，说"就1分钟，保证简短"后继续简短说明
- 若商家说在开车，礼貌说"那我稍后再打"后挂断

# Opening Line: 您好，请问您是贵培训机构的负责人吗？

# Conversation Flow:

## Step 1: 身份确认
## Step 2: 确认是否知情
## Step 3: 传达升级内容
## Step 4: 确认前端是否可见
## Step 5: 检查学员端费用
## Step 6: 企业微信添加
## Step 7: 结束通话
"""
    
    print("\n=== 官方 sample 2 (课程发布) 测试 ===")
    
    # 测 Constraints 抽取(短横线格式)
    constraints = extract_constraints_raw(sample_md)
    print(f"  Constraints 数: {len(constraints)} (期望 ≥ 8)")
    assert len(constraints) >= 8, f"应解析出 ≥8 条 Constraints, 实际 {len(constraints)}"
    
    # 检查具体内容
    text = "\n".join(constraints)
    checks = [
        ("回复极简", "字数约束"),
        ("好的", "禁用词"),
        ("折扣券", "禁承诺"),
        ("开车", "条件挂断"),
    ]
    for kw, name in checks:
        if kw in text:
            print(f"  ✓ 含 '{name}' 约束")
        else:
            print(f"  ✗ 缺 '{name}' 约束")
    
    print(f"  ✓ 官方 sample 2 通过")
    return 1, 1


def main():
    """跑全套回归 + 官方 sample 测试"""
    print("=" * 60)
    print("Parser 回归测试 + 官方兼容性测试")
    print("=" * 60)
    
    total_passed = 0
    total_count = 0
    
    # 1. V1-V6 回归
    p, n = test_v1_v6_regression()
    total_passed += p
    total_count += n
    
    # 2. 官方 sample 1
    try:
        p, n = test_official_sample_1()
        total_passed += p
        total_count += n
    except AssertionError as e:
        print(f"  ✗ 官方 sample 1 失败: {e}")
        total_count += 1
    
    # 3. 官方 sample 2
    try:
        p, n = test_official_sample_2()
        total_passed += p
        total_count += n
    except AssertionError as e:
        print(f"  ✗ 官方 sample 2 失败: {e}")
        total_count += 1
    
    print()
    print("=" * 60)
    if total_passed == total_count:
        print(f"✅ 全部通过 ({total_passed}/{total_count})")
        return 0
    else:
        print(f"❌ {total_passed}/{total_count} 通过, {total_count - total_passed} 失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
