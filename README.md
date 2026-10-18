# Wallpaper Peel

从 **Wallpaper Engine** 的创意工坊壁纸里，把作者上传的**原始贴图**剥出来 —— 分辨率就是作者原图，不受显示器分辨率和 Windows 缩放影响，也不经过任何二次压缩。

> Wallpaper + Peel：把壁纸从 `scene.pkg` 的壳里"剥"出来。

<p align="center">
  <img src="app_preview.png" width="180" alt="Wallpaper Peel icon">
</p>

## 为什么用它

对着桌面截屏保存壁纸，最多得到屏幕分辨率的图，而且会被 150% 缩放和 JPEG 压缩搞糊；
创意工坊自带的 `preview.jpg` 只是 1024×1024 的方形缩略图，根本不能当壁纸。

Wallpaper Peel 直接解析 `scene.pkg` 的容器结构，把里面**原封不动的 JPEG / PNG 码流**取出来 —— 作者传了 4K 就是 4K。

## 功能

- 自动定位 Wallpaper Engine 壁纸库（读 `config.json`，也支持手动指定目录）
- 画廊式浏览已安装的壁纸，显示真实分辨率、文件大小、类型
- 勾选导出（`Ctrl+A` 全选 / `Esc` 清空 / 只看 4K / 按类型筛选）
- 视频类壁纸直接原样拷贝 `.mp4`，零损失
- 一键「设为桌面背景」，不用手动右键

## 使用

### 直接运行 exe

到 [Releases](../../releases) 下载 `WallpaperPeel.exe`，双击即可：会弹出一个命令行窗口并自动打开浏览器页面。

> 首次运行若提示「Windows 已保护你的电脑」，点「更多信息」→「仍要运行」。
> 用完关掉命令行窗口即停止服务。

### 从源码运行

```bash
pip install pillow            # 可选，仅用于生成缩略图
python wallpaper_peel.py
```

不带 Pillow 也能跑，只是缩略图会直接使用原图，首屏加载会重一些。

### 打包成单文件 exe

```bash
pip install pyinstaller pillow
pyinstaller --noconfirm --clean --onefile --console --name WallpaperPeel ^
  --icon app.ico --add-data "web;web" wallpaper_peel.py
```

## 它到底做了什么

Wallpaper Engine 的场景类壁纸把资源打包在 `scene.pkg` 里，容器结构很简单：

```
int32  magicLen(8)  +  "PKGV00xx"
int32  entryCount
entry*: int32 pathLen + path + int32 offset + int32 length
                       ↑ 数据区紧接目录之后，offset 相对数据区起点
```

里面的 `.tex` 又是：

```
"TEXV0005" + "TEXI0001" + 7×int32(格式/标志/宽/高…) + "TEXB0003|0004"
                                                          ↓
                                        之后直接就是 JPEG 或 PNG 原码流
```

所以不需要解码 LZ4 或 BC/DXT —— 按 `FF D8 FF … FF D9`（JPEG）、`89 50 4E 47 … IEND`（PNG）把码流抠出来即可，得到的就是作者原图。
（`PKGV0014 ~ PKGV0023` 都验证过。）

## 已知限制

- 场景壁纸是**多层实时渲染**的 3D/2.5D 场景，导出的只是其中**分辨率最高的那一层**，通常就是画面主图
- 少数壁纸是分层素材（背景层 + 主体层分开），导出的可能只是背景层
- 部分壁纸作者上传的原图本身就低（720p 甚至更低），那不是提取的问题

## 免责声明

仅供个人备份自己已订阅壁纸之用。壁纸版权归原作者所有，请勿用于商业用途或二次分发。

## License

MIT
