# HarnessUI

给 Agent 的 ComfyUI 启动包：理解环境、管理资源、接入不同工作流、提交与验证任务。核心是方法和规则，Python 代码是可改造的最小示例，不是 UI 应用，也不是 ComfyUI 安装器。

## 包内有什么

- `AGENTS.md`：Agent 阅读入口。
- `INITIALIZE.md`：首次使用或迁移后的初始化 Prompt，指导路径确认、环境分析、脚本补齐和分层验收。
- `docs/`：环境、文件、资源、任务规则，接口说明与提炼依据。
- `skills/comfyui-workflow-onboard/`：接入现有工作流或搭建最小工作流的方法。
- `harnessui/`：HTTP 调用、参数映射、任务记录和图片收集。
- `workflows/`：基础文生图与标准 LoRA 文生图示例。
- `templates/workflow_module/`：沿用 ComfyUIAPI 的逐工作流 API/CLI 封装模板，使用 Image Save 异步直接落盘。
- `resources/`：资源登记示例、模型和 LoRA 档案模板。
- `modelInfo/`：按 ComfyUI models 一级目录预留的模型及辅助资源资料容器，不存权重；LoRA 详细资料仍由 loraInfo 维护。
- `loraInfo/`：按“功能 → 基底 → LoRA”组织的资料容器，规则见 [LoRA 管理准则](docs/lora-management.md)。
- `config/`、`examples/`：环境和任务配置示例。
- `scripts/`：启动、停止、重启和状态检查入口；由本机 Agent 补齐实现，当前返回未配置。
- `test/`：按当前任务生成的测试脚本，不固定测试框架或复用旧脚本。
- `Grokbot/input/`、`Grokbot/output/`：沿用原项目的入图与成图汇总位置。
- `tests/`：初版代码的历史验证脚本，不是新任务的固定要求。
- `buffer/`：归属不明的文件、候选路径与待提炼经验；`archive/buffer/` 保存已处理主题，见 [维护规则](docs/maintenance.md)。

复制整个目录即可迁移；不需要上级项目。Windows 本地使用是首版目标，跨目录迁移和协议行为已经通过离线测试。真实 GPU 生成、Linux 和远程服务须在目标电脑另外验证。结果见 [验证记录](docs/validation.md)。

## 首次配置

交给 Agent 初始化时，先使用 [初始化 Prompt](INITIALIZE.md)。下面的命令供手动配置或检查时参考，已有有效配置不要覆盖。

工作流管理以 [工作流管理规则](docs/workflows.md) 为准：新工作流复制模块模板后建立自己的 API、配置与构建逻辑，保留来源工作流的保存方式。现有五命令公共程序与两个基础图仅作为另一套可运行参考，不要求全部工作流使用标准 SaveImage。

在包根目录打开终端，使用 Python 3.10+：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item config/environment.example.json config/environment.local.json
Copy-Item resources/registry.example.json resources/registry.local.json
```

后续示例使用 `python`，请换成已安装依赖的解释器，或激活该虚拟环境。

1. 编辑环境配置里的 `base_url`，填目标 ComfyUI 的实际地址。示例 `8188` 只是常见值，不是自动检测结果。
   同时与用户确认 `limits.max_image_pixels` 并填正整数；默认 null 时正式投递会提醒并停止。该值是宽 × 高的像素上限，不是显存容量。
2. `python -m harnessui inspect` 查看可发现的节点和模型名。
3. 根据实际模型修改资源登记中的 `filename` 和 `family`。示例占位文件名不可直接投递。
4. 核对工作流与模型体系。示例都是传统 SDXL 链；逐模块模板用 Image Save 直接写盘，公共样例用标准 SaveImage。不能通过仅改文件名适配所有 Anima、Flux 或分拆式模型。
5. 接入不同工作流时先读 [Skill](skills/comfyui-workflow-onboard/SKILL.md)。

`local` 字段用于记录安装位置、解释器与额外模型路径；当前客户端不读取本机权重，也不使用这些字段启动服务。模型是否可选以 ComfyUI 返回的节点枚举为依据。

## 五个命令

本节仅说明已提供的公共参考运行器；逐模块模板使用自身 `run.py`，不受本节标准 SaveImage 收集限制。

```powershell
# 不需要环境配置，不联网；输出解析后的 prompt 和有效参数
python -m harnessui --registry resources/registry.example.json build --task examples/task.basic.json

# 联网只读检查当前任务的节点、字段、枚举与连接
python -m harnessui inspect --task examples/task.basic.json

# 正式投递：执行前需确认目标环境及任务内容
python -m harnessui submit --task examples/task.basic.json

# 将下面的 RUN_ID 换成 submit 返回值
python -m harnessui status --run RUN_ID
python -m harnessui collect --run RUN_ID
```

全局参数 `--root`、`--env`、`--registry` 放在子命令之前。`status`、`collect` 使用 manifest 中的原服务地址，避免切换配置后查询了另一台服务。

成功提交会记录在 `runs/<run_id>/`；图片通过 `/history` 和 `/view` 收集到 `outputs/<workflow_id>/<YYYYMMDD>/<run_id>/`。`collect` 不等待任务结束，也不会自动重试生成。

标准 LoRA 示例使用 `examples/task.lora.json`：model 与 CLIP 强度分别配置。不需要 LoRA 时选择基础工作流，不用不存在的 LoRA 文件加零强度绕过加载。

## 验证

测试按当前任务现生成，脚本放入 `test/`，方法与运行方式由 Agent 按实际目标决定。旧测试和 [验证记录](docs/validation.md) 只保留历史结果，不要求复用或必跑。

## 复制后交给 Agent 的首条指令

> 请阅读当前目录的 INITIALIZE.md，按照其中的初始化指令完成这台电脑的 HarnessUI 配置与能力补全。

目标电脑的具体路径和脚本实现由该电脑的 Agent 处理，不把脚本占位或 HTML 占位当成已经实现的能力。
