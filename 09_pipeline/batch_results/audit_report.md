# B.5 标注规范健全度审计报告

> 标记可疑约束: **11** 条
> 优先级: 按分歧case数降序

## 怎么读这份报告

每条约束含: 约束名 + 人工 evidence 样本 + 我的修订建议

**3 种诊断**:
- `evidence_mismatch`: 人工 evidence 跟约束类型不符 (高度可疑)
- `systematic_h_pass_a_fail`: 60%+ 都是'人工 pass, auto fail'(可能人工太宽松)
- `systematic_h_fail_a_pass`: 60%+ 都是'人工 fail, auto pass'(可能人工太严或人工错判)

---

## 1. V5_C01: 每次回复保持在 15-20 字左右，简短清晰。

- **Verifier**: rule
- **维度**: D3_constraint_compliance
- **数据**: 总 15 通, 一致 0, 分歧 15
  - 人工 pass / mock fail: 15
  - 人工 fail / mock pass: 0
- **诊断**: `evidence_mismatch:15/15, systematic_h_pass_a_fail:15/15`

### Evidence 不匹配样本

- `V5_interruption_1779203124_001`
  - 人工 pass: 您好，请问是川香小厨的负责人吗？我是美团商家关怀客服。看到咱们店近7天收到了3个差评，特意打过来看看…
  - Mock fail: 14/14=100%超字数(限20+5=25)
  - **问题**: non_length_evidence_on_length_constraint
- `V5_interruption_1779202919_000`
  - 人工 pass: 您好，请问是川香小厨的负责人吗？我是美团商家关怀客服。看到咱们店近7天收到了3个差评，特意打过来看看…
  - Mock fail: 14/14=100%超字数(限20+5=25)
  - **问题**: non_length_evidence_on_length_constraint

### 我的修订建议

- ⚠️ 人工把**字数违规**当作**流程结构违规**了, 应该改: 
  - 这条约束(流程结构)的判定应该看 step 是否覆盖, **不看字数**
  - 字数违规应该归到 V*_C01 (长度约束) 上
  - **建议**: 把 disagree 的 case 全部从 fail 改成 pass


## 2. V5_C12: S1 自我介绍并询问对方是否为商家负责人。

- **Verifier**: state_tracker
- **维度**: D1_flow_compliance
- **数据**: 总 15 通, 一致 0, 分歧 15
  - 人工 pass / mock fail: 0
  - 人工 fail / mock pass: 15
- **诊断**: `evidence_mismatch:15/15, systematic_h_fail_a_pass:15/15`

### Evidence 不匹配样本

- `V5_out_of_scope_1779197726_000`
  - 人工 fail: 超长(阈值25字): T7=54字；T11=53字；T19=51字
  - Mock pass: 匹配关键词 3/5 (60%, 阈值≥2个)
  - **问题**: length_evidence_on_flow_constraint
- `V5_cooperative_1779202511_001`
  - 人工 fail: 超长(阈值25字): T21=73字；T25=70字；T17=69字
  - Mock pass: 匹配关键词 4/5 (80%, 阈值≥2个)
  - **问题**: length_evidence_on_flow_constraint

### 我的修订建议

- ⚠️ 人工把**字数违规**当作**流程结构违规**了, 应该改: 
  - 这条约束(流程结构)的判定应该看 step 是否覆盖, **不看字数**
  - 字数违规应该归到 V*_C01 (长度约束) 上
  - **建议**: 把 disagree 的 case 全部从 fail 改成 pass


## 3. V4_C12: S1 自我介绍并询问接电话的是否为商家负责人。

- **Verifier**: state_tracker
- **维度**: D1_flow_compliance
- **数据**: 总 12 通, 一致 0, 分歧 12
  - 人工 pass / mock fail: 0
  - 人工 fail / mock pass: 12
- **诊断**: `evidence_mismatch:12/12, systematic_h_fail_a_pass:12/12`

### Evidence 不匹配样本

- `V4_interruption_1779197143_001`
  - 人工 fail: 超长(阈值25字): T7=57字；T9=52字；T3=44字
  - Mock pass: 匹配关键词 3/5 (60%, 阈值≥2个)
  - **问题**: length_evidence_on_flow_constraint
- `V4_interruption_1779202280_001`
  - 人工 fail: 超长(阈值25字): T7=61字；T29=53字；T11=48字
  - Mock pass: 匹配关键词 3/5 (60%, 阈值≥2个)
  - **问题**: length_evidence_on_flow_constraint

### 我的修订建议

- ⚠️ 人工把**字数违规**当作**流程结构违规**了, 应该改: 
  - 这条约束(流程结构)的判定应该看 step 是否覆盖, **不看字数**
  - 字数违规应该归到 V*_C01 (长度约束) 上
  - **建议**: 把 disagree 的 case 全部从 fail 改成 pass


## 4. V4_C01: 每次回复控制在 15-20 字左右，保持精简。

- **Verifier**: rule
- **维度**: D3_constraint_compliance
- **数据**: 总 12 通, 一致 0, 分歧 12
  - 人工 pass / mock fail: 12
  - 人工 fail / mock pass: 0
- **诊断**: `evidence_mismatch:12/12, systematic_h_pass_a_fail:12/12`

### Evidence 不匹配样本

- `V4_cooperative_1779196436_000`
  - 人工 pass: 您好，请问是老王炸鸡店的负责人吗？我是美团客服。您这边有个尾号 8234 的订单，目前已经超时 25…
  - Mock fail: 3/5=60%超字数(限20+5=25)
  - **问题**: non_length_evidence_on_length_constraint
- `V4_interruption_1779197143_001`
  - 人工 pass: 您好，请问是 老王炸鸡店 的负责人吗？我是美团客服。您这边有个尾号 8234 的订单，目前已经超时 …
  - Mock fail: 6/6=100%超字数(限20+5=25)
  - **问题**: non_length_evidence_on_length_constraint

### 我的修订建议

- ⚠️ 人工把**字数违规**当作**流程结构违规**了, 应该改: 
  - 这条约束(流程结构)的判定应该看 step 是否覆盖, **不看字数**
  - 字数违规应该归到 V*_C01 (长度约束) 上
  - **建议**: 把 disagree 的 case 全部从 fail 改成 pass


## 5. V2_C15: [META] 适时终结对话

- **Verifier**: llm_judge
- **维度**: D5_dialogue_quality
- **数据**: 总 12 通, 一致 1, 分歧 11
  - 人工 pass / mock fail: 11
  - 人工 fail / mock pass: 0
- **诊断**: `systematic_h_pass_a_fail:11/12`

### 我的修订建议

- 人工偏宽, mock 偏严. 多数情况 mock 是对的
- 例: V5_C01 字数 15-20, 人工 pass 但实际超字数 - 应该改 fail


## 6. V1_C08: S1 告知培训的具体时间地点，并询问骑手是否可以参加。

- **Verifier**: state_tracker
- **维度**: D1_flow_compliance
- **数据**: 总 11 通, 一致 1, 分歧 10
  - 人工 pass / mock fail: 0
  - 人工 fail / mock pass: 10
- **诊断**: `evidence_mismatch:10/11, systematic_h_fail_a_pass:10/11`

### Evidence 不匹配样本

- `V1_cooperative_1779193967_000`
  - 人工 fail: 超长(阈值35字): T7=45字；T17=37字；T9=36字
  - Mock pass: 匹配关键词 3/7 (43%, 阈值≥2个)
  - **问题**: length_evidence_on_flow_constraint
- `V1_out_of_scope_1779200168_000`
  - 人工 fail: 超长(阈值35字): T13=39字
  - Mock pass: 匹配关键词 4/7 (57%, 阈值≥2个)
  - **问题**: length_evidence_on_flow_constraint

### 我的修订建议

- ⚠️ 人工把**字数违规**当作**流程结构违规**了, 应该改: 
  - 这条约束(流程结构)的判定应该看 step 是否覆盖, **不看字数**
  - 字数违规应该归到 V*_C01 (长度约束) 上
  - **建议**: 把 disagree 的 case 全部从 fail 改成 pass


## 7. V2_C08: S1 告知 APP 有强制更新要求，并明确必须在 ${deadline} 前完成更新。

- **Verifier**: state_tracker
- **维度**: D1_flow_compliance
- **数据**: 总 12 通, 一致 3, 分歧 9
  - 人工 pass / mock fail: 0
  - 人工 fail / mock pass: 9
- **诊断**: `evidence_mismatch:9/12, systematic_h_fail_a_pass:9/12`

### Evidence 不匹配样本

- `V2_interruption_1779196169_000`
  - 人工 fail: 超长(阈值35字): T9=48字
  - Mock pass: 匹配关键词 3/4 (75%, 阈值≥2个)
  - **问题**: length_evidence_on_flow_constraint
- `V2_cooperative_1779200835_000`
  - 人工 fail: 超长(阈值35字): T3=49字；T5=44字；T7=40字
  - Mock pass: 匹配关键词 2/4 (50%, 阈值≥2个)
  - **问题**: length_evidence_on_flow_constraint

### 我的修订建议

- ⚠️ 人工把**字数违规**当作**流程结构违规**了, 应该改: 
  - 这条约束(流程结构)的判定应该看 step 是否覆盖, **不看字数**
  - 字数违规应该归到 V*_C01 (长度约束) 上
  - **建议**: 把 disagree 的 case 全部从 fail 改成 pass


## 8. V1_C06: 若骑手坚持不参加，礼貌挂断通话。

- **Verifier**: llm_judge
- **维度**: D5_dialogue_quality
- **数据**: 总 11 通, 一致 3, 分歧 8
  - 人工 pass / mock fail: 8
  - 人工 fail / mock pass: 0
- **诊断**: `systematic_h_pass_a_fail:8/11`

### 我的修订建议

- 人工偏宽, mock 偏严. 多数情况 mock 是对的
- 例: V5_C01 字数 15-20, 人工 pass 但实际超字数 - 应该改 fail


## 9. V2_C01: 每次回复控制在 30 字以内，简短干脆。

- **Verifier**: rule
- **维度**: D3_constraint_compliance
- **数据**: 总 12 通, 一致 6, 分歧 6
  - 人工 pass / mock fail: 6
  - 人工 fail / mock pass: 0
- **诊断**: `evidence_mismatch:6/12`

### Evidence 不匹配样本

- `V2_cooperative_1779200835_000`
  - 人工 pass: 喂，是李建军吗？我是咱们站长。通知你个事儿，咱们骑手APP出新版了，必须在明天晚上12点前更新完，不…
  - Mock fail: 4/6=67%超字数(限30+5=35)
  - **问题**: non_length_evidence_on_length_constraint
- `V2_out_of_scope_1779195816_000`
  - 人工 pass: 喂，是 李建军 吗？我是咱们站长。通知你个事儿，咱们骑手 APP 出新版了，必须在 明天晚上12点 …
  - Mock fail: 4/5=80%超字数(限30+5=35)
  - **问题**: non_length_evidence_on_length_constraint

### 我的修订建议

- ⚠️ 人工把**字数违规**当作**流程结构违规**了, 应该改: 
  - 这条约束(流程结构)的判定应该看 step 是否覆盖, **不看字数**
  - 字数违规应该归到 V*_C01 (长度约束) 上
  - **建议**: 把 disagree 的 case 全部从 fail 改成 pass


## 10. V1_C01: 每次回复大约在 30 字以内，不要长篇大论。

- **Verifier**: rule
- **维度**: D3_constraint_compliance
- **数据**: 总 11 通, 一致 6, 分歧 5
  - 人工 pass / mock fail: 5
  - 人工 fail / mock pass: 0
- **诊断**: `evidence_mismatch:5/11`

### Evidence 不匹配样本

- `V1_refuse_persistent_1779194514_000`
  - 人工 pass: 喂，是王强吗？我是咱们美团的骑手站长。通知你一下，10月15号下午2点在望京培训中心有个线下安全培训…
  - Mock fail: 2/2=100%超字数(限30+5=35)
  - **问题**: non_length_evidence_on_length_constraint
- `V1_out_of_scope_1779194673_000`
  - 人工 pass: 喂，是王强吗？我是咱们美团的骑手站长。通知你一下，10月15号下午2点在望京培训中心有个线下安全培训…
  - Mock fail: 4/7=57%超字数(限30+5=35)
  - **问题**: non_length_evidence_on_length_constraint

### 我的修订建议

- ⚠️ 人工把**字数违规**当作**流程结构违规**了, 应该改: 
  - 这条约束(流程结构)的判定应该看 step 是否覆盖, **不看字数**
  - 字数违规应该归到 V*_C01 (长度约束) 上
  - **建议**: 把 disagree 的 case 全部从 fail 改成 pass


## 11. V5_C13: S2 告知近 7 天的差评数量 ${review_count_last_7days}，

- **Verifier**: state_tracker
- **维度**: D1_flow_compliance
- **数据**: 总 7 通, 一致 2, 分歧 5
  - 人工 pass / mock fail: 5
  - 人工 fail / mock pass: 0
- **诊断**: `systematic_h_pass_a_fail:5/7`

### 我的修订建议

- 人工偏宽, mock 偏严. 多数情况 mock 是对的
- 例: V5_C01 字数 15-20, 人工 pass 但实际超字数 - 应该改 fail
