English version: [ci.md](ci.md)

# CLI 与 CI 集成（M3）

RenMori 是作用于标准 Ren'Py 构建产物之上的单条构建期命令，不改动游戏源码。默认的完整保护使用闭源插件，插件首次使用时从公开发布页下载一次，此后从缓存读取；完全离线的运行环境参见[保护强度与插件](#保护强度与插件)。

## 命令

```bash
renmori protect <game-build-dir> [-o OUTPUT] [options]
renmori verify  <protected-dir>
```

`protect` 将 `game/` 下的全部内容打包进 `game/renmori.rmc`，转换编译后的脚本，移除明文原始文件，写入加载器扩展 `game/renmori.rpe`，并生成 `renmori-manifest.json`。`verify` 依据该清单重新校验受保护的构建（容器哈希、必需文件、无明文残留）——可用作 CI 门禁。

原地保护（不带 `-o`）会覆盖原目录，因此 RenMori 会先将其复制到同级的 `<dir>_bak` 目录；若 `<dir>_bak` 已存在则运行失败。传入 `--no-backup` 可跳过该复制直接覆盖。使用 `-o OUTPUT` 时原目录从不被改动（受保护的是副本），因而不创建备份。

输入为 Ren'Py 构建产生的任意目录：任意包含 `game/` 子目录的目录。

### 退出码

| 退出码 | 含义 |
|-----:|---------|
| 0 | 成功 |
| 2 | 用法 / 前置条件（无 `game/`、已受保护、配置或参数错误） |
| 1 | 运行时失败（打包错误，verify 不匹配） |

stdout 的最后一行始终是一个 JSON 对象（`{"status": "ok", …}` 或 `{"status": "error", …}`）；进度信息输出到 stderr。使用 `--quiet` 可仅输出 JSON。带样式的 stderr 输出及其语言从不影响 stdout：JSON 的键与值在任意区域设置下均保持英文，因此 CI 解析是稳定的。

原地保护会打印摘要并请求确认（`[y/N]`）——但**仅在交互式终端下**。当 stdin 不是 TTY（CI），或使用 `--quiet` 或 `-y/--yes` 时，它会直接执行而不提示，因此流水线永远不会挂起。颜色在非 TTY 下自动禁用，并遵从 `NO_COLOR`。输出语言跟随系统区域设置；可用 `--lang en|zh` 或 `RENMORI_LANG` 固定。

## 选项（protect）

| 参数 | 配置键 | 默认值 | 说明 |
|------|-----------|---------|-------|
| `-o, --output DIR` | — | 原地 | 先复制到 DIR（DIR 必须不存在） |
| `-c, --config FILE` | — | 自动探测 | 否则取 `<game-dir>/renmori.toml` 或 `./renmori.toml` |
| `--chunk-size N` | `chunk_size` | 65536 | 容器分块大小 |
| `--exclude GLOB` | `exclude` | 无 | 匹配到的文件保持不加密（可重复；CLI 在配置基础上追加） |
| `--strength S` | `strength` | 完整保护 | 未设置时使用插件声明的最强强度（无插件时失败）；`auto` 有插件时完整保护、否则基线；`baseline` 为开源格式，从不下载插件 |
| `--plugin PATH` | — | 自动查找 | 闭源插件路径（否则依次取 `RENMORI_PLUGIN`、缓存、下载） |
| `--platforms LIST` | `platforms` | 自动探测 | 仅插件：以逗号分隔的目标平台列表 |
| `--launcher` | `launcher` | 关 | 仅插件：将密钥绑定到原生启动器并随附 |
| `--no-lockdown` | `lockdown` | 开 | 保持 console/developer/export 处于启用状态 |
| `--no-backup` | — | 关 | 原地保护时跳过默认的 `<dir>_bak` 复制（对 `-o` 无效） |
| `--keep-plaintext` | `keep_plaintext` | 关 | 调试用（仅基线） |
| `-y, --yes` | — | 关 | 跳过保护前的确认提示 |
| `--no-hints` | — | 关 | 成功后不打印 “create a release build” 指引 |
| `--lang {auto,en,zh}` | — | `auto` | 面向用户的输出语言（亦可用 `RENMORI_LANG`）；`auto` 跟随系统区域设置 |
| `--no-color` | — | 关 | 禁用 ANSI 颜色（亦遵从 `NO_COLOR`） |
| `--quiet` | — | 关 | 仅打印最后一行 JSON（stderr 无带样式输出） |

配置文件参见 [`examples/renmori.toml`](../examples/renmori.toml)。

## 保护强度与插件

未设置 `strength` 时，`protect` 使用闭源插件声明的最强强度；若无可用插件则**失败**（退出码 2），而不会静默地以较弱的基线格式发行。`--strength auto` 保留“有插件则完整保护、否则基线”的回退行为；`--strength baseline` 强制使用开源格式，且从不下载插件。

插件的查找顺序为：`--plugin`、`RENMORI_PLUGIN`、本地缓存（`~/.cache/renmori/plugin/<tag>`，Windows 上为 `%LOCALAPPDATA%\renmori\plugin\<tag>`），最后从公开发布页下载并依据 `SHA256SUMS` 校验。CI 中下载无需确认。在多次运行之间缓存该目录可避免重复下载。离线运行环境应预先放置插件并以 `RENMORI_PLUGIN` 指向它，或设置 `RENMORI_NO_DOWNLOAD=1` 禁止任何下载。`RENMORI_PLUGIN_BASE_URL` 与 `RENMORI_PLUGIN_TAG` 分别用于指定镜像地址与发布标签。

## CI 中的密钥

`[keys]` 部分**仅适用于基线格式**。闭源插件自行派生密钥并忽略该部分，因此在默认的完整保护下，下述密钥环境变量不起作用。

默认情况下，`protect` 为每次构建生成一个全新的随机主密钥和一个**独立**的脚本密钥，内嵌于加载器扩展（基线占位——闭源运行时改为派生这些密钥）。若要自行管理密钥，请将 RenMori 指向持有 64 位十六进制字符（32 字节）密钥的环境变量：

```toml
[keys]
master_env = "RENMORI_MASTER_KEY"
script_env = "RENMORI_SCRIPT_KEY"
```

从你的 CI 密钥库填充它们；切勿提交密钥。若某个命名变量未设置，RenMori 会回退到随机密钥并予以说明。即便固定密钥，输出在不同构建间也不是逐字节可复现的（每个文件使用随机盐），此为设计使然——请针对 `verify` 与清单的文件列表做断言，而非跨构建比较容器哈希。

## GitHub Actions

参见 [`examples/github-actions-protect.yml`](../examples/github-actions-protect.yml)：构建 → `renmori protect` → `renmori verify` → 上传产物，并在多次运行之间缓存插件。

## 针对真实引擎的端到端校验（可选）

[`tools/verify_in_renpy.py`](../tools/verify_in_renpy.py) 会保护一个示例游戏，并在真实的 Ren'Py SDK 中确认每一项资源都能逐字节无误地解密、脚本已被转换但仍可解析、注入的脚本会被拒绝。将其指向一个 SDK 和一个游戏即可；在没有可用 SDK 处会被跳过。
