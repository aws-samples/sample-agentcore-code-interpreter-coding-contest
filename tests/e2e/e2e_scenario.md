# E2E テストシナリオ

playwright-cli による手動実行手順。`BASE_URL` はデプロイ済み環境の CloudFront URL に置換すること。

## 前提条件

- デプロイ済み環境が存在する
- 管理者認証情報を把握している (user:pass)

## 1. 管理画面ログイン & ゲーム開始

```bash
playwright-cli open BASE_URL/admin.html
# → 認証ダイアログが表示される
playwright-cli snapshot
# prompt() ダイアログに "user:pass" を入力（playwright-cli では dialog-accept を使用）
playwright-cli dialog-accept "user:pass"
playwright-cli snapshot
# 検証: ゲーム状態管理カードが表示される
# 検証: 問題セットのセレクトボックスが表示される
```

## 2. ゲーム開始

```bash
# 問題セットを選択（必要に応じて）
playwright-cli select <problemSetSelect_ref> "問題セット名"
# ゲーム開始ボタンをクリック
playwright-cli click <startBtn_ref>
playwright-cli snapshot
# 検証: ステータスが「🟢 稼働中」に変わる
# 検証: ダイアログに「✅ ゲームを開始しました」が表示される
playwright-cli click <dialog_ok_ref>
```

## 3. 問題一覧ページ確認

```bash
playwright-cli goto BASE_URL/problems.html
playwright-cli snapshot
# 検証: 問題カードが表示される（ゲーム開始中）
# 検証: 各問題に title, problem_id, description, examples が表示される
# 検証: 「提出API仕様」の details が展開できる
playwright-cli click <api_summary_ref>
playwright-cli snapshot
```

## 4. リーダーボード確認（提出前）

```bash
playwright-cli goto BASE_URL/index.html
playwright-cli snapshot
# 検証: ゲーム状態が「進行中」バッジで表示される
# 検証: リーダーボードテーブルが表示される（空 or 既存データ）
```

## 5. API 経由でコード提出

```bash
# ブラウザ外で curl 実行（別ターミナル）
curl -X POST BASE_URL/api/submit \
  -H "Content-Type: application/json" \
  -d '{"username":"e2e-test","problem_id":"prime-check","code":"def solver(n):\n    if n < 2:\n        return False\n    for i in range(2, int(n**0.5) + 1):\n        if n % i == 0:\n            return False\n    return True"}'
# 検証: レスポンスに "result": "correct" が含まれる
```

## 6. リーダーボード反映確認

```bash
playwright-cli goto BASE_URL/index.html
# 5秒待機（自動更新間隔）
playwright-cli snapshot
# 検証: "e2e-test" ユーザーがリーダーボードに表示される
# 検証: prime-check 列に解答時刻が表示される
```

## 7. ゲーム停止

```bash
playwright-cli goto BASE_URL/admin.html
playwright-cli dialog-accept "user:pass"
playwright-cli snapshot
playwright-cli click <stopBtn_ref>
playwright-cli snapshot
# 検証: ステータスが「🔴 停止中」に変わる
playwright-cli click <dialog_ok_ref>
```

## 8. ゲーム停止中の動作確認

```bash
playwright-cli goto BASE_URL/problems.html
playwright-cli snapshot
# 検証: 「ゲームは現在停止中です。開始後に問題が表示されます。」が表示される
```

## 9. リーダーボードリセット

```bash
playwright-cli goto BASE_URL/admin.html
playwright-cli dialog-accept "user:pass"
playwright-cli click <resetAllBtn_ref>
playwright-cli snapshot
# 検証: 確認ダイアログ「全てのリーダーボードをリセットしますか？」が表示される
playwright-cli click <dialog_ok_ref>
playwright-cli snapshot
# 検証: 「✅ リーダーボードをリセットしました」が表示される
playwright-cli click <dialog_ok_ref>
```

## 10. リセット後のリーダーボード確認

```bash
playwright-cli goto BASE_URL/index.html
playwright-cli snapshot
# 検証: リーダーボードが空（「まだ提出がありません」メッセージ）
```

## 注意事項

- `<xxx_ref>` は snapshot で取得した要素参照に置換すること
- prompt() ダイアログは playwright-cli の `dialog-accept` で処理する
- API 提出（ステップ5）はブラウザ外で実行し、結果をターミナルで確認する
- 各 snapshot 後に目視で検証項目を確認する
