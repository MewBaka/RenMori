English version: [steam-release.md](steam-release.md)

# 将受保护的构建发布到 Steam

RenMori 保护**已构建**的 Ren'Py 发行版构建。发布到 Steam 分为三个有序步骤，且顺序至关重要：

```
Ren'Py launcher: Build Distributions   →   renmori protect   →   SteamPipe upload
   (from your project source)              (encrypt game/)        (upload the folder)
```

> **请勿颠倒此顺序。** 若你先保护、再对项目重新运行 Ren'Py 启动器的 *Build
> Distributions*，启动器会从源码重新构建并产出一份全新的**未受保护**发行版构建——你
> 的保护便荡然无存。请保护启动器的输出，切勿将受保护的文件夹重新喂回启动器。

本教程以 SDK 示例 `the_question` 及其 **market** 构建为例，因为该包内含全部三个平台。

---

## 应上传哪个构建

Ren'Py 启动器可产出：

- **pc**——Windows + Linux
- **mac**——macOS
- **market**——一个通用包，内含共享同一 `game/` 的 Windows（`.exe`）、macOS（`.app`）与 Linux（`.sh`）启动器

两种方式在 Steam 上都可行：

| 方式 | 你需要做的 | 取舍 |
|--------|-------------|-----------|
| **Market（简单）** | 保护这一个 market 文件夹；将其放入挂载到所有操作系统的**单一 depot**；按操作系统设置启动选项 | 每位玩家都会下载全部三个平台的文件 |
| **分平台（整洁）** | 分别构建 **pc** 与 **mac**，各自 `renmori protect`，各自上传到其**专属 depot**（Windows / macOS / Linux） | 步骤更多，但每位玩家只下载其所在平台 |

RenMori 的保护与平台无关——`renmori.rpe` 加载器运行在各操作系统上 Ren'Py 自带的 Python 内——因此**对 market 构建运行一次 `protect` 即可同时覆盖 Windows、macOS 与 Linux**。

---

## 步骤 1——保护

将启动器的 market 压缩包解压到一个文件夹（RenMori 接收目录，而非 `.zip`），然后：

```bash
renmori protect ./the_question-7.0-market -o ./the_question-7.0-market-protected
renmori verify  ./the_question-7.0-market-protected
```

`game/` 发生改变；启用原生启动器（默认）时，各平台的入口点也会替换为启动器，原引擎以 `.renmori_real` 名称保留在旁；使用 `--no-launcher` 时只有 `game/` 发生改变：

```
the_question-7.0-market-protected/
├─ game/
│   ├─ renmori.rmc        # all assets, encrypted
│   ├─ renmori.rpe        # runtime loader (Ren'Py loads it automatically)
│   ├─ renmori_core-*     # native runtime, one per platform
│   └─ steam_appid.txt    # kept as plaintext (the Steam SDK reads it directly)
├─ lib/
│   └─ py3-linux-x86_64/
│       ├─ the_question               # native launcher (Linux entry point)
│       └─ the_question.renmori_real  # original engine
├─ renpy/                 # untouched
├─ the_question.app/      # Contents/MacOS/the_question is the native launcher
├─ the_question.exe       # native launcher (Windows entry point)
├─ the_question.renmori_real.exe  # original engine
├─ the_question.py
├─ the_question.sh        # untouched — Linux entry script
└─ renmori-manifest.json
```

原先位于 `game/` 下的明文 `.rpa`/`.rpyc` 已不复存在；`unrpa` 与 `unrpyc` 无从下手。

---

## 步骤 2——用 SteamPipe 上传

Steam **不**接收单个文件。一次构建是**一个文件夹的内容**，通过 SteamPipe 上传到一个 depot。因此：

- **请勿**上传 `.zip`
- **请勿**只上传 `renmori.rmc`
- **请**将 depot 的 `contentroot` 指向**受保护的文件夹**，让 SteamPipe 上传其中的全部内容（`game/`、`lib/`、`renpy/`、各启动器）

`app_build_<APPID>.vdf`：

```vdf
"appbuild"
{
  "appid"       "YOUR_APPID"
  "desc"        "the_question 1.0 (renmori protected)"
  "buildoutput" "D:\steam\output\"
  "contentroot" "D:\dists\the_question-7.0-market-protected\"
  "setlive"     ""          // upload only; set the live branch in the web UI
  "depots"
  {
    "YOUR_DEPOTID"
    {
      "FileMapping" { "LocalPath" "*"  "DepotPath" "."  "recursive" "1" }
    }
  }
}
```

```bash
steamcmd +login YOUR_ACCOUNT +run_app_build "D:\steam\app_build_YOUR_APPID.vdf" +quit
```

（Steamworks 的 “SteamPipe GUI” 做的是同一件事——你将其指向受保护的文件夹即可。）

对于**分平台 depot**，请分别保护每个平台构建，并为各自赋予带独立 `contentroot` 的专属 depot。

---

## 步骤 3——启动选项

在 Steamworks 网页后台（*Installation → General Installation → Launch Options*）中设置以下各项，每个操作系统一项，指向构建内的启动器：

| 操作系统 | 可执行文件 |
|----|-----------|
| Windows | `the_question.exe` |
| Linux | `the_question.sh` |
| macOS | `the_question.app` |

入口点（除非以 `--no-launcher` 构建，否则即原生启动器）引导 Ren'Py；`renmori.rpe` 接管加载并在内存中解密资源，两种情况下启动选项相同，玩家毫无察觉。

---

## Steam 相关要点

- **请勿与 Steam DRM 二次包装**（DRMToolkit 可执行文件包装器）——它会重写启动器二进制、可能与运行时自检冲突，且自身防护薄弱，而 RenMori 已保护数据层
- **不使用启动器时（`--no-launcher`）覆盖层（overlay）是安全的**——RenMori 仅挂钩 Ren'Py 的文件加载，从不进行进程 / DLL 注入，因此 Steam 覆盖层正常工作；使用原生启动器（默认）时，见下方"原生 launcher 与 Steam"
- **成就与云存档**经由 Ren'Py 的 Python API，不受影响；`renmori.rmc` 是静态文件，因此 Steam 的文件校验与增量更新正常工作
- **`steam_appid.txt`** 由 Steam SDK 在 `renpy.loader` 之外读取，故 RenMori 默认将其保持为明文（`DEFAULT_KEEP_ON_DISK`）——将其保留在发行构建中无害，其他由外部读取的文件可通过 `renmori.toml` 中的 `keep_on_disk` 添加

---

## 原生 launcher 与 Steam

自 1.2.6 起，使用插件时原生 launcher **默认开启**，`--no-launcher` 可关闭。它被装配为各平台的入口点（Windows 上的 `the_question.exe`、Linux 上由 `the_question.sh` 启动的引擎存根 `lib/py3-linux-x86_64/the_question`、macOS 上 `the_question.app` 内的可执行文件），因此启动选项保持不变；它先做启动认证、再启动真正的引擎，这一步改变了 Steam 覆盖层与 Steamworks SDK 所依赖的进程模型，因此其 Steam 兼容性分平台记录：

| 平台 | 重启方式 | 状态 |
|----|----------|--------|
| macOS | `execv`（同 PID、继承环境） | **已验证**——覆盖层重新附着到真引擎、`SteamAPI_Init` 保持其 app context；overlay 能盖在游戏上、gameplay 流畅 |
| Windows | `_spawnv`（引擎作为子进程运行） | **尚未测试**——子进程模型最可能影响 overlay 注入；`SteamAPI_Init` 应仍能继承 app context |
| Linux | `execv`（同 macOS） | **尚未测试**——预期与 macOS 一致 |

> **求反馈——Windows。** 原生 launcher + Steam 的组合**尚未在 Windows 上确认**：Steam 覆盖层（Shift+Tab）能否附着到被重启的引擎、以及经 Steamworks SDK 的成就 / 云存档是否可用，**均未经测试**。发行前请在 Windows 上检查覆盖层与成就并反馈结果；若不正常，请以 `--no-launcher` 构建 Windows depot。

launcher 在 `game/` 下发现散装的 Ren'Py 脚本或扩展时会拒绝启动，因此玩家以 `.rpy` 文件形式放进 `game/` 的模组或补丁会使带 launcher 的构建无法启动，这类内容应随构建一并发布；以 1.2.0 或更早版本、带 launcher 加密的构建缺少这项检查，应使用 1.2.5 或更高版本重新加密。

覆盖层本身的渲染可能显得卡顿——那是 Steam 自带的 CEF 层（用"添加非 Steam 游戏"测试时尤甚，不同于正式商店 App），与 RenMori 无关。

---

## 检查清单

- [ ] 已在 Ren'Py 启动器中从源码构建（Build Distributions）
- [ ] 已对解压后的构建文件夹运行 `renmori protect`
- [ ] `renmori verify` 已通过
- [ ] SteamPipe 的 `contentroot` 指向**受保护的文件夹**，而非 `.zip`
- [ ] 已按操作系统设置启动选项（`the_question.exe` / `.sh` / `.app`）
- [ ] 未应用 Steam DRM 包装器
- [ ] **未**对受保护的文件夹重新运行启动器
- [ ] 使用原生 launcher（默认）时：已在 Windows 上检查 Steam 覆盖层与成就，二者**尚未经过验证**（见"原生 launcher 与 Steam"）
- [ ] 已使用 1.2.6 或更高版本加密
