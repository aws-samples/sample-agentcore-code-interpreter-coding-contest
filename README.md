# Code Interpreter Coding Contest

Code Interpreter Coding Contestは、様々な問題をコーディングコンテスト・タイムアタック形式で競い合うためのサーバーレスプラットフォームです。

Amazon Bedrock AgentCore Code Interpreterを活用したサンドボックスでの安全なコード実行環境、リアルタイムリーダーボード、RESTful APIを提供し、AI駆動のコーディングコンテストを簡単に開催できます。

## 主な機能

- **安全なコード実行**: Amazon Bedrock AgentCore Code Interpreterによるサンドボックス環境でのPythonコード実行
- **リアルタイムリーダーボード**: CloudFront + S3でホストされる自動更新型のWebインターフェース
- **RESTful API**: コード提出、順位取得、ゲーム状態管理のためのAPI Gateway統合
- **カスタマイズ可能な問題セット**: ディレクトリベースの問題定義で簡単に問題を追加・編集可能
- **Basic認証**: 管理画面へのアクセス制御

## 問題定義

各問題は `contents/` 配下のディレクトリとして定義します:

```
contents/
├── bracket-depth/
│   ├── metadata.json      # タイトル、説明、表示順、有効/無効
│   ├── solver.py           # 正解コード（参照実装、デプロイしない）
│   └── test_solver.py      # unittest形式のテストケース（採点に使用）
├── country-quiz/
│   ├── metadata.json
│   ├── solver.py
│   ├── test_solver.py
│   └── assets/             # 画像等の静的アセット
│       └── country.jpg
└── ...
```

- ディレクトリ名がそのまま問題ID（`problem_id`）になります
- `solver.py` はローカル検証専用で、デプロイされません
- `test_solver.py` は `unittest` 形式で、Code Interpreter上で採点に使用されます

### ローカル検証

```bash
uv run python -m pytest contents/<problem-name>/test_solver.py -v --rootdir=contents/<problem-name>
```

## デプロイ

```bash
uv sync
uv run cdk bootstrap  # 初回のみ
uv run cdk deploy -c adminUsername=<ユーザー名> -c adminPassword=<セキュアなパスワード>
```

## 使用方法

詳細はRUNBOOK.mdをご参照ください。

## アーキテクチャ

```mermaid
graph TB
    User[ユーザー]
    CF[CloudFront]
    S3Web[S3 Bucket<br/>静的Webサイト]
    S3Problems[S3 Bucket<br/>問題データ]
    APIGW[API Gateway]
    SubmitLambda[Submit Lambda<br/>コード実行・採点]
    LeaderboardLambda[Leaderboard Lambda<br/>順位取得]
    ProblemsLambda[Problems Lambda<br/>問題一覧]
    ResetLambda[Reset Lambda<br/>リセット]
    CodeInterpreter[Code Interpreter<br/>サンドボックス実行]
    DDB1[(DynamoDB<br/>Leaderboard)]
    DDB2[(DynamoDB<br/>GameState)]
    
    User -->|HTTPS| CF
    CF --> S3Web
    User -->|API Call| APIGW
    APIGW --> SubmitLambda
    APIGW --> LeaderboardLambda
    APIGW --> ProblemsLambda
    APIGW --> ResetLambda
    SubmitLambda --> CodeInterpreter
    SubmitLambda --> DDB1
    SubmitLambda --> DDB2
    SubmitLambda --> S3Problems
    LeaderboardLambda --> DDB1
    LeaderboardLambda --> S3Problems
    ProblemsLambda --> DDB2
    ProblemsLambda --> S3Problems
    ResetLambda --> DDB1
```

## データフロー

### コード提出フロー
```mermaid
sequenceDiagram
    participant U as ユーザー
    participant API as API Gateway
    participant SL as Submit Lambda
    participant S3 as Problems Bucket
    participant CI as Code Interpreter
    participant DDB1 as Leaderboard Table
    participant DDB2 as GameState Table
    
    U->>API: POST /submit<br/>{username, problem_id, code}
    API->>SL: リクエスト転送
    SL->>DDB2: ゲーム状態確認
    SL->>S3: metadata.json取得（enabled確認）
    SL->>S3: test_solver.py取得
    SL->>CI: セッション開始
    SL->>CI: solver.py + test_solver.py書き込み
    SL->>CI: unittestラッパー実行
    CI->>SL: 実行結果（passed/total）
    SL->>CI: セッション終了
    alt 全テスト通過
        SL->>DDB1: 既存記録確認
        alt 初回正解
            SL->>DDB1: 記録保存<br/>{username, problem_id, timestamp}
        end
    end
    SL->>API: 結果返却
    API->>U: {result, message}
```

### リーダーボード取得フロー
```mermaid
sequenceDiagram
    participant U as ユーザー
    participant API as API Gateway
    participant LL as Leaderboard Lambda
    participant S3 as Problems Bucket
    participant DDB1 as Leaderboard Table
    
    U->>API: GET /leaderboard
    API->>LL: リクエスト転送
    LL->>S3: enabled問題一覧取得
    LL->>DDB1: 全記録取得
    LL->>LL: ユーザー別集計・ソート
    LL->>API: ランキングデータ
    API->>U: {leaderboard, problem_ids}
```

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.
