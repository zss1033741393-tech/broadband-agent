---
name: remote_optimization
description: "远程优化（远程闭环）：调用 FAE 平台批量优化接口，针对单用户故障下发设备重启/信道切换/功率调整等整改动作"
---

# 远程优化

## Metadata
- **paradigm**: Tool Wrapper (封装 FAE 平台 manual batch optimize 接口)
- **when_to_use**: ProvisioningCeiChainAgent 需要对故障用户下发远程整改动作时
- **inputs**: JSON 参数（schema 见下）
- **outputs**: 接口调用结果 JSON（`params` + 业务返回 + `dispatch_result`）

## Parameter Schema（Provisioning 按此从方案段落提参）

| 字段 | 类型 | 必填 | 默认值 | 允许值 | 说明 |
|---|---|---|---|---|---|
| `strategy` | string | 是 | `immediate` | `immediate` / `idle` / `scheduled` | 执行策略 |
| `rectification_method` | list[int] | 否 | `null`（代表"全部"） | `[1,2,3,4]` 的任意子集 | 整改方式编号列表 |
| `operation_time` | string | 条件必填 | `0-0-0-*-*-*` | cron 6 段格式 | 仅 `strategy=scheduled` 时有效，用 `-` 分隔的 cron 表达式 |
| `config` | string | 否 | `fae_poc/config.ini` 绝对路径 | — | 自定义 config.ini 路径，留空使用默认 |

### strategy 语义

| 值 | 含义 | 典型场景 |
|---|---|---|
| `immediate` | 立即执行 | 投诉处置 / 紧急恢复 |
| `idle` | 闲时执行 | 业务时段保障（避免影响直播/游戏） |
| `scheduled` | 定时执行 | 计划性维护，必须搭配 `operation_time` |

### rectification_method 取值（见 `references/rectification_methods.md`）

| 值 | 含义 |
|---|---|
| `1` | 设备重启 |
| `2` | 信道切换 |
| `3` | 2.4G 功率调整 |
| `4` | 5G 功率调整 |
| 不传 / `null` / `[]` | 全部整改方式 |

**本 Skill 不做业务规则判断**：`rectification_method` 的组合由 PlanningAgent 在方案段落里决定（例如卖场走播场景默认含信道和 5G 功率调整），本 Skill 只做"参数 → CLI → 接口调用"的映射。

### operation_time cron 格式

6 段 cron，**用 `-` 分隔**（非空格），脚本会内部转换为空格：

```
秒-分-时-日-月-周
0-0-0-*-*-*   # 每天 00:00:00
0-30-2-*-*-*  # 每天 02:30:00
```

## When to Use

- ✅ Provisioning 接收方案段落含"远程闭环处置方案: **启用**: true"
- ✅ 场景 3 单点指令：用户要求"立即重启网关" / "闲时远程优化 / 闲时信道调整" — 任务头 `[任务类型: 单点远程操作]`
- ✅ 完整保障链的第三步（CEI 低分 + 可修复故障时触发）
- ❌ 需要现场工程师处置的硬件故障
- ❌ 用户只是咨询"能做哪些远程操作"（直接回答即可，不必调用）

## How to Use

1. ProvisioningAgent 按 schema 组装参数 JSON，列表字段用 JSON 原生数组：
   ```json
   {"strategy": "idle", "rectification_method": [1, 2, 3, 4]}
   ```
2. 调用脚本：
   ```
   get_skill_script(
       "remote_optimization",
       "manual_batch_optimize.py",
       execute=True,
       args=["<params_json_string>"]
   )
   ```
3. 脚本内部按 schema 把 JSON 展开为 argparse CLI 参数调用 FAE 平台
4. Skill 返回 `{skill, params, dispatch_result}` JSON，Provisioning **原样透传**给用户

## CLI 契约（脚本支持两种入口，保持兼容）

- **推荐：JSON 入口** — `args=["<params_json_string>"]`，由脚本内部映射到 argparse
- **兼容：标准 argparse 入口** — 可直接命令行调用，用于调试

```bash
# 立即执行（默认），全部整改方式
python manual_batch_optimize.py --strategy immediate

# 闲时执行，仅设备重启 + 信道切换
python manual_batch_optimize.py --strategy idle --rectification-method 1,2

# 定时执行
python manual_batch_optimize.py --strategy scheduled --operation-time 0-0-0-*-*-*

# 指定配置文件
python manual_batch_optimize.py --config /abs/path/to/fae_poc/config.ini
```

**参数连接符统一为空格**（argparse 标准），不要使用 `--strategy: immediate` 这类带冒号的形式。

## 依赖 fae_poc 包

本 Skill 脚本依赖项目根的 `fae_poc/` 包获取 `NCELogin` 和 `config.ini`：

```
broadband-agent/
├── fae_poc/
│   ├── __init__.py          # 导出 DEFAULT_CONFIG_PATH / require_config 等辅助
│   ├── NCELogin.py          # 用户本地部署（.gitignore 忽略）
│   ├── config.ini           # 用户本地部署（.gitignore 忽略）
│   └── config.ini.example   # 占位模板（提交）
└── skills/remote_optimization/
    └── scripts/
        └── manual_batch_optimize.py  # 顶部做双路径注入后调用 NCELogin
```

初次部署：
1. 把本地 Fae POC 项目的 `NCELogin.py` 拷贝到 `fae_poc/NCELogin.py`
2. 把 `fae_poc/config.ini.example` 复制为 `fae_poc/config.ini` 并填入真实 `base_url` / `csrf_token` / `cookie`
3. 两个文件已在 `.gitignore` 中排除，不会误提交

### 脚本顶部 prelude (复用到 cei_pipeline / fault_diagnosis 等其他真实接口脚本)

```python
import sys
from pathlib import Path

# 项目根 → 使 `from fae_poc import ...` 辅助对象可用
# fae_poc 目录 → 使 `from NCELogin import NCELogin` 这种 bare 导入可用
# 两者都注入,同时兼容两种导入风格
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_FAE_POC_DIR = _PROJECT_ROOT / "fae_poc"
for _p in (str(_PROJECT_ROOT), str(_FAE_POC_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from fae_poc import DEFAULT_CONFIG_PATH, require_config  # noqa: E402
# NCELogin 延迟到 main() 里 import, 这样部署缺失时也能返回结构化错误而非 crash
```

在 main() 里：

```python
def main():
    args = parse_args()
    config_path = require_config(args.config)  # 校验并返回绝对路径
    from NCELogin import NCELogin               # bare 导入,与本地 Fae POC 项目一致
    nce_login = NCELogin(config_file=str(config_path))
    # ... 调用 nce_login 的业务方法 ...
```

**重要**：如果从本地 "Fae POC" 项目直接迁移脚本过来，argparse 里的 `--config` 默认值往往是 `'../../config.ini'` 这类相对路径，放到本项目目录结构后会解析错位。**务必**改为 `default=str(DEFAULT_CONFIG_PATH)`，这样 `args.config` 永远是一个有效的绝对路径。

## Scripts

- `scripts/manual_batch_optimize.py` — FAE 平台批量优化接口调用入口

## References

- `references/rectification_methods.md` — 整改方式编号对照表

## Output Schema

脚本 stdout 为 JSON，包含以下字段：

```json
{
  "skill": "remote_optimization",
  "params": {
    "strategy": "idle",
    "rectification_method": [1, 2, 3, 4],
    "operation_time": "0-0-0-*-*-*",
    "config": "/abs/path/to/fae_poc/config.ini"
  },
  "cli_args": ["--strategy", "idle", "--rectification-method", "1,2,3,4"],
  "dispatch_result": {
    "status": "success",
    "message": "批量优化任务已下发",
    "task_id": "RMO-xxxxx"
  }
}
```

**Provisioning 必须原样透传 stdout**，不得改写或截断。

## 禁止事项

- ❌ 不做业务规则判断（整改方式组合/执行策略由 PlanningAgent 在方案段落里决定）
- ❌ 不在 Skill 脚本里硬编码 base_url / csrf_token / cookie（一律从 `fae_poc/config.ini` 读取）
- ❌ 不在 `rectification_method` 里填枚举之外的值（会被 FAE 平台拒绝）
- ❌ `strategy=scheduled` 时不要省略 `operation_time`（会走默认 `0-0-0-*-*-*` 实际可能不是用户期望）
