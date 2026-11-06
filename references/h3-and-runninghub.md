# 可选示例：H3 与 RunningHub

仅在选择这条默认示例路线时使用本参考与对应CLI。其他模型按 `generation-routing.md` 转换，不要求使用此图或固定节点。

## 提示词

保留六段顺序，正文英文、对白原语言：

1. `subject_definitions`：人物、物体、环境、每张图的职责。
2. `summary`：`[reference generation]` 加本段具体目标；图片确为起始帧时可加 `keyframe completion`。
3. `retention_analysis`：对象在哪个Shot使用，哪些身份/比例/位置保留，哪些状态允许变化。
4. `detailed_description`：`[Shot 1]` 固定机位、起姿、按顺序发生的动作、接触、结果与最终状态。避免无必要切镜和电影运镜。
5. `overall_soundscape`：现场环境、脚步、衣料、接触、冲击、流水、呼吸，同步可见事件。
6. `non_diegetic_music`：默认 `N/A`，用户指定音乐时照办。

`<Picture N>` 与实际上传图一一对应；`<Subject N>`是对象定义，不是新图槽位。说话者用稳定 `(S1)` ID，台词如 `<d>[Chinese] 台词</d>`。时间地点留给后期，生成无字素材。

## 图适配

编译器面向API格式图和 `MiniMaxH3AudioConditioningT8` 图像参考约定。实际填写：

- `bindings.prompt/duration/seed` 的节点、字段与可选预期类。
- `image_bindings` 图片加载节点，顺序对应图片。
- `conditioning_nodes` 全部参与条件节点；双采样低/高两段都更新。
- `output_nodes` 只保留本次收费输出分支。
- `result_node` 明确下载的视频节点。
- `overrides` 经核实的参数覆盖；API枚举不能照填UI显示名。

编译会清理模板图像/视频槽、重建本次图片引用、从输出回溯裁图，并拒绝未绑定却仍参与的媒体加载器。它不是所有H3插件和模式的通用适配器。

时长、参考数量、取整、分辨率、采样计划与实例以实际图/账户为准。曾有图用 `5+17n` 帧，但不能推广；导出按实际帧数剪辑，不能把请求6秒当成实际一定6秒。

## 状态和恢复

```bash
python scripts/rh_workflow.py fetch --workflow-id NUMBER --out project/work/workflow.private.json
python scripts/rh_workflow.py inspect --workflow project/work/workflow.private.json
python scripts/rh_workflow.py compile --project project/runninghub.json --shot S001 --out project/work/S001-dry.private.json
python scripts/rh_workflow.py submit --project project/runninghub.json --shot S001 --state project/work/S001-state.private.json
python scripts/rh_workflow.py poll --project project/runninghub.json --shot S001 --state project/work/S001-state.private.json --download project/work/S001.mp4
```

凭证仅从 `RUNNINGHUB_API_KEY` 环境读取，地区用配置 `base_url` 或 `RUNNINGHUB_BASE_URL` 选择官方 `.ai`/`.cn`，不自动换区。

已知任务可以重复查；成功文件验哈希后复用。同一状态文件加锁防重复提交，输入指纹变化需新状态文件。超时、HTTP5xx或成功无taskId保存 `SUBMISSION_UNKNOWN`，不重发。查平台历史确认后绑定：

```bash
python scripts/rh_workflow.py attach --project project/runninghub.json --shot S001 --state project/work/S001-state.private.json --task-id CONFIRMED_NUMBER
```

只绑定确认属于当前输入的任务。已知失败先定位修正，当前授权范围内的新尝试使用新状态文件并保留旧回执。CLI没有自动收费重试。

并发占完整提交、排队、执行、下载周期。未核实权限时顺序运行；用户给定或账户确认后，可用不同状态文件并行，不把示例数当账号权限。

官方参考：[API格式](https://www.runninghub.ai/runninghub-api-doc-en/api-425761094)、[任务状态](https://www.runninghub.ai/runninghub-api-doc-en/api-425761033)、[任务输出](https://www.runninghub.ai/runninghub-api-doc-en/api-425761034)。静态编译不证明新图已做付费端到端测试。
