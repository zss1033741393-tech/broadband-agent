---
name: config_translator
description: >
  【Pipeline 模式】将语义化方案 JSON 转译为设备可执行的配置格式（NL2JSON）。
  触发条件：约束校验通过后，生成最终设备下发配置（最后一步，不可提前执行）。
  输出 4 类设备配置：perception / diagnosis / closure / optimization。
---

# 配置转译

## 执行步骤

**推荐方式（直接 Python 工具，无 subprocess 开销）**：

```
plans_file = get_pipeline_file("plans")   # → "outputs/<sid>/plans.json"
translate_configs(plans_file)
# device_id 可选：translate_configs(plans_file, device_id="<id>")
```

**备用方式（subprocess，CLI 调试时使用）**：

```
get_skill_script(
    "config_translator",
    "translate.py",
    execute=True,
    args=["--plans-file", "outputs/<sid>/plans.json"]
)
```

> `translate.py` 内部使用 `FIELD_MAPPINGS` 和 `config_schema.json` 进行字段映射，
> 如需查阅语义字段 → 设备字段的映射关系，可参考：
> ```
> get_skill_reference("config_translator", "field_mapping.md")
> ```

**输出格式**：

```json
{
  "configs": [
    {
      "config_type": "perception",
      "version": "1.0",
      "device_id": "",
      "config_data": { "cei_warn_latency_threshold": 50, "cei_per_user_mode": true },
      "apply_time": "immediate"
    }
  ],
  "success": true,
  "failed_fields": []
}
```

- 输出 4 类配置：perception / closure / optimization / diagnosis
- `failed_fields` 非空时告知用户哪些字段转译失败

## 规则
- 语义字段名 ≠ 设备配置字段名，内部按 field_mapping.md 映射
- 向用户展示配置摘要和关键参数值
- 同时告知用户回退方案（如何恢复默认值）
- 可参考 domain_expert 的设备能力矩阵确认设备支持情况：
  ```
  get_skill_reference("domain_expert", "device_capabilities.json")
  ```
