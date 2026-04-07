---
name: solution_generation
description: "根据用户画像生成综合网络调优方案，包含 CEI、故障、远程闭环、Wifi 四类配置"
---

# 方案生成

## Metadata
- **name**: solution_generation
- **description**: 依据用户画像渲染四类方案模板（CEI + 故障 + 远程闭环 + Wifi）
- **when_to_use**: slot_filling 完成后，需要根据结构化画像生成完整调优方案时
- **paradigm**: Template + Workflow
- **inputs**: slot_filling 输出的结构化用户画像 JSON
- **outputs**: 包含四类配置的完整方案

## When to Use
- ✅ slot_filling 已完成，所有必填槽位已齐
- ✅ 数据洞察后用户要求生成优化方案
- ❌ 槽位信息不完整时（应继续 slot_filling）
- ❌ 用户只需要单个配置（应用具体功能 Skill）

## How to Use
1. 接收 slot_filling 输出的用户画像 JSON
2. 调用 `get_skill_script("solution_generation", "render.py")` 渲染模板
3. 脚本会根据画像参数渲染四类配置模板:
   - `templates/cei_spark.yaml.j2` → CEI 配置
   - `templates/fault_api.json.j2` → 故障配置
   - `templates/remote_loop.json.j2` → 远程闭环配置
   - `templates/wifi_sim.yaml.j2` → Wifi 仿真配置
4. 将四份配置整合为完整方案展示给用户

## Templates / References
- `templates/cei_spark.yaml.j2`
- `templates/fault_api.json.j2`
- `templates/remote_loop.json.j2`
- `templates/wifi_sim.yaml.j2`

## Examples

**输入画像**:
```json
{
  "user_type": "主播用户",
  "package_type": "直播套餐",
  "scenario": "卖场走播",
  "guarantee_target": "STA级",
  "time_window": "18:00-22:00"
}
```
**输出**: 包含四类配置的完整方案文档
