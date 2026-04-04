---
name: user_profiler
description: >
  查询和补全用户画像信息。从历史数据、应用行为、网络 KPI 中提取
  用户先验信息。当需要了解用户历史行为、网络状况、或补全画像字段时使用。
---

# 用户画像

## 何时使用
- 意图解析时需要历史数据辅助补全
- 需要查询用户应用行为历史
- 需要查询网络 KPI 数据

## 处理步骤
1. 调用 scripts/profile_handler.py 查询用户历史画像
2. 对照 references/profile_template.json 检查哪些字段已有
3. 根据 references/field_rules.md 的规则，从应用历史和 KPI 推断可补全字段
4. 返回已有画像 + 仍需用户确认的字段列表

## 规则
- 能从历史推断的就不追问用户
- 周期性行为（如定时断电）从 KPI 数据自动识别
- 画像数据可被 intent_parsing Skill 引用
