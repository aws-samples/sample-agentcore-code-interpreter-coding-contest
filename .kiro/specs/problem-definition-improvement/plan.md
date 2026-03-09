# 問題定義方法の改善計画

## 背景

このリポジトリは aws-samples として公開されており、AWS サービスの活用例を示すサンプルコードとしての役割を持つ。利用者がフォークして自身のコンテストを開催することを想定しているため、コード量が少なく読みやすいこと、カスタマイズしやすいことが重要である。特に問題の追加・編集は最も頻繁に行われるカスタマイズであり、その体験を改善することはサンプルとしての実用性に直結する。

現在、問題は `contents/problems.json` に全問題を1ファイルで定義している。テストケースの入力・期待出力を手書きJSONで管理しているため、問題作成者がテストケースの正しさを検証しづらい。`tests/test_markdown_problem.py` のような検証スクリプトが個別に存在するが、統一された仕組みがない。

## 課題

1. テストケースが正しいことを体系的に検証する手段がない
2. 正解コード（参照実装）が問題定義に含まれていない
3. 問題追加時に巨大なJSONを編集する必要があり、差分が見づらい

## 変更方針

### 0. uv への移行

`requirements.txt` を廃止し、`uv` によるプロジェクト管理に移行する。

**理由:**
- バージョンロック（`uv.lock`）による再現可能なビルド
- 問題のローカル検証に必要なライブラリ（例: commonmark）の管理

**依存関係の分類:**
- プロジェクト依存: `aws-cdk-lib`, `constructs`, `boto3` 等（CDKデプロイ用）
- 開発依存（dev）: `commonmark` 等（問題のローカル検証用。`test_solver.py` が参照実装の検証に使用）、`ruff`（lint/format）

**注意:** Code Interpreter環境には追加ライブラリを入れない。参加者の提出コードはPython標準ライブラリのみ使用可能。ローカル検証用ライブラリはあくまで問題作成者が `solver.py` + `test_solver.py` の正しさを確認するためのもの。

**影響:**
- `requirements.txt` → `pyproject.toml` + `uv.lock` に置き換え
- `pyproject.toml` に ruff のベーシックな lint/format 設定を追加（`[tool.ruff]` セクション）
- README.md, RUNBOOK.md のセットアップ手順を `uv sync` に変更
- `cdk` コマンドの実行は `uv run cdk ...` に変更

### 1. 問題ディレクトリ構造の導入

```
contents/
├── bracket-depth/
│   ├── metadata.json      # title, description, examples, order, enabled
│   ├── solver.py           # 正解コード（参照実装、デプロイしない）
│   └── test_solver.py      # unittest形式のテストケース（S3にデプロイ）
├── country-quiz/
│   ├── metadata.json
│   ├── solver.py
│   ├── test_solver.py
│   └── assets/             # 画像等の静的アセット（Web Bucketにデプロイ）
│       └── country.jpg
└── ...
```

- `solver.py`: 正解コードの参照実装。ローカル検証専用でデプロイしない
- `test_solver.py`: Python標準 `unittest` 形式。`from solver import solver` してテストする。Submit Lambda経由でCode Interpreterにアップロードされ、採点に使用される
- `metadata.json`: フロントエンド表示用および出題制御用。構造は下記参照
- `assets/`: 画像等の静的アセット。各問題ディレクトリ内にまとめる。Web Bucketにデプロイされる

### 問題IDの設計

ディレクトリ名がそのまま問題ID（`problem_id`）となる。従来の `problem_number`（整数）は廃止する。

- Submit API: `"problem_id": "bracket-depth"`
- DynamoDB: `problem_id` (String)
- Leaderboard: 問題ID一覧から動的に列を生成
- フロントエンド: 問題ID + タイトルで表示

### metadata.json の構造

```json
{
  "title": "括弧ネスト深度",
  "order": 1,
  "enabled": true,
  "description": [
    "引数として括弧文字列sを受け取り、..."
  ],
  "examples": [
    { "input": "solver(\"({[]})\")", "output": "3" }
  ]
}
```

- `order`: 表示順序を制御する整数。Problems APIはこの値で昇順ソートして返す
- `enabled`: `false` の問題はProblems APIから返されず、Submit APIでも受け付けない

### 2. ローカル検証

問題作成者は `python -m pytest contents/<problem-name>/test_solver.py`（または `python -m unittest`）で、正解コードとテストケースの整合性をローカルで検証できる。

### 3. S3バケットの分離

- **Web Bucket（既存）**: フロントエンド静的ファイル、画像アセットを配置。ゲーム参加者からCloudFront経由でアクセス可能
- **Problems Bucket（新規）**: 各問題の `test_solver.py` を配置。Submit Lambdaのみがアクセスする。ゲーム参加者からはアクセス不可

Problems Bucketのキー構造:
```
bracket-depth/test_solver.py
country-quiz/test_solver.py
...
```

### 4. Submit Lambdaの採点方式変更

現在の方式（テストケースごとに `solver(input)` を実行して文字列比較）を廃止し、以下に変更する:

1. Problems Bucketから `test_solver.py` を取得（`enabled: true` の問題のみ受け付ける。`metadata.json` の `enabled` を確認）
2. Code Interpreterセッションを開始
3. ユーザー提出コードを `solver.py` として書き込む
4. `test_solver.py` を書き込む
5. unittestをPython APIで実行するラッパーコードを実行:
   - `unittest.TestLoader` でテストを読み込み、`unittest.TextTestRunner` で実行
   - 結果から `testsRun`, `failures`, `errors` の数値のみを出力
   - テスト名・エラーメッセージは出力しない（答えの漏洩防止）
6. 出力をパースし、全テストパス（failures + errors == 0）なら正解
7. レスポンスには `n/m passed` の形式のみ返す

### 5. Problems API の新設

新しいLambda + API Gatewayエンドポイント `GET /problems` を追加する。

- ゲーム停止中（`game_active == False`）→ 問題データを返さない
- ゲーム進行中（`game_active == True`）→ `enabled: true` の問題のみ返す

このLambdaはProblems Bucketから各問題の `metadata.json` を読み込み、`enabled: true` のもののみフィルタして返す。

**metadata.jsonの配置先**: Problems Bucket に `metadata.json` も配置する。Problems Lambda が Problems Bucket から読み込む。

### 6. フロントエンド変更

- `problems.html`: `fetch('/problems.json')` → `fetch('${API_URL}/problems')` に変更
- `index.html`: 問題数の取得を同じAPIから行う
- ゲーム停止中は問題一覧が表示されない旨のUIを表示

### 7. CDKスタック変更

- **Problems Bucket**: 新規S3バケットを追加（BlockPublicAccess.BLOCK_ALL）
- **BucketDeployment**: `contents/` から `test_solver.py` と `metadata.json` を Problems Bucket にデプロイ。画像アセットは Web Bucket にデプロイ
- **Problems Lambda**: 新規Lambda関数。Problems Bucket の読み取り権限、GameState DynamoDB の読み取り権限を付与
- **API Gateway**: `GET /problems` エンドポイントを追加
- **Submit Lambda**: 環境変数に `PROBLEMS_BUCKET` を追加。Problems Bucket の読み取り権限を付与。`WEBSITE_BUCKET` からの `problems.json` 読み込みは廃止
- **Leaderboard Lambda**: 問題数のハードコード（`problem1_time` 〜 `problem4_time`）を動的化。Problems Bucket または環境変数から問題一覧を取得

### 8. Leaderboard Lambdaの動的化

現在 `problem1_time` 〜 `problem4_time` をハードコードしている箇所を、問題一覧から動的に生成するよう変更する。Problems Bucketから `enabled: true` の問題ID一覧を取得し、各問題IDに対応する列を動的に構築する。DynamoDBの `problem_number` カラムも `problem_id` (String) に変更する。

### 9. BucketDeploymentの設計

CDKデプロイ時に `contents/` ディレクトリを処理するビルドスクリプト（Python）を用意する:

- 各問題ディレクトリから `test_solver.py`, `metadata.json` を収集し、Problems Bucket用のソースを構成
- 各問題ディレクトリから `assets/` 内の画像アセットを収集し、Web Bucket用のソースを構成
- `solver.py` はデプロイ対象外

CDKの `BucketDeployment` で:
- Problems Bucket: `test_solver.py`, `metadata.json` をデプロイ
- Web Bucket: `website/` + `assets/` 内の画像アセット + `config.js` をデプロイ（現在の `problems.json` のデプロイは廃止）

### 10. 既存の `tests/test_markdown_problem.py` の扱い

この検証スクリプトの役割は `contents/markdown-bold/test_solver.py` に統合される。`tests/` ディレクトリは削除する。

### 11. 既存バグ・非効率の修正

#### Lambda@Edge の SSM 毎回呼び出し

`lambda_edge/basic_auth.py` がリクエストごとに SSM `get_parameter` を2回呼んでいる。Lambda@Edge は環境変数を使えないため、グローバル変数にキャッシュする方式に変更する。

#### `problem.js` の API_URL ハードコード

`website/problem.js` で API_URL がハードコードされている。`index.html` や `admin.html` と同様に `window.API_CONFIG?.url` から読むよう修正する。

## 影響範囲

| ファイル/リソース | 変更内容 |
|---|---|
| `requirements.txt` | 廃止。`pyproject.toml` + `uv.lock` に置き換え |
| `pyproject.toml` | 新規。プロジェクト依存 + dev依存の定義 |
| `contents/problems.json` | 廃止。各問題ディレクトリに分割 |
| `contents/<name>/metadata.json` | 新規。title, description, examples, order, enabled |
| `contents/<name>/solver.py` | 新規。正解コード（ローカル検証用） |
| `contents/<name>/test_solver.py` | 新規。unittest形式テストケース |
| `lambda/submit.py` | 採点方式を全面変更 |
| `lambda/leaderboard.py` | 問題数の動的化 |
| `lambda/problems.py` | 新規。問題一覧API |
| `programming_contest/programming_contest_stack.py` | Problems Bucket, Problems Lambda, APIエンドポイント追加 |
| `website/problems.html` | API呼び出し先変更 |
| `website/index.html` | 問題数取得方法変更 |
| `lambda_edge/basic_auth.py` | SSMキャッシュ追加 |
| `website/problem.js` | API呼び出し先変更（該当箇所があれば）、API_URLハードコード修正 |
| `tests/test_markdown_problem.py` | 廃止 |
| `RUNBOOK.md` | 問題編集方法セクションを更新 |
| `README.md` | 問題定義方法の説明を更新 |

## 使用技術

- Python `unittest`: テストケース定義・実行
- uv: プロジェクト管理・依存関係ロック
- ruff: Python lint/format
- Amazon S3: Problems Bucket（テストケース・メタデータ格納）
- AWS Lambda + API Gateway: Problems API
- Amazon Bedrock AgentCore Code Interpreter: `unittest` ラッパーコードによる採点実行
- AWS CDK (Python): インフラ定義
