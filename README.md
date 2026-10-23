# Agent settings

Codex CLIとClaude Codeで共有する、個人用のAIエージェント設定です。指示は`AGENTS.md`に統一し、4つのSkillsを両CLIから同じ実体で利用します。

## はじめる

macOS / Linux / WSL2、Python 3.11以上、Gitが必要です。Claude CodeはnativeのProject AGENTS.mdを読める現行版を使用します。

```sh
git clone https://github.com/K-Kizuku/.claude.git "$HOME/src/agent-settings"
cd "$HOME/src/agent-settings"
python3 scripts/install.py
python3 scripts/install.py --apply
python3 scripts/doctor.py
```

最初のコマンドはプレビューだけです。既存設定があれば適用を中止します。[既存環境の導入・更新・復元](docs/setup.md)を参照してください。clone先を`~/.claude`や`~/.codex`にしないでください。

## 共通化するもの

| 実体 | Codex | Claude Code |
|---|---|---|
| `AGENTS.md` | `~/.codex/AGENTS.md`へlink | `~/.claude/rules/AGENTS.md`へlink |
| `skills/<name>/` | `~/.agents/skills/<name>`へlink | `~/.claude/skills/<name>`へlink |
| CLI設定 | `templates/codex/config.toml`をcopy | `templates/claude/settings.json`をcopy |

Projectでは[AGENTS.mdの雛形](templates/project/AGENTS.md)にrepo固有のコマンド・境界を記述します。Skillsの実体と共通指示はこのcheckoutで編集します。設定copyの変更はtemplateと自動同期しません。

| Skill | 使う時 | Codex / Claude |
|---|---|---|
| systematic-debugging | 原因不明・修正後も続く失敗 | `$systematic-debugging` / `/systematic-debugging` |
| verify-changes | 振る舞い変更後の検証 | `$verify-changes` / `/verify-changes` |
| self-review | 自分の差分を確認 | `$self-review` / `/self-review` |
| handoff | セッションの切替・中断 | `$handoff` / `/handoff` |

descriptionに合う依頼では自動選択も可能ですが、実際の発動はCLI・モデル・設定で変わります。[利用フロー](docs/workflow.md)、[CLIの確認手順と互換性](docs/compatibility.md)、[評価ケース](evals/README.md)を参照してください。

## 設定の保守

```sh
python3 scripts/check.py
python3 -B -m unittest discover -s tests -v
```

依存はPython標準ライブラリだけです。CIはLinux/macOSで形式と保全テストを実行し、モデル・認証・本番データを使いません。[検証記録](docs/verification.md)には実施済みと未実施を分けています。

初期構成は独自Hook・モデル固定・自動pushを含みません。承認とsandboxを維持するuser-levelの既定であり、管理者ポリシーや全経路のセキュリティ境界ではありません。
