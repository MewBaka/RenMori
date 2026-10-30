# RenMori

**面向商业 Ren'Py 视觉小说的全量数据保护工具**

RenMori 是一套「构建期工具 + 原生运行时」，输入一个已经构建好的 Ren'Py 8.x 发行版，输出受保护的发行版。游戏中的每一项数据——脚本、立绘、CG、音频、视频、字体、翻译与配置——都会被封入加密容器，仅在运行中的引擎内部解密。目标有二：让常见的解包与反编译工具、以及只会调用它们的 agent 直接失败，并让每次构建各不相同，使得没有任何单一解包器能够跨游戏通用。

> **状态**——1.0 之前。保护体系已构建并验证；设计见 [docs/architecture.md](docs/architecture.md)，当前进度见下方[路线图](#路线图)。

English version: [README.md](README.md)

---

## 它能挡住什么，又挡不住什么

请先读这一段。在玩家机器上运行的游戏，永远无法做到不可破解。引擎要运行就必须能读取自身的数据，因此密钥与解密逻辑随游戏一同下发，而屏幕内容也始终可被录制。任何本地内容保护最终都曾被攻破，RenMori 不作相反的宣称。

RenMori 真正提供的是：

- 现成工具失效——`unrpa`、`rpatool`、`RenPack`、`RenpyEx` 以及 `unrpyc`（含 `--try-harder` 与注入式反编译）对受保护的构建均无效，这挡住了绝大多数提取尝试，因为它们不过是有人在运行这些工具
- 破解不可迁移——每次构建采用不同的容器布局、脚本编码与密钥派生，因此逆向一款作品只会得到针对该作品、该版本的工具，而非通用解包器
- 磁盘上任何时刻都不存在明文，字体亦然

若威胁模型要求阻止一名坚定且熟练的攻击者提取哪怕一项数据，任何客户端工具都无法做到。RenMori 将破解成本抬高到"针对单一作品、单一版本的专家级投入"，这已足以使绝大多数游戏不值得被破解。

## 设计优先级

以下按先后排序，低优先级让位于高优先级：

- 性能优先——任何与运行时性能冲突的保护手段都会被舍弃；默认不使用任何重型加壳或虚拟化保护，加密采用硬件加速的原生实现，完整性校验仅在启动时进行一次而不进入热路径，因此受保护的构建在帧时间、场景切换与 CG、视频播放上与未受保护者无从分辨
- 对开发者与 CI 友好——面向标准 Ren'Py 发行版构建的单条命令、明确的退出码、经文件或环境变量进行的配置，以及一份 GitHub Actions 示例工作流，且无需改动游戏源码
- 保护强度——主要经由零运行时开销的逐构建多态实现，而非依赖运行时加固

## 工作原理

保护分四层施加：

| 层 | 所做之事 |
|----|----------|
| 资源层 | `game/` 下的每个文件被封入加密容器以取代 RPA；一个原生模块接管 `renpy.loader`，返回已解密的流式文件对象，大体积视频与音频按偏移分块解密，而非整体读入内存 |
| 脚本层 | 已编译脚本改用自定义 AST 格式以取代标准 `.rpyc`，并逐构建重映射类名与字段，使基于 pickle 的反编译器无法还原，内嵌 Python 则经编译并加密 |
| 引擎层 | 仅加载构建期签名的脚本，丢入游戏目录的外来 `.rpy` 或 `.rpyc` 一律拒绝加载，从而阻断注入式反编译；发行版构建中关闭开发者控制台与数据导出子命令 |
| 启动器层 | 原生的各平台启动器先行运行，在运行时派生密钥并启动引擎，磁盘上不存放明文密钥 |

完整设计见 [docs/architecture.md](docs/architecture.md)，诚实的威胁模型见 [docs/threat-model.md](docs/threat-model.md)。

## 使用

```bash
renmori protect ./dist/MyGame-1.0-pc -o ./dist/MyGame-1.0-pc-protected
renmori verify  ./dist/MyGame-1.0-pc-protected
```

该命令默认零配置，具备明确的退出码与供 CI 解析的 JSON 结果行。可选的 `renmori.toml` 用于控制分块大小、排除清单、锁定、强度与密钥来源。`protect` 会输出 `renmori-manifest.json`，列出受保护文件与容器指纹，`verify` 则据此复核一个构建。完整参考见 [docs/usage.md](docs/usage.md)，另见 [docs/ci.md](docs/ci.md)、[docs/steam-release.md](docs/steam-release.md) 与 [examples/renmori.toml](examples/renmori.toml)。

开箱即用时该工具采用基线格式。完整保护——逐构建多态、运行时密钥派生、原生核心与原生启动器——由闭源插件提供，`renmori protect` 在其存在时会自动发现并驱动它，二者之间的契约见 [docs/interface.md](docs/interface.md)。

## 平台

目标平台为 Windows、macOS 与 Linux / Steam Deck：

- Steam——Steam 悬浮窗会注入游戏进程，因此被显式放行，反篡改也保持最小化；请勿再额外套用 Steam 自带的 DRM；成就与云存档走 Ren'Py 常规 API，不受影响——见 [docs/steam-release.md](docs/steam-release.md)
- macOS——RenMori 仅解密数据、从不执行解密得到的代码，因此无需硬化运行时授权，也不会迫使你进行付费签名，并且无需公证；Apple Silicon 至少需要 ad-hoc 签名方可运行，构建工具会自动完成，而持有 Developer ID 的构建仍可重新签名并公证

## 开核模型

RenMori 采用开核模式：框架免费且开放，而真正需要保密的部分闭源。

- 开放部分，即本仓库——命令行工具、`renpy.loader` 钩子框架与运行时 SDK、基线容器格式规范、标准加密原语的调用、CI 集成、文档、示例与测试；可单独使用，提供基线强度
- 闭源部分，以预编译插件形式由开放工具调用——多态引擎、密钥派生逻辑与反篡改运行时，它们才是阻止通用解包器的关键；多态引擎永不下发给玩家，因此将其闭源才是保密真正有意义之处

开放工具与闭源插件经由一套稳定且有文档的进程接口通信（[docs/interface.md](docs/interface.md)）；接口开放，实现闭源。

## 许可

RenMori——框架与工具、闭源插件，以及随游戏下发的运行时——适用 RenMori 许可证（[`LICENSE`](LICENSE)；中文 [`LICENSE.zh-CN.md`](LICENSE.zh-CN.md)）。使用 RenMori 保护任何 Ren'Py 游戏（含商业游戏）均免费，RenMori 运行时亦可随已发行游戏嵌入再分发，不收取费用。禁止出售 RenMori 本身或其修改版本，也禁止以其运营收费加密服务。这是一份源可见许可证，而非 OSI 开源许可证，因为"禁止转售"这一条无法在宽松许可证下表达。

第三方声明见 [`NOTICE`](NOTICE)，其中 FFmpeg 的 LGPL 与 GPL 条款尤需留意。不对"不可破解"作任何担保；详见许可证与 [docs/threat-model.md](docs/threat-model.md)。

## 路线图

- [x] **M0**——文档，位于本仓库 `docs/`
- [x] **M1**——资源层概念验证（容器、加载器钩子、加密后端），在 Ren'Py 8.5.2 引擎内验证逐字节一致——见 [docs/m1-results.md](docs/m1-results.md)
- [x] **M2**——击败 `unrpyc` 与 `rpycdec` 的脚本变换、注入阻断与发行版锁定——见 [docs/script-layer.md](docs/script-layer.md)
- [x] **M3**——命令行与 CI 集成：`renmori.toml`、`--exclude`、环境变量密钥来源、`verify` 命令、退出码与 GitHub Actions 示例——见 [docs/ci.md](docs/ci.md)
- [x] **M4**——逐构建差异化、跨平台 `.rpe` 路径、Steam 保障与 `renpy.exists` 回退——见 [docs/m4.md](docs/m4.md)
- [x] **闭源栈**——多态引擎、运行时密钥派生、原生核心与原生启动器，已在真实 Ren'Py 引擎上于 Linux（CI）与 macOS 验证，并由开放工具经既定接口驱动闭源插件
