# 每日 AI 新闻推送（GitHub Actions 版）

关机也能跑：由 GitHub 的服务器在**每天北京时间 08:00** 自动执行，抓取 AI 资讯 → DeepSeek 总结 → Server酱推送到你的微信。你的电脑无需开机。

## 目录结构

```
daily-ai-news/
├── push_news.py                    # 核心脚本：抓取 + 总结 + 推送
├── requirements.txt                # Python 依赖
├── .github/workflows/daily-news.yml# 定时工作流（每天 08:00 北京时间）
└── README.md                       # 本说明
```

---

## 部署步骤（约 10 分钟）

### 第 1 步：拿两把钥匙

**① Server酱 SendKey（推送到微信用）**
1. 打开 https://sct.ftqq.com/ ，用微信扫码登录
2. 进入「SendKey」页面，复制那串以 `SCT` 开头的 Key
3. 按提示关注「方糖」公众号（推送就发到这里）

**② DeepSeek API Key（AI 总结用）**
1. 打开 https://platform.deepseek.com/ 注册登录
2. 「API keys」→ 新建，复制 `sk-` 开头的 Key（只显示一次，务必保存）
3. 确保账户有少量余额（每天总结成本极低，约几分钱）

### 第 2 步：建 GitHub 仓库并上传代码

1. 登录 https://github.com/ （没有账号先注册）
2. 右上角 `+` → `New repository`，名字如 `daily-ai-news`，选 **Private（私有）**，创建
3. 把本文件夹 `daily-ai-news/` 里的所有文件上传上去：
   - 简单法：仓库页面点 `Add file → Upload files`，把文件拖进去提交
   - 或用 Git 命令：
     ```bash
     cd daily-ai-news
     git init
     git add .
     git commit -m "init: daily AI news push"
     git branch -M main
     git remote add origin https://github.com/你的用户名/daily-ai-news.git
     git push -u origin main
     ```

### 第 3 步：配置密钥（Secrets）

在仓库页面：`Settings` → 左侧 `Secrets and variables` → `Actions` → `New repository secret`，添加两条：

| Name（名字，必须完全一致） | Secret（值） |
|---|---|
| `SERVERCHAN_SENDKEY` | 你的 Server酱 SendKey |
| `DEEPSEEK_API_KEY` | 你的 DeepSeek API Key |

> ⚠️ 密钥只能放在 Secrets 里，**绝不要写进代码**。

### 第 4 步：立即测试一次

1. 仓库页面 → `Actions` 标签
2. 若提示启用 Actions，点绿色按钮启用
3. 左侧选 `Daily AI News` → 右侧 `Run workflow` → 绿色 `Run workflow`
4. 约 1 分钟后点进运行记录看日志；若显示 `全部完成 ✅`，微信「方糖」公众号就会收到今日 AI 要闻

### 第 5 步：完成

测试通过后就不用管了，之后**每天早上 08:00 自动推送**。

---

## 常见问题

- **没收到推送？**
  1. 看 Actions 日志里 `Server酱 推送响应` 是否 `200` 且 `"code":0`
  2. 确认已关注「方糖」公众号
  3. 确认 `SERVERCHAN_SENDKEY` 没写错、没多空格

- **想改时间？** 编辑 `.github/workflows/daily-news.yml` 里的 `cron`。
  注意是 **UTC 时间**，北京时间要减 8 小时。例如：
  - 北京 08:00 → `0 0 * * *`
  - 北京 09:00 → `0 1 * * *`
  - 北京 20:00 → `0 12 * * *`

- **想换/加新闻源？** 编辑 `push_news.py` 顶部的 `RSS_FEEDS` 列表。

- **不想用 AI 总结（省钱）？** 不配置 `DEEPSEEK_API_KEY` 即可，会直接推送新闻原始列表。

- **定时有点延迟？** GitHub 免费版定时任务可能延迟几分钟到十几分钟，属正常现象，不影响使用。

- **费用？** GitHub Actions 对公开/私有仓库都有免费额度（本任务每天仅几十秒，远用不完）；DeepSeek 每天总结成本约几分钱；Server酱个人版免费。
