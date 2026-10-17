# 标准 LoRA 文生图示例

基于基础 SDXL 工作流增加标准 LoraLoader。MODEL 和 CLIP 都经节点 `8`，其 MODEL 进入 KSampler，CLIP 进入正负文本编码，VAE 不经过 LoRA。

使用包根 `examples/task.lora.json`。任务必须提供 checkpoint 与 lora 资源 ID，二者 family 都需与工作流一致。资源可枚举只证明服务能找到名称，不证明实际权重兼容。

`lora_model_strength` 和 `lora_clip_strength` 分别映射到 strength_model/strength_clip，示例 0.7 只是占位默认，不是推荐值。触发词必须根据资源档案显式加入 positive。

不使用 LoRA 时选择 basic-t2i；不能用缺失 LoRA 文件并设置零强度来替代旁路。多个 LoRA 应明确串联顺序并增加映射；Power LoRA 等加载器另建适配。

保存与收集方式同基础示例。已做模拟验证，未做真实生成验证。
