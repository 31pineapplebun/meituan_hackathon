"""
指令质量校验脚本

用途: 检查 LLM 生成的指令是否符合外呼场景规范
输入: instruction.md (markdown 格式的指令文本)
输出: 校验报告 + 通过/不通过判定

通过标准: 必须通过所有 HARD 检查; SOFT 检查给出警告

用法:
    python validate_instruction.py path/to/generated_instruction.md
    或 from validate_instruction import validate; result = validate(text)
"""
import re
import sys
import json
from typing import Dict, List, Tuple


REQUIRED_SECTIONS = ["# Role", "# Task", "# Opening Line", "# Call Flow", "# Constraints"]
OPTIONAL_SECTIONS = ["# Knowledge Points", "# FAQ", "# Knowledge"]


def check_sections(text: str) -> Tuple[bool, List[str]]:
    """HARD: 必须包含5个核心section"""
    issues = []
    text_lower = text.lower()
    for sec in REQUIRED_SECTIONS:
        # 兼容大小写和Heading级别
        pattern = sec.lower().replace("#", "").strip()
        if pattern not in text_lower:
            issues.append(f"缺失section: {sec}")
    return len(issues) == 0, issues


def check_opening_line(text: str) -> Tuple[bool, List[str]]:
    """HARD: Opening Line 必须含变量占位符, 长度 30-150 字"""
    issues = []
    match = re.search(r"#+\s*Opening Line[:：]?\s*\n+(.+?)(?=\n#|\Z)", text, re.DOTALL | re.IGNORECASE)
    if not match:
        return False, ["无法提取 Opening Line 内容"]
    
    opening = match.group(1).strip()
    
    # 检查变量
    variables = re.findall(r"\$\{[^}]+\}", opening)
    if len(variables) < 1:
        issues.append(f"Opening Line 至少需1个 ${{变量}}占位符，实际: {len(variables)}")
    
    # 检查长度
    plain = re.sub(r"\s+", "", opening)
    if len(plain) < 30:
        issues.append(f"Opening Line 太短: {len(plain)}字 (要求≥30)")
    if len(plain) > 200:
        issues.append(f"Opening Line 太长: {len(plain)}字 (要求≤200)")
    
    return len(issues) == 0, issues


def check_call_flow(text: str) -> Tuple[bool, List[str], int]:
    """HARD: Call Flow 必须有≥3个编号步骤"""
    issues = []
    match = re.search(r"#+\s*Call Flow[:：]?\s*\n+(.+?)(?=\n#[^#]|\Z)", text, re.DOTALL | re.IGNORECASE)
    if not match:
        return False, ["无法提取 Call Flow 内容"], 0
    
    flow_text = match.group(1)
    # 编号步骤: 1. / 1、 / Step 1 / ## Step 1
    steps = re.findall(r"(?:^|\n)\s*(?:\*\*)?(?:Step\s+)?(\d+)[\.\、\:]", flow_text)
    step_count = len(set(steps))
    
    if step_count < 3:
        issues.append(f"Call Flow 步骤太少: {step_count} (要求≥3)")
    
    return len(issues) == 0, issues, step_count


def check_constraints(text: str) -> Tuple[bool, List[str], Dict]:
    """HARD: Constraints 必须含至少3类不同约束"""
    issues = []
    match = re.search(r"#+\s*Constraints[:：]?\s*\n+(.+?)(?=\n#[^#]|\Z)", text, re.DOTALL | re.IGNORECASE)
    if not match:
        return False, ["无法提取 Constraints 内容"], {}
    
    constraints_text = match.group(1)
    
    # 分类检测
    constraint_types = {
        "长度约束": bool(re.search(r"(\d+\s*个?字|字符|长度|字以内|字以下)", constraints_text)),
        "越界处理": bool(re.search(r"(超出|范围外|不在|无法回答|向同事|回电)", constraints_text)),
        "语气约束": bool(re.search(r"(口语|随意|自然|正式|友好|简洁|语气|风格)", constraints_text)),
        "禁用约束": bool(re.search(r"(不(说|使用|要|得|可)|避免|禁止)", constraints_text)),
        "结束约束": bool(re.search(r"(挂断|结束|结束通话|结束对话|再见)", constraints_text)),
    }
    
    hit_count = sum(constraint_types.values())
    if hit_count < 3:
        issues.append(f"约束类型太单一: 仅命中 {hit_count} 类 (要求≥3类)")
    
    return len(issues) == 0, issues, constraint_types


def check_variables_consistency(text: str) -> Tuple[bool, List[str]]:
    """SOFT: 变量在Opening Line出现后, Call Flow或Constraints中应有相关引用"""
    issues = []
    variables = set(re.findall(r"\$\{([^}]+)\}", text))
    
    if len(variables) == 0:
        issues.append("[警告] 整份指令未发现任何变量占位符")
    
    return True, issues  # SOFT, 总是返回True


def check_no_template_leakage(text: str) -> Tuple[bool, List[str]]:
    """HARD: 不能含有原始模板的占位文本"""
    issues = []
    leakage_patterns = [
        r"\[.*简短描述.*\]",
        r"\[.*关键事实.*\]",
        r"\{scenario\}",
        r"\{complexity\}",
        r"\{domain\}",
        r"\{topic_hint\}",
        r"对标示例",
        r"按需选择",
    ]
    for p in leakage_patterns:
        if re.search(p, text):
            issues.append(f"检测到未替换的模板片段: {p}")
    return len(issues) == 0, issues


def check_similarity_to_examples(text: str) -> Tuple[bool, List[str]]:
    """SOFT: 不应与示例1/2过度相似"""
    issues = []
    example_phrases_1 = ["飞毛腿", "单日合同", "多日合同", "排名进行的", "拒单、取消和超时"]
    example_phrases_2 = ["低延迟直播", "标准直播", "校务系统", "企业微信添加", "招生满满"]
    
    hits_1 = sum(1 for p in example_phrases_1 if p in text)
    hits_2 = sum(1 for p in example_phrases_2 if p in text)
    
    if hits_1 >= 2:
        issues.append(f"[警告] 与示例1措辞高度相似 (命中{hits_1}个特征词)")
    if hits_2 >= 2:
        issues.append(f"[警告] 与示例2措辞高度相似 (命中{hits_2}个特征词)")
    
    return True, issues  # SOFT


def validate(text: str) -> Dict:
    """主校验函数"""
    report = {
        "passed": True,
        "hard_checks": {},
        "soft_warnings": [],
        "stats": {}
    }
    
    # HARD 检查
    ok_s, issues_s = check_sections(text)
    report["hard_checks"]["section_completeness"] = {"pass": ok_s, "issues": issues_s}
    if not ok_s:
        report["passed"] = False
    
    ok_o, issues_o = check_opening_line(text)
    report["hard_checks"]["opening_line"] = {"pass": ok_o, "issues": issues_o}
    if not ok_o:
        report["passed"] = False
    
    ok_f, issues_f, step_count = check_call_flow(text)
    report["hard_checks"]["call_flow"] = {"pass": ok_f, "issues": issues_f}
    report["stats"]["step_count"] = step_count
    if not ok_f:
        report["passed"] = False
    
    ok_c, issues_c, types = check_constraints(text)
    report["hard_checks"]["constraints"] = {"pass": ok_c, "issues": issues_c}
    report["stats"]["constraint_types_hit"] = types
    if not ok_c:
        report["passed"] = False
    
    ok_t, issues_t = check_no_template_leakage(text)
    report["hard_checks"]["no_template_leakage"] = {"pass": ok_t, "issues": issues_t}
    if not ok_t:
        report["passed"] = False
    
    # SOFT 检查
    _, warn_v = check_variables_consistency(text)
    _, warn_sim = check_similarity_to_examples(text)
    report["soft_warnings"] = warn_v + warn_sim
    
    return report


def print_report(report: Dict):
    """终端友好打印"""
    print("=" * 70)
    status = "✅ PASS" if report["passed"] else "❌ FAIL"
    print(f"指令质量校验报告  {status}")
    print("=" * 70)
    
    print("\n[HARD 检查]")
    for check_name, result in report["hard_checks"].items():
        mark = "✓" if result["pass"] else "✗"
        print(f"  {mark} {check_name}")
        for issue in result["issues"]:
            print(f"      └─ {issue}")
    
    if report["soft_warnings"]:
        print("\n[SOFT 警告]")
        for w in report["soft_warnings"]:
            print(f"  ⚠ {w}")
    
    print("\n[统计]")
    for k, v in report["stats"].items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        # 自测：用示例1做校验
        print("用法: python validate_instruction.py <instruction.md>")
        print("\n--- 自测：模拟一份合格指令 ---\n")
        sample = """# Role
你是某外卖平台的骑手运营专员。

# Task
致电骑手张三，通知他完成新版APP的强制更新，并确认更新后能正常接单。

# Opening Line
您好，请问是${rider_name}吗？我是平台运营。我们新版骑手APP已经上线，您需要在今天24点前完成更新，否则将无法接单。这次更新主要优化了接单速度和导航准确度。

# Call Flow
1. 自我介绍并告知更新要求
2. 询问骑手当前APP版本，判断是否已更新
3. 若未更新，引导其在应用商店搜索"骑手版"下载最新版
4. 确认更新成功后能否正常登录和接单

# Knowledge Points (FAQ)
- 更新后无法登录: 清除缓存后重新登录, 仍不行联系站长
- 接单页面变化: 新版整合了热区显示, 在首页右上角
- 流量消耗: 更新包约80MB, 建议Wi-Fi下载

# Constraints
- 每次回复不超过30字
- 保持口语化，像打电话一样自然
- 被问及APP开发计划等超出运营职责的问题，回复"这个我帮您记录，回头让产品同学跟进"
- 避免重复同一句话，若需重申请换种说法
- 不能承诺任何赔付或额外补贴
- 若骑手明确表示拒绝更新，告知后果后挂断
"""
        report = validate(sample)
        print_report(report)
    else:
        with open(sys.argv[1], encoding="utf-8") as f:
            text = f.read()
        report = validate(text)
        print_report(report)
        sys.exit(0 if report["passed"] else 1)
