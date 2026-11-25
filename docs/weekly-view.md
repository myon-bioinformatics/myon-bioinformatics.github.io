# 公開用週次台帳ビュー

このビューはPortfolIO内の `#weekly` で開くMarkdown由来のHTMLです。新しいURLパスやJavaScriptルーターは使いません。

## 正本と表示の分離

- [親リポジトリの監査ページ](https://myon-bioinformatics.github.io/myon-bioinformatics/)：PR・Issue・CI・固定SHA・証跡・週次記録の正本
- [監査データのソース](https://github.com/myon-bioinformatics/myon-bioinformatics)：生成・集計・検証の実装
- このビュー：公開用の案内と文書を表示。GitHubやChatGPTの非公開タスクを自動取得しません。

## 次の共通化対象

1. MarkdownからHTMLへの変換は既存の `markdown.py` に集約する。
2. タブ・ルーム・共通ナビ・スクロールはPySaiyanWeBooの既存部品を利用する。
3. 週次データの収集・比較・検証は親リポジトリに残す。
4. 静的HTMLへの埋め込みと `#weekly` のリンクを検証し、再利用可能な表示契約だけをPSWBへ還元する。

**注記：** ここには最新のCI成功数や自動化の稼働数を転記しません。実測値は正本を参照してください。
