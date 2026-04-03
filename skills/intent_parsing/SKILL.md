---
name: intent_parsing
description: >
  解析用户自然语言输入为结构化意图目标。识别用户类型、场景、保障时段、
  保障对象、核心指标。信息不完整时生成追问。
  当用户描述保障需求、优化需求、或任何需要理解意图的场景时使用此 Skill。
---

# 意图解析

## 何时使用
- 用户首次输入保障需求描述
- 用户补充/修改需求信息
- 需要追问澄清模糊表述

## 处理步骤
1. 读取 references/intent_schema.json 了解目标结构
2. 从用户输入中提取可识别的字段
3. 调用 scripts/parse_intent.py 进行语义解析
4. 检查缺失字段，参考 references/examples.md 生成自然的追问
5. 所有字段完整后输出 IntentGoal JSON

## 规则
- 模糊表述要结合上下文推断，不要每个字段都追问
- 优先从用户画像 Skill 获取历史数据自动补全
- 追问最多 3 轮，超过后用合理默认值补全

## 输出格式
IntentGoal JSON（见 references/intent_schema.json）
