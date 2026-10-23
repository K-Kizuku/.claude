# 検証の選び方

受入条件からcheckを選び、ProjectのREADME/scripts/CIを正とする。コマンド未確定の雛形を実行しない。

| 変更 | 選ぶcheckの例 |
|---|---|
| 通常のロジック | 対象test、関連する型検査・lint |
| 依存/設定/起動 | parse、build、起動、設定が有効なことの実測 |
| API/DB | 境界のintegration、認可・状態・失敗時の整合性 |
| UI | build、実操作、表示の確認 (可能ならスクリーンショット) |
| Swift/SwiftUI | 利用可能なMac/Xcodeでbuild/test/表示。別OSの静的検査は補助 |
| docsの小修正 | 差分・リンク・表示。全testや外部reviewは不要 |

実行前に対象環境・credential・ネットワークの有無を確認する。未信頼のscriptsを高権限で実行しない。結果はpass/失敗/未実施に分け、timeoutや依存不足をpassへ置き換えない。既存失敗と今回の回帰を区別する。

同じ状態への証拠は再利用し、変更後に影響するcheckだけ更新する。完了報告にはコマンド・対象状態・結果・確認できなかった範囲を残す。設定構文のpassだけでCLIの読み込みや暗黙Skill発動を保証しない。
