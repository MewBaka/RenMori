English version: [research.md](research.md)

# 研究：Ren'Py 保护现状

本文档记录业已存在的方案，以说明本项目为何无需重复造轮子。研究日期：2026-10-29。

## 概要

目前**不存在面向 Ren'Py 的商业级通用保护工具**能够做到逐构建多态，并同时覆盖脚本、全部资产与引擎。这一空白真实存在，公开的工具生态完全站在**攻击方**一侧（解包器与反编译器）；少数保护尝试要么停留在原型阶段，要么只覆盖单一层面。

## Ren'Py 自有格式的工作方式（及其为何薄弱）

- **`.rpa` 封包**本质上只是一份索引加上首尾相接的文件，至多带有一个 XOR「混淆」密钥——它们并未加密
- **`.rpyc` 脚本**是 Ren'Py AST 的 zlib 压缩 pickle
- Ren'Py 官方指引称混淆只能挡住随意浏览，并承认「稍有技术的程序员即可轻易破解」；其主创已将资产加密请求（renpy/renpy#2546）以不可行为由关闭——游戏在运行时必须读取自身资产，因此解包所需的一切都会随游戏一同下发，且资产始终可从内存或屏幕捕获

## 攻击方工具（受保护构建必须击败的对象）

| 工具 | 功能 | 备注 |
|------|------|------|
| `unrpa` | 提取 `.rpa` | 支持 RPA-1.0…4.0 及各类变体 |
| `rpatool` | 创建/列出/提取/编辑 `.rpa` | 可用指定的 XOR 密钥封包 |
| `RenPack` | 面向 RPA-2.0/3.0/3.2 的 GUI/CLI，含 XOR | 可读取并*重写*封包 |
| `RenpyEx` | 纯 Rust 的 `.rpa`/`.rpyc` 提取器 | **从 `options.rpy` 自动探测密钥**，以 SHA-256 校验，力求逐字节精确 |
| `unrpyc` | 反编译 `.rpyc` | `--try-harder`，以及 `un.rpyc`/`bytecode.rpyb` 的进程内注入 |
| `rpycdec` | 反编译 `.rpyc`/`.rpymc` | 构造伪 `renpy`/`store` 包，使 pickle 得以反序列化 |

### unrpyc 的去混淆实际能处理什么

摘自 `deobfuscate.py`——这一点很重要，因为它表明哪些幼稚的「魔改」是无效的：

- **槽位提取器**依次尝试：标准 `RENPY RPC2` 头；无头的旧式格式（整个文件是单个 zlib 数据块）；`extract_slot_headerscan`（当魔数被改动或偏移时，扫描 36 字节的头部模式）；`extract_slot_zlibscan`（**当头部被破坏时，扫描 zlib 起始字节 `0x78` 并校验其校验和，再对候选数据解压**）
- **分层载荷解密器**（`DECRYPTORS`），最多 10 层，每层之后重试一次 pickle 加载：`decrypt_zlib`、`decrypt_hex`、`decrypt_base64`、`decrypt_string_escape`

**由此可知：** 更改魔数、偏移头部，或将载荷用 zlib/base64/hex/escape 包裹，都**无法**阻止 unrpyc。尤其是 zlib 扫描器可击破一切头部伎俩。要真正击败它，必须彻底放弃标准 pickle/zlib（改用自定义 AST 格式），*并且*让类与字段布局逐构建各不相同，使「伪 renpy 模块」手法无从绑定。

## 既有的保护尝试

- **ichfly/renpy-Asset-Protect**——仅通过一个基于密钥的加载器与配套的 C 可执行程序（AES + SHA-256）保护资产；属原型质量，带有硬编码密钥表与调试文件写出；作者本人声明它**不是 DRM**，并称该做法「易被绕过，但终究好过未经任何改造即可被直接转储」
- **论坛坊间做法**（Lemmasoft、知乎）：重命名 `.rpa`、用十六进制编辑器改写头部、把脚本藏进图片文件，或将引擎限制为封包白名单——这些要么可被轻易绕过，要么未经验证

## 官方 / 社区共识

- renpytom（Ren'Py 主创）：完整的资产加密「不可能」实现，因此他关闭了该功能请求；他同时**反对**混淆，因为引擎或系统更新一旦破坏游戏，混淆会使其难以修复
- uyjulian（贡献者）：即便封包格式再复杂，也可通过转储运行中游戏的内存或屏幕来攻破（参见 NinjaRipper、KrkrExtract）；要真正阻止注入式提取器，需要内核级反作弊
- unrpyc 维护者：**拒绝**接受针对特定游戏去混淆的功能请求，明确理由是这是一场「军备竞赛」

这最后一点正是 RenMori 的战略切口：既然无人会为通用工具加入逐游戏支持，**「每个构建各不相同」本身就是一项持久的优势。**

## 影响设计的结论

1. 彻底离开 RPA 与标准 rpyc/pickle——头部与编码伎俩已被 `unrpyc` 处理
2. 逐构建多态是核心价值，且恰好零运行时开销——契合性能优先的原则
3. 对客户坦诚：胜点在于「没有通用解包器 + 逐游戏的专家级成本」，而非「不可破解」——参见 [threat-model.md](threat-model.md)

## 来源

- Ren'Py 资产加密请求（以不可行为由关闭）：
  https://github.com/renpy/renpy/issues/2546
- Lemmasoft，「Protect .rpa and .rpyc from unpackers and decompilers」：
  https://lemmasoft.renai.us/forums/viewtopic.php?p=389272
- Ren'Py 历史 Wiki，「Obfuscating Your Game」：
  https://renpy.org/wiki/renpy/doc/reference/Obfuscating_Your_Game
- unrpyc：https://github.com/CensoredUsername/unrpyc
  （`master` 分支上的 `deobfuscate.py`）
- rpycdec：https://github.com/cnfatal/rpycdec
- unrpa：https://pypi.org/project/unrpa/
- rpatool：https://github.com/Shizmob/rpatool
- RenPack：https://github.com/Kroste/RenPack
- RenpyEx：https://github.com/rolanfreeman6-png/RenpyEx
- ichfly/renpy-Asset-Protect：https://github.com/ichfly/renpy-Asset-Protect
