# 内容填充与工具使用

## 执行位置与依赖

以下命令在包含 `SKILL.md`、`assets/` 和 `scripts/` 的技能目录运行。生成文件放在独立项目目录中。Python 脚本会按自身位置寻找默认模板，图片路径按内容 JSON 的位置解析。

核心填充、检查脚本使用 Python 标准库。渲染需要已安装并可在命令行调用的 LibreOffice，以及 PyMuPDF。预览拼图另外需要 Pillow。

```bash
python3 -m pip install PyMuPDF Pillow
```

从 [LibreOffice 官方下载页](https://www.libreoffice.org/download/download-libreoffice/) 安装 LibreOffice。从 [Noto CJK 官方仓库](https://github.com/notofonts/noto-cjk) 的 [Sans](https://github.com/notofonts/noto-cjk/tree/main/Sans) 和 [Serif](https://github.com/notofonts/noto-cjk/tree/main/Serif) 获取简体中文版本，安装 `Noto Sans CJK SC`、`Noto Serif CJK SC`。字体不包含在技能包内。

Windows 可右键字体文件安装，macOS 可用“字体册”安装。Linux 可将字体放入用户字体目录，并在提供 fontconfig 的系统运行 `fc-cache -f`。安装后重新启动演示软件或渲染进程，使其读取新字体。

## 查看版式

```bash
python3 scripts/inspect_template.py
python3 scripts/inspect_template.py --layout chart_full
python3 scripts/inspect_template.py --output /path/to/catalog.json
```

默认读取 `assets/paperclay.pptx`。使用 `--input /path/to/template.pptx` 查看另一份模板。目录中的 `layouts.json` 给出每个字段的类型、位置、字号、字符限制和默认占位提示。

## 内容格式

用 UTF-8 保存 JSON。顶层 `title` 是演示文稿名称，`slides` 的顺序决定输出顺序。每页的 `layout` 必须是目录中的 ID，且必须提供 `text.title`。

```json
{
  "title": "项目进展",
  "author": "项目组",
  "footer": "项目组",
  "slides": [
    {
      "layout": "cover",
      "text": {
        "title": "项目进展",
        "subtitle": "本周工作与下一步",
        "date": "2026.11"
      }
    },
    {
      "layout": "three_rows",
      "text": {
        "title": "本周工作",
        "heading_1": "需求梳理",
        "body_1": "整理已确认需求并明确验收方式。",
        "heading_2": "功能实现",
        "body_2": "按优先级实现本轮约定功能。",
        "heading_3": "交付准备",
        "body_3": "检查文档、演示和待处理问题。"
      },
      "notes": "示例文字，仅展示内容格式。"
    }
  ]
}
```

将示例文字替换为用户真实材料。顶层 `author` 和 `footer` 可省略。全局 `footer` 为含 `brand` 字段的页面提供默认页脚，页内同名字段可以覆盖它；页码自动生成。

| 页面键 | 内容 |
| --- | --- |
| `layout` | 版式 ID |
| `text` | 文本字段到字符串的映射 |
| `images` | 图片字段到图片配置的映射 |
| `tables` | 表格字段到表格数据的映射 |
| `charts` | 图表字段到图表数据的映射 |
| `notes` | 本页来源、口径或演讲备注 |

可选文字未提供时会清空，可选图片、表格和图表未提供时会移除对应占位对象。若需要完整空白模板，直接复制 `assets/paperclay.pptx`，不要通过空内容 JSON 生成。

## 图片

将图片配置放入 `images`。键名需与所选版式一致，例如封面使用 `image_1`、`image_2`、`image_3`，左图章节页使用 `image`。

```json
{
  "layout": "section_image",
  "text": {
    "title": "研究方法",
    "subtitle": "数据与验证流程"
  },
  "images": {
    "image": {
      "path": "media/method.jpg",
      "fit": "cover"
    }
  },
  "notes": "图片来源：填写实际来源及授权信息。"
}
```

脚本支持 PNG、JPEG 和 GIF。`fit: "cover"` 填满占位区域并裁切超出的部分；`fit: "contain"` 保留完整图像比例。图片路径相对 JSON 所在目录，例如 `content.json` 与 `media/` 放在同一个项目文件夹中。

## 原生表格

将表头放入 `headers`，数据行放入 `rows`。每行单元格数量需与表头一致。

```json
{
  "layout": "native_table",
  "text": {
    "title": "交付清单",
    "caption": "示例清单"
  },
  "tables": {
    "table": {
      "headers": ["项目", "交付物", "状态"],
      "rows": [
        ["模板", "可编辑演示文件", "待填写"],
        ["文档", "使用说明", "待填写"]
      ]
    }
  }
}
```

空白模板以原生内容占位符保留表格位置。填入数据后，脚本生成 PowerPoint 原生表格。单元格较长或行数过多时，应拆表或拆页。表格内的单位、时间范围和统计口径要保持明确。

## 原生图表

图表支持 `bar`（分组竖柱图）与 `line`（折线图）。每个序列的 `values` 长度必须与 `categories` 一致，数值应为 JSON 数字。

```json
{
  "layout": "chart_full",
  "text": {
    "title": "演示数据",
    "caption": "以下数值仅用于展示图表输入格式"
  },
  "charts": {
    "chart": {
      "type": "bar",
      "categories": ["第一组", "第二组", "第三组"],
      "series": [
        {"name": "示例序列", "values": [12, 18, 24]}
      ]
    }
  },
  "notes": "合成示例数据，不作为业务或研究结论。"
}
```

空白模板以原生内容占位符保留图表位置。填入数据后，脚本创建原生图表，并将数据存入嵌入的工作簿。使用 `chart_triptych` 时，分别填入 `chart_1`、`chart_2`、`chart_3`。需要比较绝对大小时，渲染后核对各图的坐标范围；自动缩放可能让不同图看起来相近。

## 生成、检查和预览

```bash
python3 scripts/compose_deck.py --spec /path/to/content.json --output /path/to/deck.pptx
python3 scripts/audit_deck.py --input /path/to/deck.pptx --output /path/to/audit.json
python3 scripts/render_preview.py --input /path/to/deck.pptx --output-dir /path/to/preview
```

`compose_deck.py` 还接受 `--template` 和 `--catalog` 以明确指定模板及版式目录。默认行为会拒绝未知字段和超过 `max_chars` 的文本。`--allow-overflow` 将长度超限改为警告，保留原字号；仅在已经检查实际排版后使用。

`audit_deck.py` 检查文件关系、遗留占位提示、对象越界和图表缓存长度。文本容量判断是近似检查。审核占位符模板时加 `--allow-placeholders`，普通成稿保持默认检查。

`render_preview.py` 输出与 PPTX 同名的 PDF、逐页 `slide-01.png` 等图片和 `contact_sheet.png`。默认预览宽度为 1600，可通过 `--width` 改变；通过 `--columns` 设置拼图列数。

```bash
python3 scripts/render_preview.py --input /path/to/deck.pptx --output-dir /path/to/preview --width 1600 --columns 3
```

## 视觉检查

逐页确认标题与正文没有截断，中文字体显示正确，表格没有超出区域，图例和标签可读，图片关键内容没有被裁掉。检查页脚与页码不干扰主体内容。

发现拥挤时，依次尝试缩短重复文字、采用更宽的现有版式、拆分页面。保持原有字号与边距。生成预览所用的 LibreOffice 与用户最终编辑软件可能存在细微的字体和图表渲染差异；在目标软件中定稿前再看一次关键页面。
