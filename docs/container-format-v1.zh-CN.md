English version: [container-format-v1.md](container-format-v1.md)

# 容器格式 v1（基线，开放规范）

本文描述**基线**容器格式：固定且公开，强度适中。发行版构建会令其经过闭源多态
引擎，该引擎逐构建随机化布局与密钥派生；本规范描述的是开放框架所实现并测试的固
定基线。

所有整数均为小端序。所有加密均为 **AES-256-GCM**（16 字节认证标签）。

## 布局

```
+-------------------------------+  offset 0
| Header (64 bytes)             |
+-------------------------------+  offset 64
| Encrypted file payloads       |   (one region per file, in add order)
|   file A: chunk 0, chunk 1, …  |
|   file B: chunk 0, …           |
+-------------------------------+  header.index_offset
| Encrypted index (GCM)         |
+-------------------------------+  EOF
```

### 头部（64 字节）

| 偏移 | 大小 | 字段 | 说明 |
|----:|-----:|-------|-------|
| 0 | 8 | magic | `52 45 4E 4D 4F 52 49 01`（`RENMORI\x01`） |
| 8 | 2 | version | `1` |
| 10 | 2 | flags | 保留，`0` |
| 12 | 4 | chunk_size | 每分块明文字节数（默认 65536） |
| 16 | 8 | index_offset | 加密索引的字节偏移 |
| 24 | 8 | index_length | 加密索引长度（明文 + 16 认证标签） |
| 32 | 12 | index_nonce | 索引的 GCM nonce |
| 44 | 16 | container_id | 每容器随机生成，为所有密钥派生加盐 |
| 60 | 4 | reserved | `0` |

头部前 **60 字节**（除 `reserved` 外的全部内容）构成索引的 GCM AAD，因此头部一经
改动便会破坏索引解密。

### 索引

一个经 GCM 加密的 UTF-8 JSON 对象：

```json
{ "v": 1, "files": { "<name>": [data_offset, size, "<file_id hex>"], … } }
```

- `name`——Ren'Py 游戏相对路径，正斜杠，无前导斜杠（`images/bg.png`）
- `data_offset`——文件首个加密分块的绝对偏移
- `size`——明文字节大小
- `file_id`——16 字节随机值（十六进制），每文件唯一，为文件密钥加盐

### 文件载荷

每个文件的明文按 `chunk_size` 字节切分为若干分块（空文件为一个空分块，因此仍携带
一个认证标签）。每个分块独立加密，以 `ciphertext || tag` 存储（明文长度 + 16）。
由于每个非末尾分块恰为 `chunk_size` 明文，文件的第 *i* 个分块始终起始于
`data_offset + i*(chunk_size + 16)`——从而支持无需扫描的**按 seek 随机访问**。

## 密钥派生（HKDF-SHA256，RFC 5869）

```
index_key      = HKDF(ikm=master_key, salt=container_id, info="renmori/v1/index")
file_key(id)   = HKDF(ikm=master_key, salt=container_id, info="renmori/v1/file/" + id)
```

- `master_key` 为 32 字节，其在运行时的来源**不属于**本基线规范——开放框架将其作为输入接收，而闭源密钥派生逻辑负责在已发布游戏中隐藏并重建它
- 每文件密钥将 nonce 方案限定为每个文件一个密钥

### 每分块的 nonce（12 字节）与 AAD

```
nonce(i) = file_id[:8] || uint32_le(i)
aad(i)   = uint32_le(i) || uint8(1 if last chunk else 0)
```

计数器使每个 nonce 在单个文件内唯一；每文件唯一的密钥则使其跨文件唯一。AAD 将每个
分块绑定到其位置并标记末尾分块，因此分块无法被重排，文件也无法被悄然截断。

## 安全说明（基线）

- 分块级别的机密性与完整性经由 GCM 保证——任何位置的篡改都会导致解密失败
- 该格式**公开且固定**，因此其自身仅为基线强度——只有当攻击者同时掌握主密钥时通用读取器才有可能，真正的屏障是运行时密钥派生（闭源）与逐构建多态（闭源），二者都不在本文件中
- 设计上不在本文处理的内容——内存或屏幕录制；见 [threat-model.md](threat-model.md)

## 参考实现

- 写入器：[`src/renmori/container/writer.py`](../src/renmori/container/writer.py)
- 读取器与流式读取：[`src/renmori/container/reader.py`](../src/renmori/container/reader.py)
- AES-GCM 后端：[`src/renmori/container/crypto.py`](../src/renmori/container/crypto.py)
- 格式常量与密钥派生：[`src/renmori/container/format.py`](../src/renmori/container/format.py)
