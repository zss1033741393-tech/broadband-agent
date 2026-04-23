import { tool } from "@opencode-ai/plugin"
import path from "path"
import { spawn } from "child_process"

export default tool({
  // 和 agno 的 description 完全一致
  description:
    "Read or execute a script from a skill. Set execute=True to run the script and get output, or execute=False (default) to read the script content.",
  args: {
    skill_name: tool.schema
      .string()
      .describe("The name of the skill."),
    script_path: tool.schema
      .string()
      .optional()
      .describe("The filename of the script."),
    execute: tool.schema
      .boolean()
      .default(false)
      .describe(
        "If True, execute the script. If False (default), return content."
      ),
    args: tool.schema
      .array(tool.schema.string())
      .default([])
      .describe(
        "Optional list of arguments to pass to the script (only used if execute=True)."
      ),
    timeout: tool.schema
      .number()
      .default(30)
      .describe(
        "Maximum execution time in seconds (default: 30, only used if execute=True)."
      ),
  },
  async execute(input, context) {
    const fs = await import("fs/promises")

    // ── 防御 1：skill_name 为空 ──
    if (!input.skill_name) {
      return "Error: skill_name is required. Example: get_skill_script(skill_name=\"insight_query\", script_path=\"run_insight.py\", execute=true, args=['{...}'])"
    }

    // ── 防御 2：script_path 未传，列出可用脚本引导模型重试 ──
    if (!input.script_path) {
      const scriptsDir = path.join(
        context.worktree, "skills", input.skill_name, "scripts"
      )
      try {
        const files = await fs.readdir(scriptsDir)
        const pyFiles = files.filter((f: string) => f.endsWith(".py"))
        if (pyFiles.length === 0) {
          return `Error: script_path is required but skill "${input.skill_name}" has no scripts.`
        }
        return [
          `Error: script_path is required. Available scripts for "${input.skill_name}":`,
          ...pyFiles.map((f: string) => `  - ${f}`),
          "",
          `Please call again with script_path specified, e.g.:`,
          `  get_skill_script(skill_name="${input.skill_name}", script_path="${pyFiles[0]}", execute=true, args=['{"..."}'])`,
        ].join("\n")
      } catch {
        return `Error: script_path is required and skill "${input.skill_name}" was not found under skills/ directory.`
      }
    }

    const scriptFile = path.join(
      context.worktree,
      "skills",
      input.skill_name,
      "scripts",
      input.script_path
    )

    // ── 防御 3：检查脚本文件是否存在 ──
    try {
      await fs.access(scriptFile)
    } catch {
      const scriptsDir = path.join(
        context.worktree, "skills", input.skill_name, "scripts"
      )
      try {
        const files = await fs.readdir(scriptsDir)
        const pyFiles = files.filter((f: string) => f.endsWith(".py"))
        return [
          `Error: Script "${input.script_path}" not found in skill "${input.skill_name}".`,
          `Available scripts:`,
          ...pyFiles.map((f: string) => `  - ${f}`),
        ].join("\n")
      } catch {
        return `Error: Skill "${input.skill_name}" not found under skills/ directory.`
      }
    }

    // ── execute=false → 读取脚本内容（和 agno 行为一致）──
    if (!input.execute) {
      try {
        const content = await fs.readFile(scriptFile, "utf-8")
        return content
      } catch (err: any) {
        return `Error reading script: ${err.message}`
      }
    }

    // ── execute=true → 通过 uv run python 执行，spawn(shell:false) 不经过 shell ──
    return new Promise<string>((resolve) => {
      const timeoutMs = (input.timeout || 30) * 1000

      const child = spawn(
        "uv",
        ["run", "python", scriptFile, ...input.args],
        {
          cwd: context.worktree,
          shell: false,
          env: process.env,
        }
      )

      const timer = setTimeout(() => {
        child.kill()
        resolve(
          `ERROR: Script execution timed out after ${input.timeout}s.\n` +
          `Script: ${input.skill_name}/scripts/${input.script_path}\n` +
          `Consider increasing timeout parameter.`
        )
      }, timeoutMs)

      let stdout = ""
      let stderr = ""
      child.stdout.on("data", (d: Buffer) => (stdout += d.toString()))
      child.stderr.on("data", (d: Buffer) => (stderr += d.toString()))

      child.on("error", (err) => {
        clearTimeout(timer)
        resolve(
          `SPAWN ERROR: ${err.message}\n` +
          `Ensure 'uv' is in PATH and Python environment is set up (run 'uv sync' first).`
        )
      })

      child.on("close", (code) => {
        clearTimeout(timer)
        if (code !== 0) {
          resolve(
            `ERROR (exit ${code}):\n` +
            `--- stdout ---\n${stdout.trim()}\n` +
            `--- stderr ---\n${stderr.trim()}`
          )
        } else {
          resolve(stdout.trim())
        }
      })
    })
  },
})
