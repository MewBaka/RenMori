English version: [script-layer.md](script-layer.md)

# 脚本层与引擎锁定（M2）

M1 已将每个 `.rpyc` 加密于容器之内，因此现成工具无法在已发布的构建上触及它们。M2
是对脚本*源*的**纵深防御**，面向容器内容被暴露的情形（容器密钥泄露或被推导出，或
内存转储），并辅以阻断注入式反编译器、锁定发行版的**引擎加固**。

## 1. 脚本变换（基线）

已编译脚本以 pickle 形式将其 AST 携带于 RPYC2 的 slot 载荷中
（`zlib(pickle((data, stmts)))`）。在构建期，RenMori 将每个 pickle 载荷替换为：

```
SCRIPT_MAGIC (b"RMSC\x01") || nonce(12) || AES-256-GCM(script_key, pickle)
```

- **`script_key` 独立于容器主密钥**——仅凭主密钥暴露容器内容并*不会*得到可反编译的脚本，因为还需脚本密钥，而它存在于运行时扩展中，在生产环境中则存在于闭源原生运行时中
- 可逆且无损——运行时在 Ren'Py 反 pickle 之前将其解密回与原始完全一致的 pickle，因此 AST 语义毫发无损；实现见 [`script/transform.py`](../src/renmori/script/transform.py)（构建）与 [`runtime/hook.py`](../src/renmori/runtime/hook.py) 中的 `renpy.script.loads` 补丁（运行时）

### 为何这能击败反编译器

存储的 slot 载荷不再是 pickle，因此提取它的反编译器只会看到
`SCRIPT_MAGIC || ciphertext`。已在同一个 `script.rpyc` 上针对两款具名工具验证：

| 工具 | 原始 `.rpyc` | 经 RenMori 变换 |
|------|--------------|-----------------|
| `unrpyc` | 反编译为 `.rpy` | **失败** |
| `unrpyc --try-harder` | — | **失败**（其 zlib/base64/hex/转义层无法触及 AES-GCM） |
| `rpycdec` | 反编译为 `.rpy` | **失败**（`Unsupported file format`） |

### 闭源升级：逐构建的 AST 结构随机化

基线的逆转是单一的带密钥步骤；攻破某一构建脚本密钥的攻击者会拿回标准 pickle。闭源
多态引擎更进一步：它逐构建随机化已编译脚本的*结构*，使得即便完全解密，载荷也不携
带任何反编译器可据以分派的标准类名，且没有单一的可逆密钥能够还原它。它是一种绝不
下发给玩家的构建期变换，且逐构建各异，因此一次攻破无法迁移。机制与实现为专有内容
——见私有仓库 `MewBaka/RenMori-core`。

## 2. 注入阻断（引擎层）

`un.rpyc` 式反编译器的工作方式，是被丢入 `game/` 并作为脚本加载，其 init 代码会倾
倒一切。RenMori 拒绝**打开**任何物理解析位置落在游戏目录内的类脚本文件
（`.rpyc/.rpymc/.rpy/.rpym/.rpe`），因此被注入文件的代码永不运行。`renpy/common`
下的引擎脚本不受影响（该防护仅作用于游戏目录）。合法脚本仅来自容器。已验证：植入
的 `game/*.rpyc` 从 `load_core` 返回 `None`，而容器脚本仍可加载。

## 3. 发行版锁定

在受保护的构建中，运行时将 `config.developer = False` 与 `config.console = False`，
并拒绝数据导出子命令（`compile`、`dialogue`、`translate`、`add_from`、
`merge_strings`）。`renpy.sh … lint`/`run` 仍可使用。

## 验证

```bash
python tools/verify_in_renpy.py --sdk /Applications/renpy-8.5.2-sdk \
    --game /Applications/renpy-8.5.2-sdk/the_question
```

阶段 1（扩展加载）：资源逐字节一致；每个脚本载荷均已变换（非 pickle）并能逆转为有
效的 pickle；植入的磁盘脚本被拒绝。阶段 2（完整 `lint`）：引擎端到端加载并解析每
个经变换的脚本，无任何错误。此外还有针对无损变换往返的单元测试
[`tests/test_script.py`](../tests/test_script.py)。
