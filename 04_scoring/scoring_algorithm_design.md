# Day 2 评分算法设计文档

> **版本**：v2.0（P3方案，已通过4/4场景验证）
> **依据**：example_2_atomic_v2.json + 5 维度方案
> **目标**：把 0/1 的约束判定结果转换成 0-100 的综合分数
> **变更历史**：
> - v1.0: B+D 组合方案，红线翻车场景验证失败（69.41 vs 预期≤40）
> - v2.0: 采纳 P3 方案（P1调严Gating + P2红线即死），4/4 场景全部验证通过

---

## 1. 核心设计原则

### 1.1 直播原话约束

一招老师明确说：
> "我们的结果是可以量化的，而不是说直接给出一个 0、1 的分数，还是需要可能给出一个 0 到 100 这么一个分数"
> "让我们后面的优化的方向是什么"

→ 设计必须满足：**0-100 + 可解释 + 能指出优化方向**

### 1.2 设计哲学

| 原则 | 含义 |
|---|---|
| 透明 | 每个分数都能拆解到具体约束，不能是黑箱 |
| 健壮 | 单点失败不引爆全局分数，但红线必须有惩罚 |
| 平滑 | 评分应该有梯度，不能出现 "92 vs 91 区分不出来" 的情况 |
| 可视化 | 5 维度直接对应雷达图，答辩 PPT 视觉化 |

---

## 2. 算法总览（P3 方案：D + P1 + P2 三层防御）

```
总分 = D 方案（5维度加权平均）原始分
        ↓
      P1 调严 Critical Gating（critical 通过率作为上限）
        ↓
      P2 红线即死机制（red_line 违规直接钳制 ≤ 40）
        ↓
      取两层钳制的较严者作为最终上限
```

### 2.1 数学表达

```
Step 1: 维度内得分计算（D方案）
  dim_score(D_i) = (Σ pass_k × w_k) / (Σ w_k) × 100
                   k ∈ 该维度内所有约束

Step 2: 维度加权汇总
  raw_score = Σ dim_score(D_i) × dim_weight(D_i)
             = D1×0.25 + D2×0.25 + D3×0.20 + D4×0.15 + D5×0.15

Step 3: P1 调严 Critical Gating
  critical_pass_rate = critical约束通过数 / critical约束总数

  if critical_pass_rate >= 1.0:   critical_ceiling = 100
  elif critical_pass_rate >= 0.9: critical_ceiling = 85
  elif critical_pass_rate >= 0.7: critical_ceiling = 65
  elif critical_pass_rate >= 0.5: critical_ceiling = 45
  else:                           critical_ceiling = 30

Step 4: P2 红线即死
  red_line_violations = 所有 is_red_line=True 且失败的约束

  if 任意红线违规:  red_line_ceiling = 40
  else:           red_line_ceiling = 100

Step 5: 取较严者
  ceiling = min(critical_ceiling, red_line_ceiling)
  final_score = min(raw_score, ceiling)
```

### 2.2 红线约束（red_line）定义

红线约束是**比 critical 更严格**的一类：违反就直接导致分数 ≤ 40。

**当前红线约束清单**（依据示例 2 业务场景）：

| 约束 ID | 名称 | 红线性质 |
|---|---|---|
| EX2_C09 | 禁止承诺折扣或优惠券 | 商业红线（违规承诺 = 商业损失） |
| EX2_C11 | 用户说开车时礼貌挂断 | 安全红线（不挂断 = 安全事故风险） |

**判定原则**：
- 必须是"违反就直接造成实际业务损害"的约束
- 数量应该极少（建议每条指令 1-3 条）
- 不是所有 critical 都是 red_line；red_line 一定是 critical 的子集

### 2.3 为什么用 P3 三层防御方案（演进路径）

**v1 方案问题**（B + D 组合）：
- D 维度加权可以摊薄单点红线违规
- B Critical Gating 阈值太宽松（70%→80分上限），无法捕捉"几条 critical 失败"的情况
- 红线翻车场景实际得 **69.41** vs 预期 ≤ 40，差距巨大

**v2 P3 方案的改进**：
| 防御层 | 作用 | 红线翻车场景效果 |
|---|---|---|
| D 维度加权 | 提供 0-100 细粒度分数 | raw_score = 69.41 |
| P1 调严 Gating | Critical 通过率作为上限 | critical 通过率 76.5% → 上限 65 |
| P2 红线即死 | red_line 违规直接 ≤ 40 | 触发，上限 40 |
| 最终钳制 | min(各层上限) | **final = min(69.41, 40) = 40** ✅ |

**三层防御的协同**：
- 普通失败 → D 方案扣分
- Critical 失败 → P1 钳制上限
- 红线失败 → P2 暴击上限到 40
- 任意一层都能独立工作，组合后覆盖所有失败模式

---

## 3. 维度内得分计算示例

以**维度 1 流程遵循度**为例（13 条约束）：

| 约束 | 通过 | 权重 |
|---|---|---|
| EX2_C13 Step1覆盖 | ✓ | 3 |
| EX2_C14 Step1分支 | ✓ | 3 |
| EX2_C15 Step2覆盖 | ✓ | 3 |
| EX2_C16 Step2分支 | ✗ | 3 |
| EX2_C17 Step3覆盖 | ✓ | 4 |
| EX2_C18 Step3.1子step | ✗ | 3 |
| EX2_C19 Step3.2子step | ✗ | 3 |
| EX2_C20 Step4询问方式 | ✓ | 4 |
| EX2_C21 Step4分支 | ✓ | 4 |
| EX2_C23 Step5覆盖 | ✓ | 3 |
| EX2_C24 Step5分支 | ✓ | 2 |
| EX2_C26 Step6覆盖 | ✓ | 2 |
| EX2_C27 Step6分支 | ✗ | 2 |

```
通过权重和 = 3+3+3+4+4+4+3+2+2 = 28
总权重和 = 3+3+3+3+4+3+3+4+4+3+2+2+2 = 39
D1 得分 = 28/39 × 100 ≈ 71.8
```

---

## 4. 完整计算示例：红线翻车场景（最能体现 P3 价值）

**场景**：模型承诺折扣（C09 失败）+ 用户开车未挂断（C11 失败）+ 多项其他约束失败。

### 4.1 维度得分

| 维度 | 内部通过情况 | 内部得分 | 权重 | 加权贡献 |
|---|---|---|---|---|
| D1 流程遵循度 | 部分失败 | 74.4 | 0.25 | 18.60 |
| D2 任务完成度 | 全通过 | 100.0 | 0.25 | 25.00 |
| D3 约束遵循度 | 多项失败 | 50.0 | 0.20 | 10.00 |
| D4 知识准确性 | 部分失败 | 45.5 | 0.15 | 6.83 |
| D5 对话质量 | 部分失败 | 60.0 | 0.15 | 9.00 |
| **raw_score** | | | | **69.41** |

### 4.2 三层钳制

```
Step 3 (P1): Critical 通过率 = 13/17 = 76.5%
  → critical_ceiling = 65

Step 4 (P2): 红线违规 = [EX2_C09, EX2_C11]
  → red_line_ceiling = 40

Step 5: ceiling = min(65, 40) = 40
  → final_score = min(69.41, 40) = 40
```

**P3 方案的关键价值**：单纯的 D 方案算出 69.41 分（语义上"勉强及格"），但实际上"承诺了折扣 + 不顾安全没挂断"的对话给 70 分是荒谬的。P3 通过红线即死把分数压到 40（明显不及格），符合业务直觉。

### 4.3 钳制原因的可解释性

报告会明确说明钳制原因：
```
ceiling_reason: "红线违规(2条): EX2_C09(禁止承诺折扣), EX2_C11(用户开车未挂断)"
```

这正是赛题要求的**可解释**——评委看一眼就知道为什么是 40 分而不是 70 分。

---

## 5. 算法实现伪代码

```python
def compute_score(constraint_results: List[ConstraintResult], 
                  taxonomy: dict) -> ScoreReport:
    """
    输入: 每条约束的判定结果 [{id, pass, scoring_dimension, weight, is_critical, ...}]
    输出: 0-100 总分 + 维度分 + 钳制原因 + 优化建议
    """
    
    # Step 1-2: D方案 维度内加权平均
    by_dim = group_by_dimension(constraint_results)
    dim_scores = {}
    for dim_id, results in by_dim.items():
        passed_weight = sum(r.weight for r in results if r.passed)
        total_weight = sum(r.weight for r in results)
        dim_scores[dim_id] = passed_weight / total_weight * 100 if total_weight > 0 else 0
    
    # Step 3: 维度加权汇总
    raw_score = sum(
        dim_scores[dim_id] * taxonomy["scoring_dimensions_definition"][dim_id]["weight"]
        for dim_id in dim_scores if dim_scores[dim_id] is not None
    )
    
    # Step 4 (P1): 调严 Critical Gating
    critical_results = [r for r in constraint_results if r.is_critical]
    critical_pass_rate = sum(1 for r in critical_results if r.passed) / len(critical_results) if critical_results else 1.0
    
    if critical_pass_rate >= 1.0:   critical_ceiling = 100
    elif critical_pass_rate >= 0.9: critical_ceiling = 85
    elif critical_pass_rate >= 0.7: critical_ceiling = 65
    elif critical_pass_rate >= 0.5: critical_ceiling = 45
    else:                           critical_ceiling = 30
    
    # Step 5 (P2): 红线即死
    red_line_violations = [r.id for r in constraint_results if r.is_red_line and not r.passed]
    red_line_ceiling = 40 if red_line_violations else 100
    
    # Step 6: 取较严者
    ceiling = min(critical_ceiling, red_line_ceiling)
    final_score = min(raw_score, ceiling)
    
    # Step 7: 生成优化方向（赛题硬要求）
    suggestions = generate_suggestions(constraint_results, dim_scores)
    
    return ScoreReport(
        final_score=final_score,
        raw_score=raw_score,
        ceiling=ceiling,
        ceiling_reason="红线违规" if red_line_violations else f"Critical通过率{critical_pass_rate*100:.1f}%",
        red_line_violations=red_line_violations,
        critical_pass_rate=critical_pass_rate,
        dim_scores=dim_scores,
        suggestions=suggestions
    )


def generate_suggestions(results, dim_scores):
    """生成优化方向（赛题硬要求："让我们后面的优化方向是什么"）"""
    suggestions = []
    
    # 优先级1: 红线违规（最高优先级）
    red_line_fails = [r for r in results if r.is_red_line and not r.passed]
    if red_line_fails:
        suggestions.append({
            "priority": "P0_RED_LINE",
            "msg": f"🚨 红线违规! 此类违规直接钳制分数≤40",
            "failed_constraints": [{"id": r.id, "name": r.name} for r in red_line_fails]
        })
    
    # 优先级2: 非红线的 critical 失败
    critical_fails = [r for r in results 
                       if r.is_critical and not r.passed and not r.is_red_line]
    if critical_fails:
        suggestions.append({
            "priority": "P0_CRITICAL",
            "msg": f"以下 {len(critical_fails)} 条关键约束失败",
            "failed_constraints": [{"id": r.id, "name": r.name} for r in critical_fails]
        })
    
    # 优先级3: 最低维度建议
    valid_dims = {k: v for k, v in dim_scores.items() if v is not None}
    if valid_dims:
        worst_dim = min(valid_dims, key=valid_dims.get)
        worst_score = valid_dims[worst_dim]
        if worst_score < 80:
            failed_in_worst = [r for r in results 
                                if r.scoring_dimension == worst_dim and not r.passed]
            if failed_in_worst:
                suggestions.append({
                    "priority": "P1",
                    "msg": f"维度【{worst_dim}】得分 {worst_score:.1f}/100 最低",
                    "failed_constraints": [{"id": r.id, "name": r.name} for r in failed_in_worst]
                })
    
    return suggestions
```

---

## 6. 候选方案对比说明

为答辩准备，我们设计时考虑了 5 个候选方案，最终选 P3：

| 方案 | 公式 | 优点 | 缺点 | 是否采纳 |
|---|---|---|---|---|
| A 纯线性加权 | `Σ(pass×w)/Σw × 100` | 简单透明 | 红线和细节混在一起，无惩罚 | ❌ |
| B Critical gating | 红线失败钳制上限 | 保护红线 | 阈值偏宽松 | 部分（被 P1 替代） |
| C 三级缩放相乘 | `L1 × L2 × L3` | 对齐 Meeseeks | 0 分爆炸风险，区分度差 | ❌ |
| D 维度均衡加权 | 5 维度各算 0-100，加权平均 | 可解释性最强、雷达图直接可视化 | 红线被摊薄 | ✅ 作为主体 |
| **P3 三层防御** | **D + P1调严Gating + P2红线即死** | **既细粒度又抓红线** | **设计稍复杂** | **✅ 最终采纳** |

**最终采纳：P3 三层防御**
- D 提供平滑、可解释、维度化的分数（雷达图视觉）
- P1 调严 Critical Gating（阈值 0.7→65 而非 0.7→80）
- P2 红线即死（red_line 违规直接钳制 ≤ 40）

### 6.1 验证数据（4 通伪场景）

| 场景 | 预期 | 实际 | 通过 |
|---|---|---|---|
| 理想对话（全通过） | ≥ 90 | 100 | ✅ |
| 中规中矩（7 失败，无 critical） | 75-87 | 86.86 | ✅ |
| 部分流程缺失（12 失败，5 critical） | 55-70 | 65 | ✅ |
| 红线翻车（12 失败，4 critical，2 red_line） | ≤ 40 | 40 | ✅ |

**4/4 全部在预期范围内，算法直觉对齐**。验证脚本：`scoring_validation_v2.py`

---

## 7. 答辩话术准备

### Q：你的 0-100 分怎么算的？为什么这样设计？

**A**：我们采用 **P3 三层防御方案**——维度加权 + Critical Gating + 红线即死。
- **第一层（D 维度加权）**：5 个维度对应业务关注点（流程遵循 25% + 任务完成 25% + 约束遵循 20% + 知识准确 15% + 对话质量 15%），每维度内部按约束权重加权平均得 0-100 分
- **第二层（P1 Critical Gating）**：关键约束通过率作为天花板（100%→100；≥90%→85；≥70%→65；≥50%→45；<50%→30）
- **第三层（P2 红线即死）**：red_line 约束（如承诺折扣、安全红线）违反，分数直接钳制 ≤ 40
- 最终分数 = min(raw_score, 第二层上限, 第三层上限)
- 4 通伪数据验证 4/4 通过，直觉对齐

### Q：为什么用 5 维度而不是 3 维度（L1/L2/L3）？

**A**：L1/L2/L3 是技术分类，业务方看不懂。
- 我们的 5 维度直接对应业务关注点：流程、任务、约束、知识、对话
- 评委和业务方一看就懂"这个模型流程走得不好"或"对话质量差"
- 同时与雷达图视觉化天然适配

### Q：红线约束（red_line）跟 critical 是什么关系？为什么要分两级？

**A**：red_line 是 critical 的子集，更严格的一级。
- critical：违反会显著扣分（通过 P1 钳制上限）
- red_line：违反就是任务严重失败（直接钳制 ≤ 40）
- 我们设计验证发现：纯 critical 机制下，承诺折扣场景能拿到 69 分，这与业务直觉不符。引入 red_line 后该场景钳制到 40，符合"明显不及格"语义。
- 当前示例 2 的红线只有 2 条：商业红线（C09 承诺折扣）+ 安全红线（C11 用户开车不挂断）。原则是"违反就直接造成业务损害"。

### Q：阈值（85/65/45/30/40）怎么定的？

**A**：演进过程透明。
- v1 初版用 100/80/60/40 区间，红线翻车场景实际得 69 分，验证失败
- v2 调严 P1 阈值，并引入 P2 红线即死（钳制 40），4 通场景全部通过预期
- 阈值不是拍脑袋，每改一次都用伪数据回归测试
- W4 会用 Gold Set 真实数据再做一次敏感性分析，必要时回到这里校准

---

## 8. 已知限制 + 后续优化方向

| 限制 | 应对 |
|---|---|
| critical/non-critical 二分有点粗 | W4 用 Gold Set 数据反推权重，可能改成连续值 |
| 维度权重 25/25/20/15/15 是经验值 | W4 收集多模型评测数据后做敏感性分析 |
| 维度分若某维度内无约束（极少见情况） | 该维度不计入加权，其他维度权重等比例放大 |
| 单个约束 verifier 失败（如 LLM 超时） | 标记为 unknown，不计入分数计算 |

---

## 9. Day 2 验证记录（已完成）

| 对话场景 | 预期分数范围 | v1 实际 | v2 实际 (P3) | 通过 |
|---|---|---|---|---|
| 理想对话：全流程覆盖、所有约束满足 | ≥ 90 | 100 | **100** | ✅ |
| 中规中矩：主流程完整，部分细节欠缺 | 75-87 | 86.86 | **86.86** | ✅ |
| 部分流程缺失：跳过 Step 3.1 + 知识不准 | 55-70 | 69.77 | **65** | ✅ |
| 红线翻车：承诺折扣 + 用户开车未挂断 | ≤ 40 | 69.41 ❌ | **40** | ✅ |

**v1→v2 关键改进**：红线翻车场景从 69.41 降到 40，符合业务直觉。

**验证脚本位置**：`scoring_validation_v2.py`

**回归测试**：后续每次改动评分算法或约束权重，都必须重跑这 4 通场景，确保不破坏现有直觉。