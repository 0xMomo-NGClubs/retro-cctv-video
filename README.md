# Retro CCTV Video · 老监控视频制作 Skill

把历史事件或虚构故事做成“固定摄像头偶然拍到”的老监控短片：人物有合理动机，道具数量连续，动作看得到发力，时间地点字样带低分辨率点阵的柔化感。

**它是一套可更换生成服务的制作流程。** 默认参考RunningHub上的MiniMax H3图像参考工作流，也可以结合Seedance等模型的提示词转换Skill，再交给自己选择的插件、SDK或API生产。没有强制指定的Seedance服务商或API地址。

## 流程

`参考拆解 → 因果/比例检查 → 人物与道具参考 → 模型提示词转换 → 视频生产 → 局部返修 → 固定全景/OSD后期 → 验收`

这套方法来自多轮实际返修：人物过大导致困境不成立、救援直接跳到答案、石头数量变化、破碎像泡沫、动作像轻碰，以及后期拉近镜头破坏监控感。经验被整理为通用检查点，没有把儿童、水缸、某个年代或固定分段数写成所有故事的要求。

核心做法：

- 先写“触发/尝试→动作→接触→结果”，把思考和慌张变成远景可读的行为。
- 跟踪关键道具的数量、持有、接触和去向；握持连续性与身体发力分别设计。
- 默认固定全景，生成无字素材；不会为强调动作自动推近镜头。
- 在低分辨率透明字层绘制数字和中文，加黑轮廓、轻微软化后放大叠回；只软化字层。
- 修失败片段，复用通过素材。只改字样或颜色时不重新生成视频。

## 安装与调用

将本仓库文件放入支持`SKILL.md`的运行环境。Codex可安装到`~/.codex/skills/retro-cctv-video`：

```bash
git clone https://github.com/0xMomo-NGClubs/retro-cctv-video.git ~/.codex/skills/retro-cctv-video
```

目录已有同名Skill时先备份或检查，不要覆盖自己的修改。在新对话中调用：

> 用 $retro-cctv-video，把“一个人搬重箱子”的故事做成老监控短片，固定全景，时间和地点用柔化点阵字样。

> 用 $retro-cctv-video，复用现有视频，只调整监控时间和地点的字号与模糊程度。

> 用 $retro-cctv-video，保留老监控导演方案，结合我已有的Seedance提示词转换Skill，再用我选择的生成工具生产。

## 生成服务如何替换

| 路线 | 本包提供 | 使用者需要准备 |
| --- | --- | --- |
| 默认示例：RunningHub / H3 | 六段提示词指导、API图检查/裁剪、一次提交与恢复查询CLI | 自己可用的API格式图、节点映射、账户凭证和生成额度 |
| Seedance 2.0 / 2.5等可选模型 | 通用制作单、提示词Skill协作与生产交接指导 | 对应版本的转换器或当前文档、自己选择且实际支持该模型的执行工具 |
| 其他模型/本地或云端工具 | 因果、连续性、固定机位规则，以及同一套后期 | 对应模型提示词、可用生成工具或实际API适配 |
| 仅本地后期 | 黑白归一化、无损中间拼接、OSD、音轨与文件校验 | 已有无字视频和字体缓存 |

`sd25-pe`、`seedance-2-5-video-director`等仅是可选转换Skill名称示例，不随本仓库分发，也不自动安装。转换器负责文本；API执行层负责生成。具体版本、能力、参数和地址以使用者选定工具为准。

本包自带生产客户端只实现RunningHub/H3 T8图像参考示例，**没有内置任意服务的通用API客户端，也没有内置Seedance客户端**。配置模板里的空值需要按自己的实际环境填写。

## 本地脚本

需要Python 3.10+、FFmpeg/ffprobe。后期依赖Pillow，示例RunningHub客户端依赖requests；创建任务需要用户已授权的视频生产范围。RunningHub状态锁脚本面向macOS/Linux。

在独立项目目录准备环境与素材；不要把凭证、缓存或输出放进本仓库：

```bash
# 在仓库目录中执行；请把下面路径改为自己的项目目录。
PROJECT_DIR=../cctv-project
SKILL_DIR="$PWD"
mkdir -p "$PROJECT_DIR"
python3 -m venv "$PROJECT_DIR/.venv"
. "$PROJECT_DIR/.venv/bin/activate"
python -m pip install -r "$SKILL_DIR/requirements.txt"
cp "$SKILL_DIR/assets/postprocess.example.json" "$PROJECT_DIR/postprocess.json"
python "$SKILL_DIR/scripts/fetch_fonts.py" --out "$PROJECT_DIR/work/fonts"
# 准备clips素材，并修改postprocess.json中的片段、字样和音轨配置。
python "$SKILL_DIR/scripts/cctv_post.py" render \
  --project "$PROJECT_DIR/postprocess.json" \
  --out "$PROJECT_DIR/outputs/final.mp4" --work "$PROJECT_DIR/work/post"
python "$SKILL_DIR/scripts/cctv_post.py" verify "$PROJECT_DIR/outputs/final.mp4"
```

详细说明：[Skill主流程](SKILL.md)、[模型转换与执行](references/generation-routing.md)、[OSD方法](references/osd-and-post.md)、[H3示例适配](references/h3-and-runninghub.md)、[验收标准](references/acceptance.md)。

## 测试与当前边界

```bash
# 不访问网络、不需要服务密钥、不提交生成任务。
python scripts/test_skill.py -v
# 提供已下载的字体缓存，才能同时运行字体相关测试。
CCTV_TEST_FONT_DIR=../cctv-project/work/fonts python scripts/test_skill.py -v
```

未指定字体目录时会明确跳过字体测试。已有验证覆盖13项离线回归；现有素材重建验证了1280×720、24fps、896帧和37.333333秒完整片尾、完整解码与复制音轨哈希一致；合成素材验证了缺音轨补静音和非整秒片尾。

RunningHub实际API图做过离线编译；新封装CLI没有额外做付费端到端验证。Seedance及其他服务当前提供协作指导，未宣称完成这些路线的付费测试。模型仍可能生成物理或人物连续性错误，需要看片验收。

## 注册入口 / 支持作者

- [RunningHub 注册入口（作者推荐/邀请链接）](https://0xmomo.com/rhai)

这是作者提供的拉新/邀请入口，可能关联平台邀请奖励或推广归因。不承诺折扣、赠额或生成效果；是否产生奖励以平台实际规则为准。使用链接完全自愿，不影响Skill功能；也可自行访问服务。该链接不是API地址，脚本不会自动访问它或附带它上传素材。

## 隐私、素材与发布

- 不提交密钥、Cookie、`.env`、私有工作流、任务回执、签名下载链接、本机绝对路径或用户原片；示例均为通用配置。
- 上传素材只发生在使用者选择的生产服务中；请使用有权使用的人物、场景、字体、音频和参考素材。包内不含原案例视频、截图或人物素材。
- 本仓库是虚构/重演内容制作工具；不要把生成视频冒充真实监控、新闻证据或取证材料。发布时遵循适用的平台生成内容标注要求，不去除第三方权利标识。
- 画内OSD与发布时的生成内容披露分别处理；不强制给每帧加额外说明，也不承诺可以省略应有标识。
- 注册链接位于README推广说明中；没有追踪代码、遥测或强制跳转。

本仓库代码与文档使用[MIT许可](LICENSE)。第三方软件、字体、外部Skill和生成服务不由本仓库重新授权，见[第三方说明](THIRD_PARTY_NOTICES.md)。
