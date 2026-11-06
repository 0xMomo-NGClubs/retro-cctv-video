# 第三方说明

本仓库只分发自身代码、文档和通用JSON示例，不携带第三方字体、视频、模型、外部Skill、FFmpeg可执行文件或Python依赖。MIT许可不覆盖这些独立资源。

| 项目 | 使用方式与出处 | 授权边界 |
| --- | --- | --- |
| VCR OSD Mono，Riciery Leal | 运行`fetch_fonts.py`时，从[作者发布页对应下载](https://www.dafont.com/vcr-osd-mono.font)下载到使用者的项目缓存 | 作者页面标注“100% Free”；本包不把该标注解释为任意再分发授权，不打包字体。需要再分发时自行核实。 |
| GNU Unifont | 从[官方站点](https://unifoundry.com/unifont.html)下载指定版本的位图字形到项目缓存 | 参阅[官方许可文件](https://unifoundry.com/LICENSE.txt)和实际下载版本中的许可；源码与字体存在不同许可安排，不由本仓库改成MIT。 |
| Pillow / requests | 使用者通过`requirements.txt`安装 | 适用各项目随包提供的许可，不把依赖源码复制进本仓库。 |
| FFmpeg / ffprobe | 调用使用者本机安装的程序 | 授权依其实际构建及配置而定，本仓库不分发可执行文件。 |
| 模型、服务与外部提示词Skill | 可选使用者已安装或自行接入的工具 | 按各自条款使用；只引用名称与协作边界，不复制其他Skill的正文或私有工作流。 |

字体获取脚本对下载字节做SHA-256校验，用于发现缓存损坏或上游变化；校验通过不替代授权核实。模型名称用于描述兼容的制作路线，不代表官方合作、认证或效果保证。
