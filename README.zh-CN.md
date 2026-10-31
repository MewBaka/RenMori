<div align="center">

![LOGO](assets/logo/renmori-protector.png)

![Static Badge](https://img.shields.io/badge/For-RenPy-orange?style=for-the-badge&logo=RenPy) ![Static Badge](https://img.shields.io/badge/License-RenMori_License-orange?style=for-the-badge) [![官网](https://img.shields.io/badge/%E5%AE%98%E7%BD%91-renmori.mewbaka.cn-orange?style=for-the-badge)](https://renmori.mewbaka.cn/) [![English](https://img.shields.io/badge/README-English-lightgrey?style=for-the-badge)](README.md) ![简体中文](https://img.shields.io/badge/README-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-orange?style=for-the-badge) [![日本語](https://img.shields.io/badge/README-%E6%97%A5%E6%9C%AC%E8%AA%9E-lightgrey?style=for-the-badge)](README.ja.md) ![GitHub Repo stars](https://img.shields.io/github/stars/mewbaka/renmori?style=for-the-badge) ![PyPI Downloads](https://img.shields.io/pypi/dm/renmori?style=for-the-badge)

**面向商业 Ren'Py 视觉小说的全量数据保护工具，100% 免费** 

RenMori 支持 Ren'Py 8.x 构建的游戏并为其输出受到保护的发行版，游戏中的每一项数据——脚本、立绘、CG、音频、视频、字体、翻译与配置——都会被封入加密容器，仅在运行中的引擎内部解密。在玩家机器上运行的游戏永远无法做到不可破解，RenMori 最大限度保证了破解难度，保证现有解包脚本以及大部分懒 Agent 无法破解。但无法抵御专家级别的逆向，诚实的威胁模型请 [点击此处查看](https://renmori.mewbaka.cn/technical/threat-model)

</div>

---

## 一、安装与使用 CLI

### 安装

```bash
pip install renmori
renmori --version
```

开发者机器上需要 **Python 3.9+**（读取 `renmori.toml` 配置需要 3.11+，更低版本可 `pip install tomli`），`cryptography` 会自动装上。想改源码则从源码安装：

```bash
git clone https://github.com/MewBaka/RenMori.git
cd RenMori && pip install -e .
```

### 保护游戏

1. **构建游戏**——在 Ren'Py 启动器里 *Build Distributions*，RenMori 在它的产物上运行，不碰你的源码
2. **保护构建**——输入可以是构建目录，也可以是启动器打出的 `.zip`（会自动解压）：

   ```bash
   renmori protect ./dist/MyGame-1.0-pc -o ./dist/MyGame-1.0-pc-protected
   # 或直接喂压缩包：
   renmori protect ./dist/MyGame-1.0-pc.zip
   ```

   首次完整保护会从公开 Release 下载对应平台的闭源插件、校验并缓存，无需手动安装，终端里会先征询，CI 下自动下载

3. **校验**结果（可用作 CI 门禁）：

   ```bash
   renmori verify ./dist/MyGame-1.0-pc-protected
   ```

4. **发布**——把受保护的文件夹作为发行版发出（`renmori.rmc` 与 `renmori.rpe` 一起），不要再对它跑 Ren'Py 启动器构建，那会从源码重建并丢掉保护

默认零配置，向 CI 打印一行机读的 JSON 结果，退出码明确，可选的 `renmori.toml` 控制分块大小、排除清单、锁定、强度与密钥来源，想用开源**基线**格式（无插件、完全离线）传 `--strength baseline`，完整参考见 [CLI 文档](https://renmori.mewbaka.cn/cli/overview) 与 [renmori.toml 示例](https://renmori.mewbaka.cn/cli/configuration)。

---

## 二、文档

完整文档见 **[renmori.mewbaka.cn](https://renmori.mewbaka.cn/)**，按使用流程排列的关键页面如下：

**理解它**

- [项目简介](https://renmori.mewbaka.cn/guide/introduction) —— RenMori 是什么，保护了哪些数据
- [调研](https://renmori.mewbaka.cn/technical/research) —— 市面上已有什么，以及为何需要一个新工具
- [架构](https://renmori.mewbaka.cn/technical/architecture) —— 逐层的完整设计
- [威胁模型](https://renmori.mewbaka.cn/technical/threat-model) —— 它能挡住什么，挡不住什么

**保护游戏**

- [快速开始](https://renmori.mewbaka.cn/guide/quick-start) —— 从构建产物到受保护的发行版
- [CLI 参考](https://renmori.mewbaka.cn/cli/overview) —— `protect` / `verify`、参数与输出
- [配置](https://renmori.mewbaka.cn/cli/configuration) —— `renmori.toml` 配置文件
- [插件](https://renmori.mewbaka.cn/cli/plugin) —— 基线与完整保护，以及闭源二进制

**CI 自动化**

- [CI 与密钥管理](https://renmori.mewbaka.cn/integration/ci) —— 流水线、密钥，以及 GitHub Actions 示例

**发布**

- [Steam 发行](https://renmori.mewbaka.cn/integration/steam-release) —— 悬浮窗、DRM、Steamworks

**内部与参考**

- [容器格式](https://renmori.mewbaka.cn/technical/container-format) · [loader hook](https://renmori.mewbaka.cn/technical/loader-hook) · [脚本层](https://renmori.mewbaka.cn/technical/script-layer) · [插件接口](https://renmori.mewbaka.cn/technical/plugin-interface)

---

## 三、授权

RenMori——框架与工具、闭源插件、以及随游戏一同下发的运行时——采用 **RenMori License 1.0**：[`LICENSE.zh-CN.md`](LICENSE.zh-CN.md)（英文：[`LICENSE`](LICENSE)）。

- **免费使用**——保护任何 Ren'Py 游戏（无论是否商业）都是免费的，RenMori 运行时可随已发行游戏一同再分发，不收费
- **禁止转售**——不得售卖 RenMori 本身或其二改版本，也不得用它开展收费的「代加密」服务
- 这是一份 **source-available（源码可见）** 许可，而非 OSI 开源许可，因为「禁止转售」这一条无法在宽松许可下表达

第三方声明见 [`NOTICE`](NOTICE)（注意其中 FFmpeg 的 LGPL/GPL 条款），不对不可破解作任何担保，见许可证与[威胁模型](https://renmori.mewbaka.cn/technical/threat-model)。

完整条款、提交要求与面向开发者的说明见文档站：[免责声明](https://renmori.mewbaka.cn/license/disclaimer)、[提交要求](https://renmori.mewbaka.cn/license/contributing)、[给开发者的提示](https://renmori.mewbaka.cn/license/developer-notes)。

关于此项目授权问题/技术协助，请联系邮箱：*team@mewbaka.cn*