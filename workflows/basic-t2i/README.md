# 基础文生图示例

这是使用 ComfyUI 基础节点的传统 SDXL 文生图模板，不包含模型。它不依赖原项目的 Anima、WD14、rgthree 或第三方保存节点。

链路：CheckpointLoaderSimple → 正/负 CLIPTextEncode、EmptyLatentImage → KSampler → VAEDecode → SaveImage。输入字段与节点连接见本目录 API 图，参数映射见 workflow.spec.json。

任务示例在包根 `examples/task.basic.json`。资源 ID `local-sdxl` 必须由目标机器配置，filename 必须可被其 CheckpointLoaderSimple 枚举；family 声明必须与实际模型一致。

默认 512×512、20 steps、CFG 7、euler/normal、batch 1 仅用于小型冒烟配置，不是模型最佳参数或显存保证。所有这些参数都可显式覆盖。seed 省略时每次 build/submit 重新随机，复现时读取保存的有效值。

最终节点为 `7`（SaveImage），通过执行历史收集实际文件名。输出前缀由运行库加唯一 run_id，最终本地输出在包根 outputs 中。

支持离线构建与模拟服务协议验证；真实 GPU 生成尚未验证。目标电脑应按 Skill 中的验收步骤完成实测，再记录模型版本、服务版本和 run_id。
