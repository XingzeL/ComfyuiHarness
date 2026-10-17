# LoRA 资料目录

分类约定：`<功能>/<基底>/<LoRA名称>/`，具体规则见 [LoRA 管理准则](../docs/lora-management.md)。

功能为 character、stylize、action、scene、effect、turbo、other。各功能下的 unknown 是基底待核实资料容器；具体基底目录按需创建。

每份资料包含 README.md、可选的 previews.json 和 preview_01 等本地例图。用 [档案模板](../resources/lora.template.md) 建档。权重保存到本机 ComfyUI 的 LoRA 目录，不放在这里。

统一浏览入口为 [index.html](index.html)，目前是明确标识的占位页；具体目录展示与维护方式由目标电脑的 Agent 和用户确定。

磁盘清单入口为 [LORA目录.md](LORA目录.md)，目前待扫描。对应 `_gen_catalog.py` 与 `_gen_catalog_html.py` 已预留，均明确返回待实现，不能据此声称目录已经刷新。
