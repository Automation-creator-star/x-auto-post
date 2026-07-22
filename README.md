# x-auto-post

@nespe_shacho のX投稿自動化リポジトリ。

## 仕組み

- `queue/` に `YYYY-MM-DD-<slot>.txt`(slot = morning / noon / night)という名前で投稿文を置く
- GitHub Actions が毎日 JST 8:00 / 12:15 / 21:00 に起動し、当日・該当スロットのファイルがあれば投稿して `posted/` に移動する
- ファイルがなければ何もしない(安全側)

## スロット

| slot | 投稿時刻 (JST) | 内容 |
|---|---|---|
| morning | 8:00 | 用語・技術解説 |
| noon | 12:15 | ITニュース解説(当日生成) |
| night | 21:00 | インフラエンジニアのキャリア・転職ネタ |

## シークレット(Settings → Secrets and variables → Actions)

`CONSUMER_KEY` / `CONSUMER_SECRET` / `ACCESS_TOKEN` / `ACCESS_TOKEN_SECRET`

## 手動実行

Actions タブ → "Post to X" → Run workflow(force_slot でスロット指定可)
