# 検証記録

2026-10-24 (JST)、Phase 1実装時の記録です。Linux / Python 3.12.14 / Git 2.51.1で実施しました。

| 確認 | 結果 |
|---|---|
| sourceの構文・参照・context予算・Skill形式・tracked-file検査 | 実施。`python3 scripts/check.py` |
| isolated setup / recovery / doctor / hygiene tests | 実施。`python3 -B -m unittest discover -s tests -v` |
| subprocessでpreview→digest指定apply→再apply→doctor→rollback | 実施。temp homeのみを使用。preview書込0件、再apply変更0件、復元を確認 |
| 既存config/異なるlink/broken linkの衝突 | testで適用前の中止と既存内容の保全を確認 |
| backupのpermission、元のbytes/modeへの復元 | testで確認 |
| preview後のfile/source変更、同時installer、途中失敗/pending | testで検出・保全・回収を確認 |
| 導入後に変更されたfile/link | rollbackが保持することをtestで確認 |
| configの破損・drift、旧指示/native機能無効化 | doctorが値を表示せず報告することをtestで確認 |
| 本物のCodex/Claudeによる設定読込、sandbox負例、40 runのSkill発動評価 | 未実施。この環境に両CLIがないため |
| macOS / Python 3.11の実行 | ローカルでは未実施。GitHub Actionsのmatrix結果を別途確認 |

unit testの成功は本物のCLIが指示を読んだ証拠ではありません。本人PCの既存設定や認証は変更していません。[CLIのsmoke手順](compatibility.md)で利用環境における実効値・読込・発動を確認してください。

CIはLinux/macOS × Python 3.11/3.12でsource checkとunit testsを実行します。各commitのActions結果が正であり、CIの成功をモデル挙動の確認に拡大しません。テストに実token・本番データ・外部送信は不要です。

セマンティックな競合やprompt injectionの扱いは共通指示と評価ケースで定義し、決定論的な完全検出を実装したとは扱っていません。独自Hooks・cross-review自動化・継続ログ解析はこのPhase 1に含みません。
