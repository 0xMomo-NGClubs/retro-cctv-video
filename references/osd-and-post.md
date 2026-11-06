# 固定机位与 OSD

从原始分辨率参考帧测量字样的占屏比例、字号比、间距、位置、轮廓和软化程度，不只看放大的播放器截图。

验证过的起点：854×480透明层，VCR OSD Mono的数字/英文采用16×24字格，GNU Unifont中文采用24×24字格；一像素黑轮廓、略灰白字、0.45原生像素软化，再双线性放大叠回成片。不宣称已识别出参考片完全相同的字体。

只软化字层，不自动加扫描线、噪点、闪烁、恐怖片效果或摄像头抖动。参数按参考与输出尺寸调，数字全用同一字体和字格，不单独把某几位放大。

```bash
python scripts/fetch_fonts.py --out project/work/fonts
```

包内不含字体二进制。下载器校验已验证文件SHA-256，内容变化时检查来源后再更新清单。不会安装系统字体，也不静默回退到其他字体。

## 配置

路径相对配置文件，见 `assets/postprocess.example.json`。

- `segments[].file` 为无字素材。`start_seconds` 与 `frames` 或 `duration_seconds` 控制区间；省略长度用可用视频长度。
- `output` 统一尺寸/FPS、CRF与 `fit=contain`（默认保留整个画面）或明确的 `cover`（统一画幅归一化）。没有逐镜变焦参数。
- `osd.font_dir/native_size` 指字体目录与字层原生尺寸；画幅需匹配。长文本统一缩小整行，不单独拉伸某些数字。
- `osd.date` 可选ISO日期，跨日递增；负年份等用 `date_label`。省略日期只显示时钟。
- `osd.start_time` 是 HH:MM:SS，支持跨分钟/小时。`date_label` 模式跨日时会提示人工核对日期。
- `osd.camera/place` 固定；多机位先明确规划，再每个固定机位分别配置渲染。
- `audio.mode=copy` 复制与整片等长的同步premix，并验音频码流哈希；明显过长或过短均先处理混音，不截短视频。
- `audio.mode=segments` 裁剪并拼各段声音，默认边界30ms淡入淡出；跨切镜完整台词用事先制作的premix。最终AAC可配峰值限制。

每段归一化为无损中间文件，copy拼接后最后叠字。1fps OSD用 `eof_action=repeat:shortest=0`，否则非整秒尾部可能提前结束。导出核对预期总帧数、时长与音频哈希，不只看退出码。

## 来源

- [海康威视OSD参数](https://open.hikvision.com/hardware/structures/NET_DVR_PICCFG_V30.html)：固定字格、日期、黑白显示与对齐。
- [VCR OSD Mono作者发布页](https://www.dafont.com/vcr-osd-mono.font?sort=date)：Riciery Leal，Bitmap、100% Free；本包不再分发字体文件。
- [GNU Unifont官方](https://unifoundry.com/unifont.html)：双宽位图字形、OFL及带嵌入例外的GPL授权。

这些资料说明素材和方法，不代表所有监控设备使用同一字体或参数。
