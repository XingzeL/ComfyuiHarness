# 模型与辅助资源登记规则

登记范围覆盖 ComfyUI models 中实际存在的全部一级目录，不局限于 checkpoint、UNet、CLIP、VAE。资料容器统一在 [modelInfo](../modelInfo/README.md)，按 models 目录类型分类；其中 loras 只保留容器，LoRA 详细档案仍在 loraInfo。

## 三个独立事实

“有档案”表示知道资源信息；“可加载”表示当前服务能找到名称；“兼容”表示资源适用于当前模型体系及链路。不能互相替代。真实生成验证另行记录日期、环境和任务 ID。

机器登记使用 `resources/registry.local.json`，基础引用记录 `id`、`kind`、`filename`；需要按生成模型基底检查的资源另记 `family`：

- `id` 是稳定逻辑标识，任务用它引用资源。
- `kind` 表示资源类型，不限于 checkpoint、lora；按目标加载节点及工作流配置使用。现有公共样例的 kind 与 resource_kind 必须一致。
- `family` 是生成模型或 LoRA 等资源的基底兼容信息，需要时必须核实。CLIP、VAE、检测器等优先记录实际架构及配套要求，不能为所有目录强行填写同一基底。不适用与未知要区分。
- `filename` 是加载节点接受的相对文件名或模型包名称，可带子目录；不要求资源都是单个 .safetensors 文件。
- `document`、`verification` 是可选档案和验证说明；不会自动证明资源可用。

示例中的 SDXL 只是教学场景。原公共样例仍按 family 严格匹配它们使用的 checkpoint 和 LoRA，不代表已实现全部资源的自动解析。新工作流模块按实际加载节点实现类型、架构与配套检查；登记必须基于来源和验证，不能读一个目录名就判定兼容。

## 加载方法

一体式 checkpoint、UNet、CLIP、VAE 分别对应不同加载方式。更换模型体系时重新核对整条链，不只替换 checkpoint 文件名。

LoRA 记录：基底与版本、作用于 model/CLIP 的方式、触发词、建议强度、叠加顺序、适用工作流和验证结果。作者建议和本机实测分开，不把某次成功参数写成全局固定值。

标准 `LoraLoader` 接法：模型加载器的 MODEL/CLIP → LoRA → 采样模型与正负提示词编码。VAE 仍来自模型加载器。多 LoRA 按明确顺序串联，记录每段强度。

仅模型 LoRA 使用 `LoraLoaderModelOnly` 时没有 CLIP 输出；rgthree、easy 节点或其他堆叠加载器的字段和旁路方式可能不同，先查 `/object_info` 与实现，不直接复用标准 LoRA 的字段结构。

模型文件名在枚举中不存在时明确报缺失；不偷偷选相近名字。不同系统分隔符可以按服务枚举规范化，但不修改文件名的含义。

## 档案与资料

使用 [通用模型档案模板](../resources/model.template.md) 和 [LoRA 档案模板](../resources/lora.template.md)。详细说明分别放在 modelInfo 与 loraInfo；机器可读引用只维护已有 registry.local.json，不再增加重复清单。

每次任务必须查看当前基底的角色 LoRA；目标角色有兼容且可加载的 LoRA 时默认使用。角色档案不按工作流保存多套配置，实际接法由当前 Agent 处理。换角先看图，再结合 WD14 和用户输入规划过滤及补充，详见 [LoRA 管理准则](lora-management.md)。

LoRA 的资料目录、分类、录入字段及 HTML 维护统一遵守 [LoRA 管理准则](lora-management.md)。详细资料放在 `loraInfo/`，`resources/registry.local.json` 仅保存运行所需的资源引用，不重复维护完整档案。

下载和安装属于独立动作。确需入库时记录来源、版本、文件大小和可用摘要；不携带原项目凭据，不默认安装某一模型体系的最新版。
