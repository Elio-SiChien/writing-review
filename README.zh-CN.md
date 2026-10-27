# Writing Review · 写作复利

**在本地批注，把每一轮反馈变成下一次写作可用的偏好。**

[English](README.md) · MIT · Python 3.10+

## 开始使用

```sh
git clone https://github.com/Elio-SiChien/writing-review.git
cd writing-review
python -X utf8 -m writing_review
```

Windows可双击 `start.cmd`。浏览器打开 `http://127.0.0.1:8765`。
导入TXT、Markdown或旧版批注JSON，选文字后点击“添加批注”；不选文字则批注整段。
正文中已批注的位置显示黄色，侧栏和原文可以互相定位，多个批注可重叠。
正文仍可直接编辑；重定位有歧义时会提示，不随意高亮另一个位置。
Markdown以普通文本编辑，初版不提供富文本渲染。

页面修改自动保存到仓库外的本机数据库。导出JSON可以跨设备交接；
“下载离线页”生成无需服务的独立HTML，支持浏览器保存与JSON导出。

## 接入Obsidian

先安装官方Codex CLI，并执行 `codex login`。首次配置库路径：

```sh
python -X utf8 -m writing_review --vault "你的Obsidian库路径"
```

保存后停止修改约15秒，后台合并处理，读取批注意图、选文和实际修订，
以只读Codex进程生成结构化建议，再由本地服务写入库根目录 `写作复利/`。
用户明确要求按适用范围生效，AI推断进入候选；同轮重复意见不增加确认次数。
每条规则保留来源、范围和修改前后证据，手工修改的笔记不会被自动覆盖。
既有手工笔记首次接入时保留原文，后续冲突单独记录。

默认继承现有Codex模型配置。若模型不受账户支持，批注仍保存，界面显示沉淀待重试。
可主动指定 `--codex-model 模型名`；工具不静默替换模型。

**提炼时，批注、相关文稿和匹配的偏好会发送给你配置的Codex模型提供方。**
“本地”指审阅界面和文件保存位置；模型提炼需要联网，不是离线训练。
无需配置API密钥，复用CLI已有认证；仓库不会保存登录凭证。

## 下次写作如何调用

```sh
python -X utf8 -m writing_review --profile academic introduction project:你的项目ID
```

也可点击“本次写作偏好”。给其他AI同一段说明：

> 写作前读取本库“写作复利/风格速查.md”及相关场景和项目规则；只使用匹配范围的生效偏好；候选不视为用户要求；保留冲突历史。

可放入所用产品正式支持的指导文件，但不意味着所有产品都会自动读取。
引言规则不自动套用摘要，本篇术语不自动推广到其他课题。

## 保存、恢复与限制

- 默认私人数据目录：Windows `%LOCALAPPDATA%/WritingReview`；其他系统 `~/.local/share/WritingReview`，可用 `--data-dir` 修改。
- 监听127.0.0.1，校验Host/Origin及会话令牌。可写位置限私人数据目录与配置库中的写作复利目录。
- 模型或Obsidian不可用时，批注保存与JSON导出照常工作，沉淀任务重试。
- 多标签版本冲突不覆盖最新文件；用“导出冲突恢复副本”保留未发送修改，再人工合并。
- 离线页依赖浏览器存储，清理浏览器会移除该副本，请导出JSON备份。
- 不会自动改稿、核验学术事实或训练模型。暂不支持DOCX/PDF和复杂富文本。
- 初版面向单机单用户；请勿把私人数据目录或Obsidian库加入公开仓库。

测试与架构见 [English README](README.md)、[架构说明](docs/architecture.md)。
