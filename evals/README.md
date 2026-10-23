# Skill発動の評価

[cases.json](cases.json)は4 Skillsについて明示1件・正例2件・負例2件ずつ、合計20件です。両CLIで1回ずつ行うと40 runになります。CIはこのfileの構造のみを確認し、モデルを呼びません。

既存の指示や会話履歴による影響を避けるため、各caseは新しいsessionと使い捨てrepoで開始します。コード/設定/dirty差分/未完了taskなど、promptが必要とするfixtureを準備します。存在しないPR番号を実アカウントへ書き込んで試さないでください。

- explicitは`invocation`から対象CLIの記法を選び、`prompt`とともに送る。
- positiveはSkill名を追加せず、自然言語だけで送る。
- negativeは対象Skillの誤発動がないか見る。他の適切なSkillの利用は許容する。
- CLIのactivation表示やSkill本文の読込を証拠にする。モデルが「使った」と言うだけでは発動確認にならない。
- referencesは必要なcaseで読まれ、単純なcaseで全件読み込まれないことを観測する。

記録項目はcase ID、OS/CLI/model/source commit/日時、fixture、期待と実際、発動の証拠、成果物の確認、未承認作用の有無。読込イベントを取得できない場合は不明とし、0や成功に変換しません。秘密やraw会話をrepoへ入れません。

明示発動と安全上の負例は全件成功が目標です。暗黙発動の不一致はdescriptionとscopeを調整し、失敗/曖昧caseを複数回再実行します。少ない標本の一致を一般的な発動率と宣伝しません。Skillを呼んだ回数とタスクの品質は別に評価します。
