# 日常の使い方

小さな修正は、対象を読む→直す→必要な確認で完了します。通常の編集ごとに計画書・外部review・worktree・handoffを作る必要はありません。

| 作業 | 使用例 | 確認 |
|---|---|---|
| 原因不明の不具合 | 「修正後も同じテストが落ちます。原因から調べて直してください」 | 再現、仮説、原因、元の経路での解消 |
| 振る舞い変更後 | 「この変更を影響範囲に合わせて検証してください」 | Projectのtest/build、実際の設定やUI |
| 自作の差分 | 「自分の差分に要件漏れやバグがないか確認してください」 | committed/staged/unstaged/必要なuntracked |
| セッション切替 | 「別のCLIへ切り替えるので引き継いでください」 | 記録path、次の行動、Git/agentの再確認先 |

確実にSkillを選ぶ時はREADMEの`$name` (Codex) / `/name` (Claude) を使います。自動発動の証拠は本文の読込やCLIの表示から確認し、モデルの自己申告だけで判断しません。

新機能では既存仕様・受入条件・変更箇所・検証を必要な粒度で整理します。実装まで依頼されているなら承認範囲で続行します。認可/移行/データ削除/公開などの不可逆な作用は、具体的な影響と復旧を明らかにして承認を確認します。計画専用Skillはこの初期構成には含めません。

認証・データ整合性等の高risk変更では、利用可能な反対側CLIによる独立reviewを検討します。対象SHAとdirty差分を固定し、書込不能snapshotや権限を絞ったtoolを使います。Bashを許可しただけでread-onlyとは呼びません。別モデルを使えない時は未実施とし、不可逆な実行の判断と実装/局所検証を区別します。詳細なcross-review自動化は未導入です。

## Projectごとの違い

[雛形](../templates/project/AGENTS.md)を必要なrepoの`AGENTS.md`として使い、実際のコマンド・重要な境界・base branchを埋めます。既存fileがある場合は内容を確認してmergeし、丸ごと上書きしません。Claudeのnative読込を妨げる旧指示や設定はdoctorと`/memory` / `/context`で確認します。

Globalの短い既定、Project固有の仕様、必要時のcontext/Skillsを分けます。Codex専用のAGENTS.override.mdを両CLI共通の上書きには使いません。相反する自然言語指示は消すか整理し、機械的な設定の優先順位だけで必ず解消されると考えないでください。

## 並列と中断

標準subagentを使う価値がある独立作業だけを分け、既定は親+子1体です。編集のfile所有とworktreeを分け、共有lockfile/schemaは親で集約します。worktreeはport/DB/simulator/credentialを分離しません。子の結果は親がGitの実体と検証証拠で確認します。

handoffは[記録方法](../context/handoff.md)に従います。再開は記録→Git実体→必要なPR/Issue→agentの現在状態を確認します。長期の判断は必要な時にADRへ、恒久ルールは実際の反復失敗を根拠に整理します。記録や分析から自動的にルールを増やしたりpushしたりしません。
