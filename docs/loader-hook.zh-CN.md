English version: [loader-hook.md](loader-hook.md)

# 加载器钩子：RenMori 如何接入 Ren'Py 8.5

以下为阅读 Ren'Py **8.5.2** 源码（`renpy/loader.py`、`renpy/main.py`、
`renpy/script.py`、`renpy/pygame/rwobject.pyx`）并检视 SDK 所附运行时后得出的发
现。对于我们支持的每个 Ren'Py 版本都须重新核验。

## 1. 每一项资源都经由同一处瓶颈

`renpy.loader.load(name)` → `load_core(name)` → 依次尝试
`renpy.loader.file_open_callbacks` 中的每个函数，返回第一个非 `None` 的结果。默认
顺序：`config.file_open_callback`、文件系统、封包（RPA）、APK、远程。

调用方审计：

| 资源 | 调用点 |
|------|--------|
| 图像 | `loader.load()` → `pygame.image.load(f, filename)`（`display/pgrender.py`） |
| 音频**与视频** | `renpy.audio.audio.load()` → `loader.load(fn, directory="audio")`；影片经由音频通道播放 |
| 字体 | `loader.load(fn, directory="fonts")`（`text/font.py`） |
| 脚本 | 以 `loader.load(fn, tl=False)` 读取 `.rpyc`（`script.py`），无论该文件来自磁盘还是索引 |

**唯一的绕过点：**`renpy.exists()` 使用 `transfn()`，且被明确记载为仅限磁盘。调
用 `renpy.exists()` 去查询一个已被我们移入容器的文件的游戏，会得到 `False`。该钩
子对此打了补丁。

**RenMori 将其回调插入 `file_open_callbacks` 的索引 0 处**，使容器优先于磁盘上的
任何内容。

## 2. 文件发现：`scandirfiles_callbacks`

`listdirfiles()`（用于脚本发现、`renpy.list_files()`、自动图像以及填充
`loadable_cache`）通过以 `add(dn, fn, files, seen)` 调用
`renpy.loader.scandirfiles_callbacks` 中的每个函数而构建。RenMori 注册了一个函
数，以 `dn=None` 添加每一个容器条目（与封包条目的添加方式相同）。这使得我们的文
件在 `loadable()` 中为真，并使脚本发现能够找到仅存在于容器内的 `.rpyc` 文件。

## 3. 时序：钩子必须在 `index_files()` 之前安装

脚本在启动时被发现，早于任何游戏 `.rpy` 代码运行，因此普通的 `init python` 块为时
已晚。Ren'Py 8.5 提供了一个官方的早期钩子：**Ren'Py 扩展（Ren'Py Extensions）**。
`renpy.main.main()` 会按排序顺序，从 Ren'Py 基目录、`game/` 与 `game/libs` 加载每
一个 `*.rpe`（包含 `autorun.py` 的 zip，会被置入 `sys.path`）与 `*.rpe.py`，**早
于** `renpy.loader.index_files()` 且早于脚本被加载。

RenMori 将其运行时作为 `game/renmori.rpe` 随附。（`.rpe` 同时也是攻击者的注入点；
启用可选的原生启动器（`--launcher`）时，1.2.5 及以后的版本在发行版根目录、`game/`、
`game/libs` 或 `renpy/common` 中出现 `game/renmori.rpe` 以外的任何 `.rpe` 时拒绝启动，
并把 `game/renmori.rpe` 本身纳入密钥派生，被改写的副本只能派生出错误的密钥；未启用
`--launcher` 的构建没有该门禁。）

## 4. 返回类型至关重要：`RWopsIO` 与重开陷阱

Ren'Py 8.5 经由 `rwobject.pyx` 中的 `to_rwops()`，将文件对象交给 C 代码
（SDL_image、FreeType、ffmpeg）。其行为依次为：

1. 反复拆解 `.raw`
2. `RWopsIOImpl` → 直接使用其 C 层 `SDL_RWops`（**快速，无 GIL**）
3. **带字符串 `.name` 的 `io.IOBase` → 按该名称从磁盘重开**（若存在 `.base`/`.length` 则一并携带）
4. 否则，任何带 `read` 者 → 以 Python 回调包装，**每次读取都会取得 GIL**

RenMori 的应对：

- **陷阱**——一个子类化 `io.IOBase` 并暴露字符串 `.name` 的解密文件对象会被从磁盘重开，届时它要么找不到文件，要么把原始密文交给 SDL；我们的流对象既不得暴露 `.name`，也不得暴露 `.raw`
- **中小文件**——完整解密并返回 `RWopsIO.from_buffer(plaintext, name=name)`，这是一个纯 C 层缓冲 RWops，此后不再取得 GIL，为 Ren'Py 最快的路径
- **大文件（视频、长背景音乐）**——返回 `RWopsIO(stream, name=name)`，其中 `stream` 按需解密分块；此路径经由 Python 回调，每次读取取得一次 GIL，必须予以基准测试，生产环境的答案是闭源运行时中的原生 nogil 解密 `SDL_RWops`

## 5. 在 Ren'Py 自带 Python 内实现 AES：无需依赖

Ren'Py 自带的 Python 既无 `cryptography` 也无 `pycryptodome`，但确实附带 `ctypes`
（三个运行时上均存在 `PyInit__ctypes`），并且：

| 运行时 | AES-256-GCM 来源 |
|--------|------------------|
| macOS（`librenpython.dylib`，通用二进制） | OpenSSL 静态链接**并导出**（`EVP_aes_256_gcm`、`EVP_CIPHER_CTX_new`、`EVP_DecryptUpdate`……） |
| Linux（`librenpython.so`） | 同上，已导出 |
| Windows（`librenpython.dll`、`libpython3.12.dll`） | EVP 符号**未导出**；改用操作系统的 **CNG（`bcrypt.dll`）**，自 Vista 起的每个 Windows 版本都具备硬件加速的 AES-GCM |

因此运行时读取器经由 `ctypes` 调用 OpenSSL（macOS/Linux）或 CNG（Windows）。解密
在原生代码中以 AES-NI / ARMv8 crypto 运行；仅每分块的调用开销为 Python。构建工具
使用 `cryptography` 包。所有后端都产出标准 AES-256-GCM，因此容器格式不依赖于后
端。
