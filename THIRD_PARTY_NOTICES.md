# 第三方组件声明 / Third-Party Notices

Wallpaper Peel 的分发版本（`WallpaperPeel.exe`）由 PyInstaller 打包而成，内部包含下列第三方组件。
各组件的著作权归其作者所有，并按各自许可证分发。

---

## 1. Python 3.13

- 项目：https://www.python.org/
- 许可证：PSF License Agreement
- 版权：Copyright © 2001–2026 Python Software Foundation. All rights reserved.
- 全文：https://docs.python.org/3/license.html

## 2. Pillow 11.3.0

- 项目：https://python-pillow.org/
- 许可证：HPND（Historical Permission Notice and Disclaimer，MIT 风格）
- 版权：Copyright © 2010–2026 by the Pillow contributors；
  Copyright © 1995–2011 by Secret Labs AB；Copyright © 1995–2011 by Fredrik Lundh
- 用途：生成缩略图、预览缩放
- 全文：https://github.com/python-pillow/Pillow/blob/main/LICENSE

HPND 允许复制、修改与再分发（含二进制形式），条件是保留上述版权声明与本许可声明。
本文件即用于满足该条件。

## 3. PyInstaller 6.22.3

- 项目：https://pyinstaller.org/
- 许可证：GPL 2.0 **并附带特殊例外（Bootloader Exception）**
- 版权：Copyright © 2010–2026 PyInstaller Development Team
- 全文：https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt

该例外明确允许将本程序打包后的可执行文件以任意许可证分发（本项目采用 MIT）。
引导程序（bootloader）本身仍为 GPL 2.0。

---

## 仅在构建期使用、不随分发包提供的组件

以下组件只在开发/打包时使用，不会包含在 `WallpaperPeel.exe` 中：

- `pywin32-ctypes`、`altgraph`、`pefile`、`pyinstaller-hooks-contrib`、`packaging`、`setuptools`

## 未使用的第三方内容

本项目**不包含**任何 Wallpaper Engine 的代码、素材或壁纸文件。
程序只读取用户本机已存在的 `scene.pkg` 文件并解出其内部数据；不包含、不下载、不分发任何壁纸作品。

Wallpaper Engine 是 Kristjan Skutta 的商标。本项目为第三方独立工具，与 Wallpaper Engine 官方无任何关联，也未获其背书。

---

本项目的自身代码以 MIT 许可证发布，见 [LICENSE](LICENSE)。
