import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

// 在 edit / write 修改 .md 文件后，自动校验其中的 mermaid 代码块语法。
// 若存在语法错误，把错误追加到该工具调用的输出中，让模型在下一次迭代时自动修复。
export const CheckMermaidPlugin = async ({ $, client, directory }) => {
  return {
    "tool.execute.after": async (input, output) => {
      const { tool, args } = input;
      if (tool !== "edit" && tool !== "write") return;

      const filePath = args?.filePath;
      if (typeof filePath !== "string" || !/\.(md|mdx)$/i.test(filePath)) return;

      // 只有包含 mermaid 代码块的文件才值得拉起校验子进程
      let content;
      try {
        content = await readFile(filePath, "utf8");
      } catch {
        return;
      }
      if (!/```mermaid/.test(content)) return;

      const script =
        [new URL("../check-mermaid.mjs", import.meta.url).pathname, join(directory, ".opencode", "check-mermaid.mjs")].find(existsSync) ?? "";
      try {
        const proc = await $`node ${script} ${filePath}`.quiet();
        if (proc.exitCode === 1) {
          const detail = proc.stderr.toString().trim();
          output.output = `${output.output ?? ""}\n\n[check-mermaid] 语法校验未通过 (${filePath}):\n${detail}`;
        }
      } catch (e) {
        // 子进程无法运行（缺 node / 依赖未安装）时不阻塞编辑，仅记日志
        await client.app.log({
          body: {
            service: "check-mermaid",
            level: "warn",
            message: `mermaid 校验跳过: ${e instanceof Error ? e.message : String(e)}`,
          },
        });
      }
    },
  };
};
