# 仕様とCLIの確認

調査日: 2026-10-24 (JST)。以下は公式資料で確認した仕様と、ローカルで確認する手順です。本物の両CLIによる挙動検証は[検証記録](verification.md)で別に示します。

| 機能 | 公式仕様 | 根拠 |
|---|---|---|
| Codex global指示 | CODEX_HOMEのAGENTS.override.mdが優先、なければAGENTS.md | [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) |
| Codex Project指示 | rootからCWDまでの指示を合成。既定の合計上限32 KiB | [AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md) |
| Codex user Skills | ~/.agents/skills、Skill folderのsymlinkに対応 | [Build skills](https://learn.chatgpt.com/docs/build-skills) |
| Codex設定 | on-request承認、workspace-write sandbox | [Config basics](https://learn.chatgpt.com/docs/config-file/config-basic) |
| Claude global指示 | user rulesのMarkdownを読込。共通AGENTS.mdへlink | [User-level rules](https://code.claude.com/docs/en/memory#user-level-rules) |
| Claude Project指示 | 現行版のnative AGENTS.md対応。v2.1.277より前は対象外 | [AGENTS.md](https://code.claude.com/docs/en/memory#agentsmd) |
| Claude Skills | personalの~/.claude/skills、個別folderのsymlinkに対応 | [Skills](https://code.claude.com/docs/en/skills) |
| Claude編集 | acceptEditsで作業範囲のfile編集を進める | [Permissions](https://code.claude.com/docs/en/permissions) |
| Claude sandbox | enabled、regular permissions、unsandboxed retry禁止、依存不足時の開始拒否 | [Sandboxing](https://code.claude.com/docs/en/sandboxing) |

Claudeのnative AGENTS.mdは内蔵機能が有効なsessionで使用します。旧指示fileがproject/親にある場合やProject instructions設定によっては読まれません。古いCLI向けの互換fileは生成しません。v2.1.277はnative AGENTS.mdの文書上の導入版であり、template内の全キーがその版で動くと検証した意味ではありません。現行版で下記を確かめてください。

## 実CLIのsmoke手順

認証は各CLIの公式の方法で準備します。このrepoのscriptsにtokenを渡す必要はありません。使い捨てrepoで、導入した設定と信頼・権限の実効値を確認します。

1. `codex --version` / `claude --version`とOSを記録し、`python3 scripts/doctor.py --project PROJECT_PATH`を実行。
2. Codexを起動し`/status`、Claudeを起動し`/memory` / `/context` / `/permissions` / `/sandbox`で指示・Skills・権限を確認。表示コマンドが版で変わったらそのCLIのhelpを正とする。
3. GlobalとProject AGENTS.mdの冒頭/末尾に一時的な無害のmarkerを置く。両方が読み込まれ、Projectの具体的コマンドが適用されることを観測。確認後markerを除去する。
4. nested Project、既存AGENTS.override.md、旧指示の同居、無効化設定も負例として確認。意図せず共通指示が消えていたら成功としない。設定repo自身を開いた場合の重複読込も観測する。
5. [20ケース](../evals/cases.json)を各CLIで試し、発動/非発動・参照の必要時読込を観測する。
6. 隔離fixtureのworkspace外sentinelへ書けないこと、未承認の外部作用でnative approval/拒否が出ることを確認。実データや本物の送信先を使わない。
7. 小さな振る舞い修正を行い、検証・差分確認・handoffを試す。別CLIで再開してHEAD/dirty/agentの再確認が行われるか観測する。

runごとに日時、source commit、OS、CLI版、モデル、case、結果、必要最小限の証拠をローカルに残します。会話・config・秘密のraw出力を公開しません。モデルを使う試験は利用枠を消費するためopt-inで実施し、通常CIには含めません。

## 限界

user-level設定は管理者policyではありません。CLI引数、Project/managed設定、配列の合成、既存allow、MCPの権限は実効値を変えます。doctorは静的警告であり、全経路の安全性やSkillの発動を証明しません。

Claude Linux/WSL2のsandboxにはOS側依存やkernelの能力も必要です。doctorはbwrap/socatの存在を確認しますが、kernelで動くことまでは保証しません。失敗時にsandboxを外さず、[公式手順](https://code.claude.com/docs/en/sandboxing)で準備します。macOS・SwiftUI・iOSの動作をLinuxだけで検証済みと表示しません。

共通本文にClaude専用の@importやmodel固定はありません。CLI設定は別々で、Hooksは未導入です。CodexのrulesやClaudeのshell patternも全経路を遮断する境界とせず、高riskな操作はcredentialと実行環境を分離してください。
