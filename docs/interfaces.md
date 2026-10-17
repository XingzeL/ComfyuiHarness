# 最小模板接口

本文描述最初提供的公共参考运行器。新增工作流按 [工作流管理规则](workflows.md) 使用自己的 api.py / run.py / workflow_builder.py；本页的 workflow.spec.json、SaveImage 限制及五命令不是项目对所有工作流的要求。

## CLI 与配置

入口 `python -m harnessui`。全局参数：`--root`、`--env`、`--registry`；子命令为 `inspect`、`build`、`submit`、`status`、`collect`。输出 JSON；发现依赖错误、执行失败、未知状态或收集验证失败时退出码为 1。排队/运行中的 status 是成功查询，退出码为 0，但不是成图成功。

`inspect` 可不带任务，此时只发现环境；`build/submit` 必须传 `--task`；`status/collect` 必须传 `--run`。

环境必填 `base_url`，可选 `timeout_seconds`。不隐式读取系统代理、不保存 URL 凭据；首版本地服务无鉴权。如果目标环境需要代理或认证，显式扩展 transport 并从环境变量读取秘密，不把值写入 manifest。

正式 submit 还需已确认的 `limits.max_image_pixels`，缺失/null 提醒并暂停。Python submit 可用 environment=env 显式传入环境配置；未传时读取 root/config/environment.local.json。CLI 使用 --env 选中的配置。build 和只读 inspect 不要求已确认预算，不代表预算检查已通过。

任务 JSON 只有 `workflow` 与 `parameters`。参数键来自工作流描述，未知参数报错，不静默忽略。资源值使用登记 ID，图像值使用包内相对路径。

## 工作流描述

每个工作流目录包含 `workflow.json`、`workflow.spec.json` 和说明。描述含：

- `id`：与目录名一致。
- `family`：资源基底体系。
- `template`：相对当前目录的 API 图文件。
- `outputs`：全部标准 SaveImage 节点 ID，必须为字符串。
- `parameters`：名称到参数定义的映射。

参数定义使用 `type`（string/integer/number/boolean）、可选 `default`、`min/max/choices`、`resource_kind`、`image`、`random_seed`。未提供默认值的参数必须在任务中填写。`random_seed` 配合空默认值用于生成整数种子。

每个参数的 `targets` 是非空列表，元素为 `node`、`class_type`、`input`。同一参数可同步多个输入；不同参数不能争用同一输入。只覆盖已有字面值输入，不能通过参数覆盖图连接。复杂重接线由专用适配或新工作流承担。

`resource_kind` 从资源登记解析 ID 为服务端相对名称。`image: true` 在 build 时只验证本地图并记录摘要，在 submit 中快照、上传并替换为服务返回的图像名。内置示例不依赖上传，但运行库和测试覆盖此机制。

在线验证以 `/object_info` 返回的节点输入输出为依据。支持传统基本类型、枚举和连接；自定义动态字段、不透明值类型与特殊输出需要适配，不能声称通用转换器已支持。

## Python API

```python
from pathlib import Path
from harnessui.client import Client
from harnessui.core import read_json, build, inspect_service, submit, status, collect

root = Path.cwd().resolve()  # 调用方明确指定包根
task = read_json(root / "examples/task.basic.json")
registry = read_json(root / "resources/registry.local.json")
env = read_json(root / "config/environment.local.json")
client = Client(env["base_url"], env.get("timeout_seconds", 30))
built = build(root, task, registry)             # 离线，不写文件
report = inspect_service(client, built)        # 在线只读；枚举路径可能规范化
# 以下仅在任务已获授权、环境核对完成后执行
result = submit(root, task, registry, client, environment=env)  # 检查 execution_status 和 prompt_id
```

`submit` 的参数构建错误会抛出异常；开始记录 run 后的网络或提交错误返回带失败状态的 manifest。调用方必须检查状态，不能把函数返回当作成功。

`status(root, run_id)` 更新执行状态；`collect(root, run_id)` 仅在成功执行后收集。未完成或历史不足时抛出 HarnessError；实际收集问题记录在 manifest 中。

## 记录与扩展

manifest 保存运行 ID、原服务地址、client_id、prompt_id、有效参数、所用资源、输入摘要、图摘要、状态及实际输出。`prompt.json` 是最终提交的图，`workflow.spec.json` 是当时映射快照。

自定义处理放在对应工作流目录，保留任务记录与输出约定。不要把 WD14、特定 Power LoRA 布局或模型特例硬编码进公共客户端。测试脚本按当前任务需要生成到 test/，不固定方法。
