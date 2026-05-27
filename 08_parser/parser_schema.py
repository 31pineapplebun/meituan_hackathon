"""指令解析器输出 Schema (dataclass + 手写校验)

设计选择: 不用 pydantic, 用标准库 dataclass。
原因: 1) 减少依赖 2) 校验逻辑透明可读 3) 部署友好

解析器输入: 指令 Markdown 文本
解析器输出: 严格符合此 Schema 的 JSON
"""
import re
from dataclasses import dataclass, field, asdict
from typing import List


# --- 评分维度枚举 ---
VALID_DIMENSIONS = {
    "D1_flow_compliance",
    "D2_task_completion",
    "D3_constraint_compliance",
    "D4_knowledge_accuracy",
    "D5_dialogue_quality",
}

# --- Verifier 类型枚举 ---
VALID_VERIFIERS = {
    "rule",
    "rule_pattern",
    "state_tracker",
    "llm_judge",
    "llm_extract_then_rule",
}


class ValidationError(Exception):
    """自定义校验异常"""
    pass


@dataclass
class AtomicConstraint:
    """单条原子约束"""
    id: str
    name: str
    scoring_dimension: str
    verifier: str
    source_text: str
    is_critical: bool = False
    weight: int = 2
    
    def validate(self):
        errors = []
        # ID 格式
        if not re.match(r"^[A-Z][A-Z0-9_]*_C\d{2,3}$", self.id):
            errors.append(f"约束ID格式不对: {self.id}, 应为 {{INSTR}}_C{{编号}}")
        # name 长度
        if not self.name or len(self.name) > 60:
            errors.append(f"约束名称长度异常 ({len(self.name)}字): {self.name}")
        # 维度合法
        if self.scoring_dimension not in VALID_DIMENSIONS:
            errors.append(f"维度不在 {VALID_DIMENSIONS}: {self.scoring_dimension}")
        # verifier 合法
        if self.verifier not in VALID_VERIFIERS:
            errors.append(f"verifier不在 {VALID_VERIFIERS}: {self.verifier}")
        # 权重范围
        if not 1 <= self.weight <= 5:
            errors.append(f"权重应在1-5: {self.weight}")
        # source_text 非空
        if not self.source_text or not self.source_text.strip():
            errors.append(f"source_text 不能为空: {self.id}")
        return errors


@dataclass
class FAQItem:
    """FAQ 知识点"""
    id: str
    question_intent: str
    answer_template: str = ""
    key_facts: List[str] = field(default_factory=list)
    
    def validate(self):
        errors = []
        if not re.match(r"^[A-Z][A-Z0-9_]*_FAQ\d{1,3}$", self.id):
            errors.append(f"FAQ ID 格式不对: {self.id}")
        if not self.question_intent:
            errors.append(f"FAQ {self.id} 缺少 question_intent")
        return errors


@dataclass
class FlowStep:
    """流程步骤 (简化版)"""
    step_id: str
    label: str
    purpose: str = ""
    is_branch: bool = False
    
    def validate(self):
        errors = []
        if not self.step_id:
            errors.append("step_id 不能为空")
        if not self.label:
            errors.append(f"step {self.step_id} 缺少 label")
        return errors


@dataclass
class InstructionMeta:
    """指令元数据"""
    instruction_id: str
    instruction_name: str
    role: str = ""
    task: str = ""
    opening_line: str = ""
    variables: List[str] = field(default_factory=list)
    
    def validate(self):
        errors = []
        if not self.instruction_id:
            errors.append("instruction_id 不能为空")
        if not self.instruction_name:
            errors.append("instruction_name 不能为空")
        return errors


@dataclass
class ParsedInstruction:
    """完整解析结果"""
    meta: InstructionMeta
    atomic_constraints: List[AtomicConstraint]
    faq_items: List[FAQItem] = field(default_factory=list)
    flow_steps: List[FlowStep] = field(default_factory=list)
    
    def validate(self):
        """完整校验,返回所有错误清单"""
        errors = []
        
        # 子组件校验
        errors.extend(self.meta.validate())
        for c in self.atomic_constraints:
            errors.extend(c.validate())
        for f in self.faq_items:
            errors.extend(f.validate())
        for s in self.flow_steps:
            errors.extend(s.validate())
        
        # 全局规则1: 约束数 >= 3
        if len(self.atomic_constraints) < 3:
            errors.append(f"约束数过少 ({len(self.atomic_constraints)}),至少3条")
        
        # 全局规则2: 必须覆盖关键维度
        dims = {c.scoring_dimension for c in self.atomic_constraints}
        required = {"D1_flow_compliance", "D3_constraint_compliance"}
        missing = required - dims
        if missing:
            errors.append(f"缺少必要维度: {missing}")
        
        # 全局规则3: 约束 ID 不重复
        ids = [c.id for c in self.atomic_constraints]
        dupes = [x for x in set(ids) if ids.count(x) > 1]
        if dupes:
            errors.append(f"约束ID重复: {dupes}")
        
        return errors
    
    def to_dict(self):
        return asdict(self)


if __name__ == "__main__":
    # 测试 schema
    sample = ParsedInstruction(
        meta=InstructionMeta(
            instruction_id="V1",
            instruction_name="测试指令",
            role="测试角色",
            task="测试任务",
            variables=["rider_name"]
        ),
        atomic_constraints=[
            AtomicConstraint(
                id="V1_C01",
                name="字数<=30",
                scoring_dimension="D3_constraint_compliance",
                verifier="rule",
                is_critical=False,
                weight=2,
                source_text="每次回复30字以内"
            ),
            AtomicConstraint(
                id="V1_C02",
                name="Step1 告知培训",
                scoring_dimension="D1_flow_compliance",
                verifier="state_tracker",
                is_critical=True,
                weight=3,
                source_text="Step 1 告知培训时间地点"
            ),
            AtomicConstraint(
                id="V1_C03",
                name="禁用'好的'",
                scoring_dimension="D3_constraint_compliance",
                verifier="rule_pattern",
                is_critical=False,
                weight=3,
                source_text="不说'好的'等语气词"
            ),
        ]
    )
    
    errors = sample.validate()
    if errors:
        print(f"❌ {len(errors)} 个校验错误:")
        for e in errors:
            print(f"  - {e}")
    else:
        print(f"✓ Schema 验证通过: {len(sample.atomic_constraints)} 条约束")
    
    # 测试错误捕获
    print("\n--- 故意错误测试 ---")
    bad = ParsedInstruction(
        meta=InstructionMeta(instruction_id="V1", instruction_name="bad"),
        atomic_constraints=[
            AtomicConstraint(
                id="bad_id",  # 故意错的ID
                name="x" * 100,  # 故意太长
                scoring_dimension="bad_dim",  # 故意错的维度
                verifier="bad_verifier",  # 故意错的verifier
                weight=99,  # 故意超界
                source_text=""  # 故意空
            ),
        ]
    )
    bad_errors = bad.validate()
    print(f"故意错的校验捕获 {len(bad_errors)} 个错误:")
    for e in bad_errors[:5]:
        print(f"  - {e}")

