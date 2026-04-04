---
name: config_translator
description: >
  将语义化方案 JSON 转译为设备可执行的配置格式（NL2JSON/NL2DSL）。
  这是最终输出步骤，将方案转为可下发到设备的配置文件。
  当方案校验通过、需要输出最终配置时使用此 Skill。
---

# 配置转译

## 何时使用
- 约束校验通过后，生成最终设备配置（**最后一步**）
- 用户要求导出配置文件

## 如何执行

**第一步**：加载字段映射规则

```
get_skill_instructions("config_translator")
get_skill_reference("config_translator", "field_mapping.md")
```

**第二步**：执行转译脚本

```
get_skill_script(
    "config_translator",
    "translate.py",
    execute=True,
    args=['<plans_json>', '<device_id>']   # device_id 可选，默认为空
)
```

- `plans_json`：plan_generator 返回的 plans dict（key 为 template 文件名）

**脚本输出格式（stdout JSON）**：

```json
{
  "configs": [
    {
      "config_type": "perception",
      "version": "1.0",
      "device_id": "",
      "config_data": { "cei_warn_latency_threshold": 50, "cei_per_user_mode": true, ... },
      "apply_time": "immediate"
    },
    ...
  ],
  "success": true,
  "failed_fields": [],
  "schema": { ... }
}
```

- 输出 4 类配置：perception / closure / optimization / diagnosis
- `failed_fields` 非空时，说明部分字段转译失败，应告知用户

## 规则
- 语义字段名 ≠ 设备配置字段名，必须按 field_mapping.md 映射
- 向用户展示配置摘要和注意事项
- 同时生成回退配置建议（告知如何恢复默认值）
