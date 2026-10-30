English version: [usage.md](usage.md)

# CLI 使用

`renmori` 命令行工具用于保护**已构建**的 Ren'Py 8.x（Python 3）发行版构建。它不会改动游戏源码——你应在 Ren'Py 启动器 *Build Distributions* 的输出上运行它。

- 关于 CI 流水线与密钥管理，参见 [ci.md](ci.md)
- 关于发布到 Steam，参见 [steam-release.md](steam-release.md)
- 关于配置文件，参见 [`examples/renmori.toml`](../examples/renmori.toml)

---

## 安装

尚未发布到 PyPI（版本 `0.0.1`），从源码安装：

```bash
git clone <this-repo> renmori
cd renmori
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
renmori --version
```

需要 Python 3.9+（读取 `renmori.toml` 配置需要 3.11+，或在更低版本上安装 `tomli` 包）。

---

## 快速上手

```bash
# 1. Build your game in the Ren'Py launcher (Build Distributions), then unzip it.
# 2. Protect the built folder into a new one:
renmori protect ./dist/MyGame-1.0-pc -o ./dist/MyGame-1.0-pc-protected

# 3. Check it:
renmori verify ./dist/MyGame-1.0-pc-protected
```

输入为任意包含 `game/` 子目录的目录。`protect` 会将 `game/` 下的全部内容打包进 `game/renmori.rmc`，转换编译后的脚本，删除明文原始文件，写入加载器扩展 `game/renmori.rpe`，并生成 `renmori-manifest.json`。

---

## 命令

### `renmori protect <game-dir> [options]`

保护一个发行版构建目录

- **原地保护（默认）：** 覆盖该目录，但会先将原始目录复制到同级的 `<dir>_bak`——在交互式终端下会先打印摘要并询问 `[y/N]`，之后才改动任何文件
- **输出到新目录：** `-o OUTPUT` 保护一份副本并保持原目录不变（此模式下不创建备份）

### `renmori verify <protected-dir>`

依据受保护构建自身的 `renmori-manifest.json` 重新校验它：容器哈希、必需文件是否齐全、磁盘上是否不残留明文 `.rpa`/`.rpyc`/`.rpy`。可用作 CI 门禁。

---

## 选项（`protect`）

| 参数 | 配置键 | 默认值 | 说明 |
|------|-----------|---------|-------|
| `-o, --output DIR` | — | 原地 | 在 DIR 中保护一份副本（DIR 必须不存在）；原目录保持不变 |
| `-c, --config FILE` | — | 自动探测 | 否则取 `<game-dir>/renmori.toml` 或 `./renmori.toml` |
| `--chunk-size N` | `chunk_size` | 65536 | 容器分块大小（字节） |
| `--exclude GLOB` | `exclude` | 无 | 匹配到的文件保持不加密（可重复；在配置基础上追加） |
| `--strength S` | `strength` | full | 默认为完整保护（插件的最强格式，无插件则失败）；`baseline` 强制使用开源格式；`auto` 为有插件时用完整、否则用基线（见下文） |
| `--plugin PATH` | — | `$RENMORI_PLUGIN` | 闭源保护插件的路径；启用完整（`poly`）保护 |
| `--platforms LIST` | `platforms` | 自动检测 | 仅插件：目标平台的逗号分隔列表，否则从构建的 `lib/py3-*` 检测 |
| `--launcher` | `launcher` | 关 | 仅插件：将密钥绑定到原生启动器并随之分发 |
| `--no-lockdown` | `lockdown` | 开 | 保持 console/developer/export 处于启用状态 |
| `--no-backup` | — | 关 | 原地保护时不创建 `<dir>_bak` 副本（对 `-o` 无效） |
| `--keep-plaintext` | `keep_plaintext` | 关 | 不删除已打包的原始文件（调试用） |
| `-y, --yes` | — | 关 | 跳过保护前的确认提示 |
| `--no-hints` | — | 关 | 成功后不打印 “package & publish” 指引 |

## 通用选项（两条命令均适用）

| 参数 | 默认值 | 说明 |
|------|---------|-------|
| `--lang {auto,en,zh}` | `auto` | 面向用户的输出语言；`auto` 跟随系统区域设置；亦可用 `RENMORI_LANG` |
| `--no-color` | 关 | 禁用 ANSI 颜色——非终端时自动关闭，并遵从 `NO_COLOR` |
| `--quiet` | 关 | 抑制所有带样式的 stderr 输出；仅打印最后一行 JSON |

---

## 输出与退出码

面向用户的进度信息（横幅、摘要面板、步骤行、结果面板与发布提示）输出到 **stderr**，带样式且本地化。**stdout 的最后一行始终是一个 JSON 对象**，其键名为稳定的英文：

```json
{"status": "ok", "output": "…", "manifest": {"file_count": 842, "container_sha256": "…", "strength": "baseline"}, "backup": "…"}
```

因此无论样式如何，CI 都能在任意区域设置下解析相同的输出。`verify` 打印 `{"status": "ok", "file_count": …, "container_sha256": "…"}` 或 `{"status": "error", "problems": [...]}`。

| 退出码 | 含义 |
|-----:|---------|
| 0 | 成功 |
| 2 | 用法 / 前置条件（无 `game/`、已受保护、备份或输出目录已存在、在提示处中止、参数或配置错误） |
| 1 | 运行时失败（打包错误，或 `verify` 不匹配） |

---

## 配置文件

将 `renmori.toml` 放在游戏目录旁（或通过 `-c` 指定）。所有字段均为可选；CLI 参数会覆盖它，而 `--exclude` 在其基础上追加。为便于 CI，键值可从环境变量读取。完整参考见 [`examples/renmori.toml`](../examples/renmori.toml) 与 [ci.md](ci.md)。

```toml
[protect]
chunk_size = 65536
exclude = ["thirdparty/*"]
lockdown = true

[keys]
# master_env = "RENMORI_MASTER_KEY"   # 64 hex chars; from your CI secret store
# script_env = "RENMORI_SCRIPT_KEY"
```

---

## 常见工作流

**保护一份副本，保留原件：**

```bash
renmori protect ./dist/MyGame-1.0-pc -o ./dist/MyGame-1.0-pc-protected
```

**原地保护（保留 `MyGame-1.0-pc_bak` 备份）：**

```bash
renmori protect ./dist/MyGame-1.0-pc
```

**非交互 / CI（无提示，仅 JSON）：**

```bash
renmori protect ./build/MyGame-pc --no-backup --quiet -y
```

**强制指定语言（例如在容器中）：**

```bash
RENMORI_LANG=en renmori protect ./build/MyGame-pc
# or: renmori protect ./build/MyGame-pc --lang en
```

**在真实引擎中的端到端校验（可选）：**

```bash
python tools/verify_in_renpy.py --sdk /path/to/renpy-8.5.2-sdk --game /path/to/your-game
```

---

## 故障排查

| 现象 | 原因 / 处理 |
|---------|-------------|
| `has no 'game/' directory` | 将 RenMori 指向包含 `game/` 的构建目录，而非 `game/` 本身或 `.zip` |
| `is already protected` | 目标已含 `renmori.rmc`；请从全新构建（或 `_bak`）重新开始 |
| `backup <dir>_bak already exists` | 删除它，或传入 `--no-backup`，或用 `-o` 保护一份副本 |
| `strength 'x' requires the closed renmori plugin` | 将 `--plugin` / `$RENMORI_PLUGIN` 指向插件，或改用 `baseline`（见下文） |
| CI 中始终不出现提示 | 设计如此——仅在交互式 TTY 下提示 |

---

## 基线保护与完整保护

**完整保护**——每次构建的结构多态、运行时密钥派生、原生核心，以及可选的原生启动器——是**闭源**组件，以预编译插件形式分发，从不以源码形式提供。它是**默认**：`renmori protect` 会发现插件并自动启用,而在无插件时直接失败,而不会悄悄退化为较弱的基线。

```bash
export RENMORI_PLUGIN=/path/to/renmori-plugin      # or pass --plugin PATH
renmori protect ./dist/MyGame-1.0-pc -o ./dist/MyGame-1.0-pc-protected
```

**基线**流水线——固定的容器格式,加载器扩展中内嵌一个占位密钥——需经 `--strength baseline` 显式启用。它能挫败 `unrpa`、`unrpyc` 等现成工具,但密钥与读取器以明文随附,因此面对有决心的攻击者并非真正的保护。传入 `--strength auto` 可获得"有插件时用完整、否则用基线"的平滑行为。`--platforms` 与 `--launcher` 仅对插件生效,工具与插件之间的进程契约在 [interface.md](interface.md) 中规定。

无论哪条流水线,都能处理用启动器归档构建的游戏:`.rpa` 封包会在保护时被解开,其中的条目作为独立文件打进容器,这样封包消失后引擎仍能找到脚本与素材。

RenMori 面向 **Ren'Py 8.x（Python 3）**。其运行时已在 Linux（CI，无头）与 macOS 的真实 Ren'Py 引擎中验证，Windows 与 Linux 运行时则由各平台上的单元、黄金容器与密钥派生任务加以检验；在 Proton 下的 Steam Deck 运行仍待完成。发行前请在你的目标平台上测试。
