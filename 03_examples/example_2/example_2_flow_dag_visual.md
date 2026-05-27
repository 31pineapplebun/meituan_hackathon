# 示例 2 嵌套 Flow DAG 可视化

> 用于配合 `example_2_flow_dag.json` 验证流程理解

## 完整流程图

```mermaid
flowchart TD
    Start([开场白: 问是否负责人]) --> S1{S1: 身份确认}
    S1 -->|是负责人| S2{S2: 确认是否知情}
    S1 -->|不是负责人<br/>请其转达| S2

    S2 -->|不知情<br/>说明前端原因| S3[S3: 传达升级内容]
    S2 -->|已知情| S3

    S3 --> S3_1[S3.1: 区别说明<br/>标准 vs 低延迟]
    S3_1 --> S3_2[S3.2: 价格说明]
    S3_2 --> S3_3[S3.3: FAQ]
    S3_3 --> S4[S4: 确认前端可见]

    S4 --> S4_1{S4.1: 询问发布方式}
    S4_1 -->|Web控制台| S4_WEB{Web控制台分支}
    S4_1 -->|校务系统A/SaaS系统B| S4_TP{第三方系统分支}

    S4_WEB -->|已显示<br/>直接使用| S5
    S4_WEB -->|未显示<br/>后台配置,明天查看| S5

    S4_TP -->|已显示<br/>按需选择| S5
    S4_TP -->|未显示| SF1[/子流程SF_GUIDE_OPEN<br/>缓慢引导开通4步骤<br/>每步暂停3秒/]
    SF1 --> S5

    S5{S5: 检查学员端费用}
    S5 -->|未设置费用| S6
    S5 -->|已设置费用<br/>提醒适用低延迟| S5_SUB{可否自行配置?}

    S5_SUB -->|可以| S6
    S5_SUB -->|无法| SF2[/子流程SF_GUIDE_FEE<br/>缓慢引导设置4步骤<br/>每步暂停3秒/]
    SF2 --> S6

    S6{S6: 企业微信添加}
    S6 -->|号码可添加<br/>请通过验证| S7
    S6 -->|不可添加<br/>请提供新号码| S7

    S7([S7: 结束通话<br/>祝课程顺利、招生满满])

    %% 中断条件：可由任意主流程节点触发（用虚线表示非常规跳转）
    Driving{{中断条件:<br/>用户说在开车}}:::interrupt
    Driving -.->|"中断当前节点<br/>无论流程进展到哪一步"| EARLY[EARLY_END:<br/>那我稍后再打<br/>挂断]

    classDef step fill:#E8F4F8,stroke:#2E86AB,stroke-width:2px
    classDef sub_step fill:#FFF4E6,stroke:#F18F01,stroke-width:1.5px
    classDef branch fill:#F0E8FF,stroke:#6A4C93,stroke-width:2px
    classDef sub_flow fill:#FFE8E8,stroke:#C73E1D,stroke-width:2px
    classDef terminal fill:#E8F8E8,stroke:#2D7A2D,stroke-width:2px
    classDef interrupt fill:#FFFDE7,stroke:#F57F17,stroke-width:2px,stroke-dasharray: 5 5

    class S3,S4 step
    class S3_1,S3_2,S3_3,S4_1 sub_step
    class S1,S2,S4_WEB,S4_TP,S5,S5_SUB,S6 branch
    class SF1,SF2 sub_flow
    class S7,EARLY terminal
```

## 流程统计

| 类型 | 数量 |
|---|---|
| 主要 step | 7 |
| 嵌套子 step | 5 (S3.1, S3.2, S3.3, S4.1, S5.SUB_CHECK) |
| 分支判定点 | 7 (S1, S2, S4.1, S4.1.WEB, S4.1.THIRD_PARTY, S5, S5.SUB_CHECK, S6) |
| 子流程 | 2 (SF_GUIDE_OPEN, SF_GUIDE_FEE，各含4个有序子步骤) |
| 终止节点 | 2 (S7正常结束 + EARLY_END_DRIVING提前结束) |
| 最大嵌套深度 | 3 (S4 → S4.1 → S4.1.THIRD_PARTY) |

## 这张图揭示的真实复杂度

对比示例 1 的 4 个线性 step，示例 2 实际包含：

1. **7 个主步骤**，其中 4 个含分支
2. **9 个分支决策点**（每个 if/else 算 2 个分支）
3. **2 个子流程**，每个 4 个有序步骤，且有时序约束
4. **3 层嵌套**：S4 → S4.1 → S4.1.THIRD_PARTY → SF_GUIDE_OPEN

**这意味着**：
- 一次完整对话至少要触发 7 个 step 节点
- 完整覆盖所有分支需要至少 8 通对话（多种 persona）
- 子流程必须分轮发送（不能一轮说完4步），这是新的约束类型
