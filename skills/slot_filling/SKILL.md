---
name: slot_filling
description: "槽位填充引擎：综合目标场景驱动追问收集画像；数据洞察场景从洞察结果提取参数，供方案生成使用"
---

# 槽位填充引擎

## Metadata
- **name**: slot_filling
- **description**: 驱动决策树追问（综合目标）或提取洞察参数（数据洞察），输出结构化画像 JSON
- **when_to_use**: 综合目标需拆解意图并收集完整槽位；或 data_insight 后需要构造方案生成所需画像时
- **paradigm**: Workflow + Instructional
- **inputs**: 用户自然语言描述（模式A）/ data_insight 完整输出 JSON（模式B）
- **outputs**: 结构化用户画像 JSON（含 mode 标记）

## When to Use
- ✅ 用户描述了综合性业务目标（如"直播套餐用户，保障直播"）
- ✅ 主 Agent 判定为"综合目标类"任务
- ✅ data_insight 完成后用户要求生成优化方案（以数据洞察模式调用）
- ❌ 用户直接指定了具体功能（CEI/Wifi/故障/远程闭环）

## 场景分支

### 模式A — 综合目标（原有逻辑）

**调用方式**：`slot_engine.process(current_state_json, user_input)`

**行为**：
1. 调用 `get_skill_script("slot_filling", "slot_engine.py", execute=True)` 初始化或更新槽位状态
2. 引擎返回当前槽位状态和下一批追问
3. 根据返回提示向用户提问（每次 1-2 个槽位）
4. 用户回答后重新调用引擎更新状态
5. 所有必填槽位填齐后，引擎返回 `is_complete=true` 及完整 JSON
6. 将 JSON 传递给 solution_generation

### 模式B — 数据洞察（新增）

**调用方式**：`slot_engine.process_from_insight(insight_result_json)`

**触发时机**：data_insight 执行完毕、用户要求生成优化方案时

**行为**：
1. 调用 `get_skill_script("slot_filling", "slot_engine.py", execute=True)` 并传入 data_insight 完整输出
2. 脚本返回：
   - `extracted_slots`：已程序化确定的字段（time_window、complaint_history）
   - `slots_to_infer`：含推断线索的待推断字段列表
   - `config_hints`：来自 data_insight 的原始配置线索
   - `insight_summary`：快速摘要（priority_pons、distinct_issues、remote_loop_candidates 等）
3. **Agent 根据推断线索自行填充剩余槽位**：
   - `guarantee_target`：参考 `scope_indicator`（regional/multi_pon → 整网，single_pon → 家庭网络）
   - `scenario`：参考 `distinct_issues` 中的异常类型推断适用场景
   - `user_type` / `package_type`：若无明确信号，使用通用默认值（宽带用户/普通套餐）
4. 构造完整画像 JSON，加入 `"mode": "data_insight"` 和 `config_hints`，设置 `is_complete=true`
5. 直接流转 solution_generation（**无需追问**，原型阶段）

> **扩展点**：当关键字段无法从洞察数据推断时，可将追问写入 `next_questions` 字段，走与模式A相同的追问逻辑。当前原型阶段 `next_questions` 始终为空。

## Scripts
- `scripts/slot_engine.py` — 槽位状态管理、追问逻辑、洞察模式预处理

## Examples

### 模式A 示例

**输入**: "直播套餐卖场走播用户，18:00-22:00 保障抖音直播"
**解析结果**:
```json
{
  "user_type": "主播用户",
  "package_type": "直播套餐",
  "scenario": "卖场走播",
  "guarantee_target": null,
  "time_window": "18:00-22:00",
  "complaint_history": null
}
```
**追问**: "您希望保障的范围是？（家庭网络 / STA级 / 整网）"

### 模式B 示例

**输入**: data_insight 完整输出（含 config_hints）
**处理结果**:
```json
{
  "mode": "data_insight",
  "extracted_slots": {"time_window": "19:00-22:00", "complaint_history": true},
  "slots_to_infer": {"guarantee_target": "参考 scope_indicator='regional' → 候选值='整网'", ...},
  "config_hints": {"priority_pons": ["PON-2/0/5", "PON-1/0/3"], ...},
  "next_questions": []
}
```
**Agent 推断后构造画像并流转 solution_generation**
