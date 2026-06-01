# gh-trending-daily

每天抓取 GitHub Trending，生成精美的每日报告，部署到 GitHub Pages。

## 目录

```
gh-trending-daily/
├── scripts/
│   ├── fetch_trending.py   # 抓取 trending 页面 → data/*.json
│   ├── render_html.py      # 渲染 JSON → site/*.html
│   └── publish.py          # push 到 GitHub Pages (gh-pages 分支)
├── data/                    # 历史数据 JSON
├── site/                    # 生成的 HTML（推到 gh-pages）
├── run.sh                   # 一键跑全流程
└── .gitignore
```

## 配置 (~/.hermes/.env)

```bash
GITHUB_TOKEN=ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
GH_OWNER=gitgubjie
GH_REPO=gh-trending-daily   # 可选，默认 gh-trending-daily
```

## 一次性 GitHub 仓库初始化

1. 登录 https://github.com/new
2. 仓库名 `gh-trending-daily`、Public、**不**勾选任何初始化选项
3. Settings → Pages → Source: `gh-pages` branch, `/ (root)`

## 手动跑一次

```bash
bash run.sh
```

## 自动跑（cron 21:00 每天）

由 Hermes 调度，全流程跑完后通过微信发送 GitHub Pages 链接。
