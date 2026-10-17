# 本机服务脚本

固定入口：start_comfyui.py、stop_comfyui.py、restart_comfyui.py、status_comfyui.py。脚本名说明功能，位置不变；实现由目标电脑的 Agent 根据实际 ComfyUI 配置生成或替换。

当前四个文件是明确返回未配置的占位脚本，退出码为 2，不会启动或结束进程。不能将占位入口存在视为服务管理已完成。完成实现后更新本文件的配置状态。

## 在目标电脑补齐

读取实际安装位置、Python 环境、启动方式、服务地址和日志位置，结合 config/environment.local.json 填充脚本。保留现有的本机启动方式，不复制原电脑盘符或凭据。

- start：启动当前配置对应的 ComfyUI，等待 HTTP 就绪；已经就绪时避免重复启动。
- stop：只停止本配置对应的服务，不能按名称终止所有 Python 进程。
- restart：检查运行/排队任务及影响，停止、启动并确认就绪；不能在异步提交返回后立即中断新任务。
- status：检查服务可达和就绪状态，报告结果。

脚本输出可读结果或 JSON，已实现后成功退出 0、失败退出非零。需要操作服务时由 Agent 调用这些功能入口，或由工作流 API 按自身运行规则调用；不要把某个工作流的特殊重启频率写成所有脚本的全局行为。

黑图恢复遵守 docs/tasks.md：同一失败任务最多三次恢复重启。服务脚本本身不再套一层无限重启循环。

## 其他已预留的功能入口

- `preflight_submit.py`：投递前检查服务、依赖、最近输出及 limits.max_image_pixels；上限未确定时提醒用户并暂停投递。
- `check_outputs.py`：结果检查、黑图识别及恢复记录。
- `collect_outputs.py`：将确认有效的成图汇总到 Grokbot/output，避免覆盖。

以上三个脚本目前返回 unimplemented、退出码 2，目标电脑 Agent 根据工作流补齐；没有统一规定复杂的参数协议。可复用模块已有检查逻辑，不要求复制另一套实现。现有模块仍使用自身预检和保存逻辑，不会因为占位文件存在就自动调用它们。

LoRA 清单与 HTML 刷新入口放在 loraInfo/_gen_catalog.py、loraInfo/_gen_catalog_html.py，沿用原项目位置和名称，同样待目标电脑实现。
