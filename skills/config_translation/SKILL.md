---
name: config_translation
description: >
  将语义化方案 JSON 转译为设备可执行的配置格式（NL2JSON/NL2DSL）。
  这是最终输出步骤，将方案转为可下发到设备的配置文件。
  当方案校验通过、需要输出最终配置时使用此 Skill。
---

# 配置转译

## 何时使用
- 方案校验通过后，需要输出设备配置
- 用户要求导出配置文件

## 处理步骤
1. 读取 references/config_schema.json 了解设备配置格式
2. 参考 references/field_mapping.md 进行字段映射
3. 调用 scripts/translator.py 执行转译
4. 校验输出格式合规性
5. 输出 4 类配置 JSON（感知粒度/故障诊断/远程闭环/智能优化）

## 规则
- 语义字段名 ≠ 设备配置字段名，必须按 field_mapping 映射
- 输出必须通过 config_schema.json 的格式校验
- 转译失败时返回具体失败字段，不要猜测
