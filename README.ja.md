<div align="center">

![LOGO](assets/logo/renmori-protector.png)

![For RenPy](https://img.shields.io/badge/For-RenPy-orange?style=for-the-badge&logo=RenPy) ![License](https://img.shields.io/badge/License-RenMori_License-orange?style=for-the-badge) [![English](https://img.shields.io/badge/README-English-lightgrey?style=for-the-badge)](README.md) [![简体中文](https://img.shields.io/badge/README-%E7%AE%80%E4%BD%93%E4%B8%AD%E6%96%87-lightgrey?style=for-the-badge)](README.zh-CN.md) ![日本語](https://img.shields.io/badge/README-%E6%97%A5%E6%9C%AC%E8%AA%9E-orange?style=for-the-badge) ![GitHub Repo stars](https://img.shields.io/github/stars/mewbaka/renmori?style=for-the-badge) ![PyPI Downloads](https://img.shields.io/pypi/dm/renmori?style=for-the-badge)

**商用 Ren'Py ビジュアルノベル向けの全データ保護ツール、100% 無料**

RenMori は Ren'Py 8.x でビルド済みのゲームを受け取り、保護された配布物を出力します。スクリプト・立ち絵・CG・音声・動画・フォント・翻訳・設定といったすべてのデータは暗号化コンテナに封入され、実行中のエンジン内部でのみ復号されます。プレイヤーの端末で動くゲームを完全に解析不能にすることは原理的にできません。RenMori は抽出のコストを最大限に引き上げ、既存の解凍スクリプトや大半の手抜き Agent では歯が立たないようにしますが、専門家によるリバースエンジニアリングまでは防げません。正直な脅威モデルは [こちら](https://renmori.mewbaka.cn/ja/technical/threat-model)

</div>

---

## 1. CLI のインストールと使い方

### インストール

```bash
pip install renmori
renmori --version
```

開発者のマシンには **Python 3.9+** が必要です（`renmori.toml` の設定を読むには 3.11+、それ未満は `pip install tomli`）。`cryptography` は自動で入ります。ソースから使う場合:

```bash
git clone https://github.com/MewBaka/RenMori.git
cd RenMori && pip install -e .
```

### ゲームを保護する

1. **ゲームをビルド**する — Ren'Py ランチャーの *Build Distributions*。RenMori はその成果物に対して動作し、あなたのソースには一切触れません
2. **ビルドを保護**する — 入力はビルド済みフォルダ、またはランチャーが出力した `.zip`（自動で解凍されます）:

   ```bash
   renmori protect ./dist/MyGame-1.0-pc -o ./dist/MyGame-1.0-pc-protected
   # アーカイブを直接渡しても OK:
   renmori protect ./dist/MyGame-1.0-pc.zip
   ```

   初回の完全保護では、公開 Release からお使いのプラットフォーム向けの閉源プラグインをダウンロード・検証してキャッシュします（手動インストール不要）。端末では先に確認を取り、CI では自動でダウンロードします

3. 結果を**検証**する（CI ゲートとして利用可）:

   ```bash
   renmori verify ./dist/MyGame-1.0-pc-protected
   ```

4. **配布**する — 保護済みフォルダをそのままリリースとして配布します（`renmori.rmc` と `renmori.rpe` を一緒に）。それに対して Ren'Py ランチャーのビルドを再実行しないでください。ソースから作り直されて保護が失われます

既定ではゼロ設定で動作し、CI 向けに機械可読な JSON 結果を 1 行出力し、終了コードも明確です。任意の `renmori.toml` でチャンクサイズ・除外リスト・ロックダウン・強度・鍵ソースを制御できます。オープンソースの**ベースライン**形式（プラグインなし・完全オフライン）を使うには `--strength baseline` を指定します。詳細は [CLI ドキュメント](https://renmori.mewbaka.cn/ja/cli/overview) と [renmori.toml の例](https://renmori.mewbaka.cn/ja/cli/configuration) を参照してください。

---

## 2. ドキュメント

完全なドキュメントは **[renmori.mewbaka.cn](https://renmori.mewbaka.cn/ja/)** にあります。利用の流れに沿った主要ページ:

**理解する**

- [はじめに](https://renmori.mewbaka.cn/ja/guide/introduction) — RenMori とは何か、何を保護するのか
- [既存手法の調査](https://renmori.mewbaka.cn/ja/technical/research) — 既存のツールと、新しいツールが必要な理由
- [アーキテクチャ](https://renmori.mewbaka.cn/ja/technical/architecture) — レイヤーごとの完全な設計
- [脅威モデル](https://renmori.mewbaka.cn/ja/technical/threat-model) — 何を防げて、何を防げないか

**ゲームを保護する**

- [クイックスタート](https://renmori.mewbaka.cn/ja/guide/quick-start) — ビルドから保護済みリリースまで
- [CLI リファレンス](https://renmori.mewbaka.cn/ja/cli/overview) — `protect` / `verify`、引数、出力
- [設定](https://renmori.mewbaka.cn/ja/cli/configuration) — `renmori.toml` 設定ファイル
- [プラグイン](https://renmori.mewbaka.cn/ja/cli/plugin) — ベースラインと完全保護、閉源バイナリ

**CI で自動化する**

- [CI と鍵管理](https://renmori.mewbaka.cn/ja/integration/ci) — パイプライン、シークレット、GitHub Actions のサンプル

**リリースする**

- [Steam 配信](https://renmori.mewbaka.cn/ja/integration/steam-release) — オーバーレイ・DRM・Steamworks

**内部構造とリファレンス**

- [コンテナ形式](https://renmori.mewbaka.cn/ja/technical/container-format) · [ローダーフック](https://renmori.mewbaka.cn/ja/technical/loader-hook) · [スクリプト層](https://renmori.mewbaka.cn/ja/technical/script-layer) · [プラグインインターフェース](https://renmori.mewbaka.cn/ja/technical/plugin-interface)

---

## 3. ライセンス

RenMori ——フレームワークとツール、閉源プラグイン、そしてゲームに同梱される実行時ランタイム——は **RenMori License 1.0** の下で提供されます: [`LICENSE`](LICENSE)（中国語: [`LICENSE.zh-CN.md`](LICENSE.zh-CN.md)）。

- **無料で利用可能** — Ren'Py ゲーム（商用・非商用を問わず）の保護は無料で、RenMori ランタイムはリリース済みゲームに同梱して再配布しても無料です
- **再販は禁止** — RenMori 本体やその改変版を販売すること、またそれを使った有料の「代行暗号化」サービスを運営することはできません
- これは **source-available（ソース公開）** ライセンスであり、OSI のオープンソースライセンスではありません。「再販禁止」という条項は寛容型ライセンスでは表現できないためです

サードパーティの告知は [`NOTICE`](NOTICE) を参照してください（FFmpeg の LGPL/GPL 条項に注意）。解析不能性は一切保証しません。ライセンスと [脅威モデル](https://renmori.mewbaka.cn/ja/technical/threat-model) を参照してください。

完全な条項・提出要件・開発者向けの説明はドキュメントサイトにあります: [免責事項](https://renmori.mewbaka.cn/ja/license/disclaimer)、[提出要件](https://renmori.mewbaka.cn/ja/license/contributing)、[開発者向けのヒント](https://renmori.mewbaka.cn/ja/license/developer-notes)。

本プロジェクトのライセンスに関するお問い合わせ／技術サポートは、メール: *team@mewbaka.cn* までご連絡ください。
