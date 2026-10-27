# Writing Review · 写作复利

**批注保存到固定目录，让你正在使用的AI按需读取。**

[English](README.md) · [架构](docs/architecture.md) · [验收](docs/verification.md) · MIT

## 一键开始

Python 3.10+，无需第三方运行依赖。Windows双击 `start.cmd`，或执行：

```sh
python -X utf8 -m writing_review
```

浏览器打开 `http://127.0.0.1:8765`。导入TXT、Markdown或旧版JSON，
选中文字添加意见，原文自动显示黄色；不选文字则批注整段。
正文可以直接编辑，多条重叠批注、刷新恢复和JSON导出均保留。

## 批注存到X，再让AI读取X

X可以是你指定的目录：

```sh
python -X utf8 -m writing_review --review-dir "你的固定批注目录"
```

也可以直接指定Obsidian库：

```sh
python -X utf8 -m writing_review --vault "你的Obsidian库路径"
```

配置库后，默认X为库内 `写作复利/批注收件箱/`；未配置则放在私人数据目录的
`reviews/`。网页会显示准确路径。每份文稿包含：

- `latest.json`：结构化原始记录，包括原稿、当前正文、选文、批注ID与意见。
- `latest.md`：方便AI和人通读的正文与批注。
- `history/`：按版本保留JSON与Markdown，不覆盖旧版本。
- `CURRENT.json`：指向已完整保存的最新版本对，AI应先读此文件。

已有批注在启动时补写，无需重新导出或重新批注。页面修改自动落盘。
文件目录暂时不可写时，数据库仍保存，页面提示交接文件待重试。
“重新保存交接文件”只重新写文件，不调用模型。

点击 **复制给AI的指令**，粘贴给有本地文件权限的AI即可。通用说法是：

> 请读取X中的AI读取说明.md和目标文稿的CURRENT.json，按其指定的JSON/Markdown逐条修订，并把明确写作偏好按适用范围整理到Obsidian写作复利。

没有本地权限的AI由你提供JSON/Markdown。文件保存不等于AI已处理，工具不会宣称自动学习完成。

## 写作复利仍然保留

AI在修订前读取风格速查和对应场景规则；修订后记录用户明确偏好、来源ID、范围和修改前后例子。
推断只进入候选，同轮重复意见不重复计数，人工笔记和冲突历史要保留。
引言规则不自动套用摘要，本篇术语不自动升级为跨项目原则。

“本次写作偏好”仍可读取已有规则，也可执行：

```sh
python -X utf8 -m writing_review --profile academic introduction project:你的项目ID
```

这些读取操作不调用模型。其他AI需通过其支持的指导文件或本次请求读取同一知识源。

## 可选高级功能与边界

后台模型提炼默认关闭，旧任务也不会自动运行。只有主动传入 `--auto-extract` 才启用旧Codex适配器，
需要兼容的模型和登录；模型拒绝访问不会影响默认保存与文件交接。启用时相关编辑材料会发送给所配置的模型提供方。
修改启动配置后需要重启服务。

本地服务只监听127.0.0.1，校验来源和会话令牌。私人数据默认位于Windows的
`%LOCALAPPDATA%/WritingReview`，可用 `--data-dir` 修改。勿将私人数据、批注目录和Obsidian库放入公开仓库。

纯离线HTML备用页仍支持浏览器保存和JSON导出，但不能自动写入X，需手动导出交回。
初版暂不支持DOCX/PDF导入、复杂富文本或自动改稿。真实中文输入法体验仍需实际使用验证。
测试命令、合成示例和可选CI见[English README](README.md)。
