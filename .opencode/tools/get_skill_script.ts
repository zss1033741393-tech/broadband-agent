import { tool } from "@opencode-ai/plugin"
import path from "path"
import { spawn } from "child_process"

export default tool({
  // ↓ 和 agno 的 description 完全一致
  description:
    "Read or execute a script from a skill. Set execute=True to run the script and get output, or execute=False (default) to read the script content.",
  args: {
    skill_name: tool.schema
      .string()
      .describe("The name of the skill."),
    script_path: tool.schema
      .string()
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
    const scriptFile = path.join(
      context.worktree,
      "skills",
      input.skill_name,
      "scripts",
      input.script_path
    )

    // execute=False → 读取脚本内容（和 agno 行为一致）
    if (!input.execute) {
      const fs = await import("fs/promises")
      try {
        const content = await fs.readFile(scriptFile, "utf-8")
        return content
      } catch (err: any) {
        return `Error reading script: ${err.message}`
      }
    }

    // execute=True → 通过 uv run python 执行，spawn(shell:false) 不经过 shell
    return new Promise<string>((resolve) => {
      const timer = setTimeout(() => {
        child.kill()
        resolve(`ERROR: Script execution timed out after ${input.timeout}s`)
      }, input.timeout * 1000)

      const child = spawn(
        "uv",
        ["run", "python", scriptFile, ...input.args],
        {
          cwd: context.worktree,
          shell: false,
          env: process.env,
        }
      )

      let stdout = ""
      let stderr = ""
      child.stdout.on("data", (d: Buffer) => (stdout += d.toString()))
      child.stderr.on("data", (d: Buffer) => (stderr += d.toString()))

      child.on("error", (err) => {
        clearTimeout(timer)
        resolve(
          `SPAWN ERROR: ${err.message}\nEnsure 'uv' is in PATH and Python environment is set up (run 'uv sync' first).`
        )
      })

      child.on("close", (code) => {
        clearTimeout(timer)
        if (code !== 0) {
          resolve(
            `ERROR (exit ${code}):\n--- stdout ---\n${stdout.trim()}\n--- stderr ---\n${stderr.trim()}`
          )
        } else {
          resolve(stdout.trim())
        }
      })
    })
  },
})
