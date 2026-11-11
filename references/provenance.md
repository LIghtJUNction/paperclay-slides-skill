# 来源与重建说明

## 视觉参考

Paperclay Slides 的视觉参考为用户提供的 `Anthropic_Roadshow_CN_(1).pdf`。分析对象共 57 页，页面内容为栅格图像。由此提炼出暖纸背景、陶土色强调、浅色分组、宽留白、图文分区和数据页结构，并重建为 24 种可复用版式。

版式与参考页的对应关系记录在 `assets/layouts.json` 的 `source_pages`。这些字段用于说明设计依据，不表示逐页复制。页数和对应关系仅描述用户提供的文件。

## 配色与字体

`assets/tokens.json` 中的颜色是对参考页面的视觉采样与重建值，方便制作一致的演示文稿。它们不作为任何公司的官方品牌色规范。

栅格参考文件没有可用于确认原字体的文本字体对象。本模板使用 `Noto Sans CJK SC` 和 `Noto Serif CJK SC` 作为视觉近似，保留中文与拉丁文字混排所需的基本覆盖。字体需从 [Noto CJK 官方仓库](https://github.com/notofonts/noto-cjk) 单独安装；字体授权遵循各字体所附许可证。

## 分发内容

技能包含重建的占位符模板、版式目录、设计 token、Python 工具和使用说明。原始参考 PDF、原稿照片、商标、水印及原稿业务数据不包含在分发包中。

Paperclay Slides 是独立制作的通用演示工具。项目名称和内容不表示与 Anthropic 存在合作、认可或官方模板关系。生成新演示文稿时，使用用户自己的名称、素材和数据。

## 写作方法

说明文档采用用户指定的 [Research-Paper-Writing-Skills](https://github.com/Master-cai/Research-Paper-Writing-Skills) 中的写作方法：先明确结构，每段传递一个信息，按输入、处理和输出解释方法，并用可检查的事实支持功能声明。

该项目将主要写作方法归功于彭思达老师的公开研究笔记及 [learning_research](https://github.com/pengsida/learning_research)，Master-cai 负责整理与技能封装。本技能应用上述写作方法，未捆绑其技能文件。

## 授权范围

原创脚本、说明和占位符模板的许可见发布包中的 `LICENSE`。外部字体、用户加入的图片、标识和数据按各自授权使用。引用视觉参考说明设计来源，不扩大第三方素材的分发权利。
