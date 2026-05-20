# Workspace AGENTS

## 子代理策略
- Use subagents liberally to keep main context window clean offload research,exploration,and parallel analysis to subagents
- For complex problems, throw more compute at it via subagents One task per subagent for focused execution

## 使用skill规范
- 每次对话开始时，先寻找当前最适合的 skill 流程来做，并列出会按怎样的 skill 来安排哪些内容。
- 正常情况下不需要每次都告诉用户这次用了哪些 skill；只有在用户明确要求、或说明 skill 选择本身对理解结果很关键时，再主动说明。

## 沟通的简洁性
- 正常情况下，中间排查过程不需要显性输出；优先直接执行、测试、排查，等完全排查完后再简洁说明结果。
- 不使用 P0/P1/P2 术语。
- 描述问题要用大白话。
- 默认使用更自然的表达方式，像正常聊天一样回答。
- 只有在信息整理、对比、汇总时，表格确实更清楚的情况下才使用表格。

## 第一性原理
- 使用第一性原理思考。
- 不要默认用户非常清楚自己想要什么或该怎么得到。
- 保持审慎，从原始需求和问题出发。
- 如果动机和目标不清晰，先停下来和用户讨论。
- 如果目标清晰但路径不是最短，直接指出，并建议更好的办法。

## 开发流程树 worktree
- 所有开发都要符合以下流程规范。
- 先使用 using-superpowers 编排选流程，并建立一个流程图；后续任何改动、更新、功能新增都要在流程图中体现。
- 使用 planning-with-files 建立 `task_plan.md`、`progress.md`、`findings.md`，详细列清楚所需功能内容。
- 每次开发前用 gsd-method-guide 把每步写成 `///`。
- 如果涉及开发改动，走 OpenSpec 四步闭环。
- 每次改动、每次新增功能，都要同步更新流程图。

## 交付规范
- 交付给用户的文件与说明默认使用中文。
- 必须避免乱码。
- 生成的文件不得触发恢复/修复模式。
- 在交付前必须先做一次完整审核与可打开性检查。

##  Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.