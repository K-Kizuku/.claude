# 引き継ぎの保存と再開

Git repoでは`git rev-parse --git-common-dir`の結果を現在のdirectoryから絶対pathへ解決し、その下の`agent-state/<task-id>/handoff.md`に保存する。.gitが通常directoryとは限らない。並列担当は`handoff-<agent-id>.md`に分ける。Git管理領域への書込がruntimeで保護されている場合は、その保護を解除せずOSのuser state directoryの`agent-settings/handoffs/<repo-id>/<task-id>/`を使い、実際のpathを明示する。

repo外の作業もuser state directoryへ保存する。macOSは`~/Library/Application Support/`、Linux/WSL2は`$XDG_STATE_HOME` (未指定なら`~/.local/state/`) を基準にする。repo-id/task-idは短い安全な識別子とし、別repoの記録を混ぜない。

```markdown
# <タスク名>
- 記録時刻:
- 目的・完了条件:
- branch / worktree / HEAD:
- dirty変更path:
- 完了 / 未完了 / 阻害要因:
- 判断と根拠:
- plan / Issue / PR / ADR:
- 検証コマンド・対象状態・結果 / 未検証:
- active agent (ID・担当・最終観測):
- 承認済みの作用と対象:
- 次の1〜3手:
```

記録は経緯であり、外部の状態は記録時点の観測。再開時はGit/PR/Issue/agentを開き直す。動作中の可能性があるagentを確認せず二重起動しない。会話全文や既存成果物を複写せず参照する。秘密を含めない。

短期記録は完了後にarchiveを検討し、自動削除しない。長く有効な判断は必要な時だけProjectのADRへ移す。恒久指示へ自動的に昇格させない。
