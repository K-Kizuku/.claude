# 導入・更新・復元

## 前提

- macOS、Linux、またはWSL2。native Windowsとネットワークdriveへの配置は対象外。
- Python 3.11以上、Git、利用するCLIの現行版。installerはCLIや認証を導入しない。
- 別checkoutで管理する。`~/.claude` / `~/.codex`自体をrepoに置き換えない。
- 設定に書くキーのCLI対応とsandbox依存は[互換性](compatibility.md)で確認する。未対応ならupdateしてから使用する。

## 新しいPC

READMEのclone後、checkoutのdirectoryから実行します。bash/zsh/fishで同じ呼び方です。

```sh
python3 scripts/install.py
python3 scripts/install.py --apply
python3 scripts/doctor.py
```

`--apply`はその場で再評価した配置へ適用します。別の実行で見たpreviewに厳密に結び付けるには、表示されたdigestを`--expect`へ渡します。

```sh
python3 scripts/install.py --apply --expect DIGEST_FROM_PREVIEW
```

リンク10件と設定copy2件が対象です。両CLIのruntime directory全体、ログ、認証、MCP設定には触れません。source内容・対象file・親directoryがpreviewから変わっていたら停止します。previewは設置先や状態directoryに書き込みません。

## 既存設定があるPC

`conflict`は通常file、異なるlink、broken link等を表します。衝突が1件でもあればapply全体を中止します。既存Skillと指示を無断で削除・上書きしません。symlinkされた親directoryも止めるため、実体pathの確認が必要です。

既存の設定fileを維持してリンクだけ導入する場合:

```sh
python3 scripts/install.py --keep-configs
python3 scripts/install.py --keep-configs --apply
```

その後、[Codex template](../templates/codex/config.toml)と[Claude template](../templates/claude/settings.json)の管理対象キーを既存設定へ手動で整理し、doctorと実CLIで確認します。keepは安全設定の適用完了を意味しません。未作成のconfigはkeep指定でも新規作成します。

既存の**通常の設定file全体**をtemplateで置き換えると明示的に決めた場合は、previewとdigestを使います。既存のモデル・MCP・個人設定も置き換わるため、通常は手動mergeを推奨します。

```sh
python3 scripts/install.py --replace-config codex
python3 scripts/install.py --replace-config codex --apply --expect DIGEST_FROM_PREVIEW
```

両方を置き換える時は`--replace-config codex --replace-config claude`をpreview/apply両方に付けます。置換前のbytesをprivate backupへ保存します。設定のsymlinkやdirectoryは置換しません。既存値のraw差分をstdoutへ出さないため、内容の比較は秘密を出力しないローカルeditorで行ってください。

## オプションと終了コード

| コマンド | 効果 |
|---|---|
| 引数なし | previewのみ |
| `--apply` | 衝突のない計画を適用 |
| `--expect DIGEST` | そのpreviewと一致する時だけ続行 |
| `--keep-configs` | 既存configを保持。linkの衝突は無視しない |
| `--replace-config codex` / `claude` | 指定の通常configをbackup後に置換。applyにはdigest必須 |
| `--rollback ID` | そのtransactionが設置した未変更の対象だけ復元 |
| `--help` | 利用可能な引数を表示 |

installは成功/衝突なしpreviewで0、衝突・復元競合・エラーで2。doctorは警告/不足があれば1、診断不能は2。checkは違反があれば1を返します。CLI未導入でも配置は準備できますが、doctorは未検証・不足を報告します。

## マシン固有path

`CODEX_HOME` / `CLAUDE_CONFIG_DIR`を設定済みなら尊重します。未指定は`~/.codex` / `~/.claude`です。Codexのuser Skillsは`~/.agents/skills`のままです。

```sh
env CODEX_HOME=/absolute/codex-config CLAUDE_CONFIG_DIR=/absolute/claude-config python3 scripts/install.py
```

相対pathは実行directoryから絶対化します。混乱を避けるため絶対pathを推奨します。preview/apply/rollback/doctorは同じ環境変数で実行してください。これらの変数をinstallerが変更することはありません。

## 更新とロールバック

instructions/Skillsはsymlinkなのでcheckoutの編集やpullが直ちに反映されます。利用中の設定自身を変更する時は、他のagent sessionを閉じるか別の作業checkoutで検証し、承認済みcommitへ揃えてから再開してください。config copyの更新はpreview後に手動merge、または明示的なreplaceで行います。

適用時に表示するRollback IDを使います。

```sh
python3 scripts/install.py --rollback TRANSACTION_ID
```

置換前のfileは元のbytesとpermissionへ戻し、新規設置したfile/linkだけ解除します。設置後にユーザーやCLIが変えた対象は保持して競合を報告します。空のdirectoryとbackupは残します。source repo自体の編集・commitは戻しません。sourceの復元はGitの確認済みcommitへの切替で別に行います。

状態とbackupはmacOSで`~/Library/Application Support/agent-settings/`、Linux/WSL2で`$XDG_STATE_HOME/agent-settings/` (未指定は`~/.local/state/agent-settings/`)。transaction directoryは0700、manifest/backupは0600です。既存の状態directoryが公開permissionなら停止します。backupに旧configの秘密が含まれる場合があるため、このdirectoryをGitや共有driveへ入れないでください。

途中失敗では`interrupted`/`pending`をmanifestに残します。表示されたIDで復元できます。強制終了で`install.lock`が残った場合は、他のinstallerが動いていないこととmanifestを確認してからlockだけを手動解除し、rollbackします。未知のprocessやbackupを削除して復旧しないでください。

同じinstaller間はlockで直列化し、新規fileはno-clobberで作成します。別の悪意あるprocessによる同時置換まで防ぐOSの完全なtransactionではありません。CLIを閉じて導入・復元し、変更済みの対象を強制上書きしない運用を前提にします。
