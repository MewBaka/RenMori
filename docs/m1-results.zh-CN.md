English version: [m1-results.md](m1-results.md)

# M1 成果——资产层

M1 交付并验证了基线资产层：一个取代 Ren'Py RPA 封包的加密容器、一个运行时加载器钩子，以及运行在 Ren'Py 内置 Python 内的加密后端。验证基于 Ren'Py 8.5.2，以 SDK 样例项目 `the_question` 与一个包含数千项资产的吉字节级发行版构建共同演练，从而覆盖每一种资产类型以及流式读取路径。

目标平台为 Windows，开发与验证主机为 macOS/arm64。Windows 运行时路径（CNG）在 M4 中单独编写并验证。

## 已证明的内容

每一种资产类型都通过引擎内真实的 `renpy.loader` 逐字节一致地解密，并与各原始文件的 SHA-256 比对：

| 资产类型 | 投递路径 |
|----------|----------|
| 图像——立绘、CG（PNG/JPG） | 缓冲 |
| 音频（Opus/OGG） | 缓冲 |
| 脚本（`.rpyc`） | 缓冲 |
| 翻译（`tl/<language>/`） | 缓冲 |
| 字体，小型（TTF） | 缓冲 |
| 字体，大型——多 MB（TTF） | 流式 |
| 视频，大型——WebM/OGV/AVI | 流式 |

`lint` 会从容器中解析每一个 `.rpyc` 与翻译，因此脚本层得以完整加载。完成保护后，磁盘上不再残留任何明文封包、`.rpyc` 或 `.rpy`——只余 `renmori.rmc` 与 `renmori.rpe`，以及运行时的 `cache/`。

## 现成工具失效

- `unrpa` 拒绝该容器：版本自动探测失败，因为它并非 RPA 封包
- 磁盘上不存在任何 `.rpyc` 或 `.rpy` 供 `unrpyc` 反编译
- 对吉字节级容器做特征签名雕刻时，找不到任何多字节魔数（`PNG`、`RENPY RPC2`、`OggS`、`RIFF`、`OTTO`、`zip`），只余统计意义上预期的三字节巧合命中，且无一可恢复——该容器与随机数据无从区分

## 性能——基线参考读取器

通过 Python 参考读取器（ctypes → `librenpython` 中的 OpenSSL EVP，按 64 KB 分块的 AES-256-GCM），在引擎内对多 MB 资产测得的顺序解密吞吐约为 74 MB/s。这远高于实时视频与音频解码所需的速率，后者仅需数 MB/s。小型资产走缓冲路径，随后交由 Ren'Py 自身的 C 缓冲 RWops 处理，不再产生逐次读取的 GIL 争用。

这是参考读取器；实际发行的原生解密器会移除逐分块的 Python 调用开销。实际游玩会话中的前后帧时间对比（感知层面）在基准测试框架中单独追踪。

## 已确立的关键架构事实

- 钩子点：`file_open_callbacks`（插入到最前）与 `scandirfiles_callbacks`（负责发现以及 `lower_map`）；`.rpe` 扩展在 `index_files()` 之前加载——参见 [loader-hook.md](loader-hook.md)
- 在 Ren'Py 内部进行 AES 而不依赖任何第三方：macOS/Linux 上由 `librenpython` 导出的 OpenSSL EVP（位于 `sys.executable` 旁），Windows 上为 CNG；`_ctypes` 内建于全部三个发行运行时
- 规避了 `to_rwops` 重开陷阱：流式对象既不暴露 `.name` 也不暴露 `.raw`

## 已知缺口 / 后续

- `renpy.exists()`（仅查磁盘的 `transfn`）对容器内文件返回 False；若有项目需要，已备好补丁
- 基线占位密钥嵌入在 `autorun.py` 中；运行时密钥派生属于闭源组件
- 基线脚本层仍发行标准 `.rpyc`（静态加密）；自定义 AST 格式属于闭源多态层
- 窗口化的感知性能基准（帧时间）在基准测试框架中追踪
