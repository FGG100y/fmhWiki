#!/usr/bin/env node
// 校验 .md 文件中的 mermaid 代码块语法。
// 用法: node check-mermaid.mjs <file.md>
// 退出码: 0=通过(或没有 mermaid 块)  1=存在语法错误  2=参数错误/运行环境问题
import { readFile } from "node:fs/promises";

const [, , filePath] = process.argv;
if (!filePath) {
  console.error("usage: node check-mermaid.mjs <file.md>");
  process.exit(2);
}

const content = await readFile(filePath, "utf8");
const blocks = [...content.matchAll(/```mermaid\s*\n([\s\S]*?)\n?```/g)];

if (blocks.length === 0) process.exit(0);

const startLine = (match) => content.slice(0, match.index).split("\n").length;

const { JSDOM } = await import("jsdom");
const dom = new JSDOM("<!DOCTYPE html><html><body></body></html>");
globalThis.window = dom.window;
globalThis.document = dom.window.document;
globalThis.navigator = dom.window.navigator;

const { default: mermaid } = await import("mermaid");
mermaid.initialize({ startOnLoad: false, securityLevel: "loose" });

const errors = [];
for (let i = 0; i < blocks.length; i++) {
  const block = blocks[i][1];
  try {
    await mermaid.parse(block);
  } catch (e) {
    const raw = e instanceof Error ? e.message : String(e);
    const msg = raw
      .split("\n")
      .map((l) => l.trim())
      .filter((l) => l && !/^[-^]+$/.test(l))
      .join(" ");
    errors.push(`第 ${i + 1} 个 mermaid 代码块 (行 ${startLine(blocks[i])}): ${msg}`);
  }
}

if (errors.length > 0) {
  console.error(errors.join("\n"));
  process.exit(1);
}
