# 逐工作流封装模板

沿用当前 ComfyUIAPI 模块结构：配置 → 本模块 workflow_builder → /prompt 异步入队 → ComfyUI 后台直接保存。复制本目录到 workflows 下并按目标机器工作流修改，不通过自动加载适配器。

本例是传统 SDXL 单图采样，最终节点为自定义 `Image Save`，沿用原项目的字段。该节点是依赖，不保证目标电脑已安装；提交时会检查节点与字段及模型枚举。不同节点实现即使同名也需要核对保存语义。

## 使用

1. 配置包根 config/environment.local.json，填实际 base_url。也可通过 --env 显式指定环境文件。
   确认并填写 limits.max_image_pixels；缺失或 null 时提醒用户并停止正式投递，超过上限同样停止。本例检查主采样画布，改为多阶段工作流时须补充各阶段尺寸检查。
2. 将 config.example.json 中 checkpoint 改为本机可识别的文件名；确认触发词、模型与采样设置。
3. `python run.py --config config.example.json --dry-run` 检查最终图。dry-run 不联网、不创建 output；显式 --save-prompt 时才写指定文件。
4. 获得生成授权并检查环境后，去掉 --dry-run 提交。返回 prompt_id、seed、expected_output_path、manifest_path 后结束投递轮。
5. 后续轮次再检查预期文件、历史和图片有效性；不需要执行公共运行器的 collect 才会保存图片。

## 运行规则

- 本例没有每张重启要求；提交前执行服务/节点/资源检查和最近输出检查。
- 正式提交一次即异步返回，不等待成图；dry-run 不执行网络或服务操作。
- image_limits.py 从本机配置检查像素上限；未确定或超限时在联网与创建提交记录前停止。dry-run 会提示尚未检查本机预算，不自动采用默认上限。
- 缩放比例、尺寸对齐和内部放大后的尺寸由当前 Agent 按具体工作流计算，并接入本模块；不依赖统一缩放模板。
- 需要检查结果时在后续轮次确认任务完成并检查实际输出。
- 按目标工作流修改本节：写明动作发生阶段、频率、顺序、执行脚本、本机命令来源、队列冲突处理和失败停止条件。
- 必需的重启由本模块 api.py 或结果处理脚本调用包根 scripts 的服务入口。当前服务文件是占位，本机 Agent 先补齐再使用。
- 完成后动作不能紧跟在异步入队返回后执行；需由有完成确认能力的后续脚本承担。

## 输出和记录

API 设置本模块 output/YYYYMMDD 的绝对路径，服务进程必须能访问这个目录；不能拿客户端路径当远程服务器路径。文件前缀总会附加唯一 run_id，使用 prefix_as_filename 保存单张 PNG，避免重试覆盖。

config 参数 filename_prefix 只填简短技术标识，不含场景、服装、动作等内容描述。预期路径仅对本例单图及 Image Save 的命名语义成立；修改节点、batch 或保存模式后须同步调整预期路径逻辑。

output/jobs/<run_id> 保存 task.json、实际 prompt.json 和 submit_manifest.json。提交前检查服务、依赖与最近输出。确认异常黑图后由 Agent 按包根 docs/tasks.md 重启并重投，最多三次恢复重启，仍黑则告知用户。API 本身不等待生成或循环恢复。

提交超时等不确定结果保留 submission_unknown，不自动重试。每次重跑都创建新记录。保留任务依据和成图，清理仅针对明确的一次性脚本。

## 按新工作流修改

替换 workflow.json；修改 models.py 与 workflow_builder.py 的字段和节点映射。必要时扩展 api.py 的输入上传、缩放及预检；保留原保存节点，在 output_paths 或 builder 中实现其保存规则。

当前模板没有图生图上传、任意 LoRA 堆栈、自动安装依赖和服务启动能力。真实 GPU 生成未验证；只有离线构建与模拟提交验证。接入后记录目标环境、依赖、实际输出与恢复说明。

每次任务查看 loraInfo 中当前基底的角色 LoRA，默认选用目标角色的兼容文件；本次 Agent 负责加载代码适配，不要求角色档案保存各工作流配方。换角先看图，再结合 WD14 和用户要求处理提示词。输入放包根 Grokbot/input，结果检查后汇总到 Grokbot/output；新测试脚本放包根 test，按任务现生成。
