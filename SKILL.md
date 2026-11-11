---
name: paperclay-slides
description: 使用暖纸底色、陶土橙、克制字体和宽留白的 Paperclay Slides 模板制作可编辑 PPTX。适用于用户要求纸陶幻灯、参考路演风格、同款排版的演示文稿、项目汇报、产品介绍、研究报告，或要求复用本技能中的占位符模板。提供 24 种版式、结构化内容填充、原生表格和图表、预览与检查脚本。
---

# Paperclay Slides

从 `assets/paperclay.pptx` 复制所需版式，填入内容并输出独立的 PPTX。保留原模板供下次使用。`assets/paperclay.potx` 提供 PowerPoint 模板格式；`assets/preview.png` 展示六种代表版式。使用 `assets/layouts.json` 查询字段、类型、边界和文本长度，使用 `assets/tokens.json` 保持配色与字体一致。

## 制作流程

1. 明确受众、页数、用途和可用材料。先写每页一句话大纲，再选择版式。读取 [design-system.md](references/design-system.md) 了解排版约束。
2. 将每页内容映射到一个版式。每页必须提供 `text.title`。按 [authoring-guide.md](references/authoring-guide.md) 编写 UTF-8 JSON。将真实数据、单位和来源一起保留，原始材料缺少的事实不自行补造。
3. 先运行 `inspect_template.py` 查询实际字段。使用现有字段名，避免凭名称猜测。用短文本表达单一信息；内容过密时改用更宽版式或拆页。
4. 运行 `compose_deck.py`。让脚本报告未知字段和超长文本；先修改内容或版式，再重新生成。保持字号，不通过缩小字体塞入内容。
5. 运行 `audit_deck.py` 和 `render_preview.py`。查看每一页 PNG，检查标题折行、字形、间距、图片裁切、表格和图例。自动检查仅覆盖结构与近似边界，仍需视觉检查。
6. 交付 PPTX 和紧凑预览。说明会影响使用的依赖或渲染差异。只有实际打开相应软件后，才声称已在该软件中检查。

## 常用命令

在本技能目录运行。将内容文件和输出目录设为用户项目中的实际路径。

```bash
python3 scripts/inspect_template.py --layout chart_full
python3 scripts/compose_deck.py --spec /path/to/content.json --output /path/to/deck.pptx
python3 scripts/audit_deck.py --input /path/to/deck.pptx
python3 scripts/render_preview.py --input /path/to/deck.pptx --output-dir /path/to/preview
```

核心脚本使用 Python 3.10+ 标准库。渲染需要 LibreOffice 和 PyMuPDF，拼图需要 Pillow。安装 `Noto Sans CJK SC` 与 `Noto Serif CJK SC` 后再检查中文排版；字体来源和安装方法见 [authoring-guide.md](references/authoring-guide.md)。

## 版式选择

| 任务 | 优先版式 |
| --- | --- |
| 开场、分节、单一主张 | `cover`、`section_image`、`section_dark`、`statement` |
| 导航、原则、团队 | `agenda`、`three_rows`、`team` |
| 对照、结构、过程 | `comparison`、`architecture`、`process`、`hub_spoke` |
| 并列内容、策略 | `three_columns`、`strategy_rows` |
| 趋势、证据、指标 | `text_chart`、`chart_triptych`、`metric_grid`、`kpi_chart`、`trend`、`chart_kpis`、`chart_full` |
| 表格、摘要、附录 | `summary_table`、`table_callout`、`native_table`、`appendix_text` |

## 填充规则

- 将文字放入 `text`，图片放入 `images`，数据表放入 `tables`，图表放入 `charts`。图片路径相对 JSON 文件所在目录解析。
- 模板以原生内容占位符保留图片、图表和表格的位置。填入数据后，脚本生成图片对象、原生表格和可编辑图表。图表支持分组竖柱图和折线图。
- 普通成稿中，省略的可选文字会清空，省略的媒体占位对象会移除。通过全局 `footer` 设置组织页脚；页码自动生成。
- 用户只要空白模板时，交付 `assets/paperclay.pptx` 的副本，保留所有占位符。检查模板使用 `audit_deck.py --allow-placeholders`。
- 保持暖纸背景、墨色文字和少量陶土橙强调。蓝、桃、灰米和鼠尾草绿用于已选版式中的分组。不要随意增加渐变、阴影或小卡片。
- 保留用户指定的页数。正文过多时先精简重复内容；需要增页时结合任务范围决定，不随意增加封面或附录。

## 设计来源

本技能根据用户提供的 57 页栅格路演 PDF 重建设计规则。原始字体无法从该文件确认，模板采用 Noto CJK 字体作视觉近似。原 PDF、照片、商标和水印不随技能分发。来源与边界见 [provenance.md](references/provenance.md)。
