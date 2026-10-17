# 模型资源资料目录

本目录按 ComfyUI `models` 的实际一级目录分类，预留同名空容器。不仅登记 checkpoint，也覆盖 CLIP、VAE、ControlNet、检测、放大、音频等资源，以及模型包、配置等辅助文件。

这里只放资源档案，不复制或存放权重。容器存在不代表该电脑已安装资源，也不代表任何工作流已经支持它。

## 录入方式

在对应 `modelInfo/<类型>/<资源名称>/README.md` 中，使用 [通用模型档案模板](../resources/model.template.md) 记录名称、类型、来源、版本、文件或目录、基底/架构（适用时）、配套要求和加载方法。

机器可读引用继续使用 `resources/registry.local.json`，不再增加一套重复登记文件。具体模型 ID、默认选择和字段解析由工作流模块根据实际节点实现。

`modelInfo/loras/` 仅保留与 ComfyUI 目录对齐的容器；LoRA 的详细资料仍统一在 [loraInfo](../loraInfo/README.md)，按功能 → 基底 → 名称组织，不在两处重复建档。

## 本机路径与兼容性

实际 models 根可在 config/environment.local.json 的 local.models_root 中记录；额外搜索目录按本机 ComfyUI 配置发现。任务中的加载名称必须以相应节点实际接受的名称为准，不能由资料目录拼出绝对权重路径。

`clip` 与 `text_encoders`、`unet` 与 `diffusion_models` 等目录可能存在别名或共享搜索关系。先保留本机实际目录名，再根据加载节点核对，不强行合并，也不因两个目录存在就认为一定有两份不同模型。

类型与基底不是同一概念：VAE、CLIP、检测模型等按实际架构和配套关系记录；不适用基底分类的资源注明不适用，信息未确认则写未知。不能给全部资源强行套一个生成模型 family。

首次按当前 ComfyUI 的 models 目录预留容器。迁移后 Agent 应按目标电脑实际目录补建；仅传文件的方式（如 Git）可能不保留空目录，应在初始化时重建。具体模型目录在实际录入时创建，不生成虚假的模型条目。
