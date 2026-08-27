# hayfield-entrance

ヘイフィールド 求職者向けEntrance Book（Notion CMS → 静的HTML → GitHub Pages）。

- CMS: Notion「【求職者向け】ヘイフィールド Entrance Book（HP編集用）」
- 生成: `python3 generate_site.py site_out`（`NOTION_TOKEN` 必須）
- デプロイ: GitHub Actions（毎日 9:00 / 17:00 JST + 手動 + push時）→ GitHub Pages
- 内容修正はNotion側を編集（次回ビルドで反映）。デザインは `site_template.html`。
