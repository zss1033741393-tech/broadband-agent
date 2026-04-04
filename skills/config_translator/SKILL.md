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

**推荐方式（直接 Python 工具，无 subprocess 开销）**：

```
plans_file = get_pipeline_file("plans")   # → "outputs/<sid>/plans.json"
translate_configs(plans_file)
# device_id 可选，如需传入：translate_configs(plans_file, device_id="<id>")
```

**备用方式（subprocess，独立 CLI 调试时使用）**：

```
get_skill_script(
    "config_translator",
    "translate.py",
    execute=True,
    args=["--plans-file", "outputs/<sid>/plans.json"]
    # device_id 可选，追加 "--device-id", "<id>"
)
```

> `translate.py` 内部已硬编码 `FIELD_MAPPINGS`，并自动加载 `config_schema.json`，
> **不需要**提前调用 `get_skill_reference` 读取 `field_mapping.md` 或 `config_schema.json`。

**输出格式**：

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
