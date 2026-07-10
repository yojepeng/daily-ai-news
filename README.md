# 每日科技（GitHub Actions 版）

关机也能跑：由 GitHub 的服务器在**每天北京时间 06:30** 自动执行，分 4 个板块抓取科技资讯 → 各板块用 DeepSeek 总结成详细报道 → Server酱推送到你的微信（可选附**语音播报**链接）。你的电脑无需开机。

推送内容分 4 个板块（共 28 条）：
- **一、Vibe Coding**（6 条）
- **二、OPC 一人公司**（6 条，政策 / 热点 / 新闻）
- **三、AI**（8 条，应用 + 动向 + 模型发布）
- **四、科技新闻**（8 条）

**去重机制**：板块间 / 数据源间按标题归一化全局去重；已推送过的标题记入 `history.json`，之后 **7 天（一周）** 内不再重复推送。某板块当天不足目标条数时，按实际条数推送。

**语音播报**：默认开启。用免费的 edge-tts（微软在线语音，无需密钥）把新闻合成 mp3，经 GitHub Pages 生成公开链接，随推送一并发送「🎧 语音播报」入口，点开即可听。详见下方「语音播报配置」。

## 目录结构

```
daily-ai-news/
├── push_news.py                    # 核心脚本：抓取 + 总结 + 推送 + 语音合成
├── requirements.txt                # Python 依赖（含 edge-tts）
├── .github/workflows/daily-news.yml# 定时工作流（每天 06:30 北京时间）
├── history.json                    # 跨天去重历史（自动生成/更新，勿手改）
├── audio/                          # 每日语音 mp3（自动生成，自动清理旧文件）
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
3. 左侧选 `Daily Tech News` → 右侧 `Run workflow` → 绿色 `Run workflow`
4. 约 1-2 分钟后点进运行记录看日志；若显示 `全部完成 ✅`，微信「方糖」公众号就会收到今日「每日科技」

### 第 5 步：完成

测试通过后就不用管了，之后**每天早上 06:30 自动推送**。

---

### 语音播报（当前已关闭）

语音播报功能（edge-tts 合成 mp3 + 托管）**当前默认关闭**（`ENABLE_TTS=false`），文字推送完全不受影响。

若未来想重新开启，需要：
1. 准备一个**可用的音频托管服务**（如腾讯云 COS / 阿里云 OSS / Cloudflare R2 等，需确保域名在微信内可访问）
2. 修改 `push_news.py` 的 `upload_to_storage` 函数适配对应存储
3. 工作流 `ENABLE_TTS` 改为 `'true'`，并添加对应的存储密钥到 GitHub Secrets

> ⚠️ **历史经验**：GitHub Pages（`github.io` 域名）会被微信拦截，不适合作为微信推送的音频托管方案。

---

## 常见问题

- **没收到推送？**
  1. 看 Actions 日志里 `Server酱 推送响应` 是否 `200` 且 `"code":0`
  2. 确认已关注「方糖」公众号
  3. 确认 `SERVERCHAN_SENDKEY` 没写错、没多空格

- **想改时间？** 编辑 `.github/workflows/daily-news.yml` 里的 `cron`。
  注意是 **UTC 时间**，北京时间要减 8 小时。例如：
  - 北京 06:30 → `30 22 * * *`（当前设置）
  - 北京 08:00 → `0 0 * * *`
  - 北京 09:00 → `0 1 * * *`
  - 北京 20:00 → `0 12 * * *`

- **想换/加新闻源或板块？** 编辑 `push_news.py` 顶部的 `TOPICS` 列表（每个板块的 `section` 名称、`feeds` 搜索词、`n` 控制该板块条数；`hours_back` 可单独设置该板块的时间窗，单位小时）。跨天去重的保留天数由环境变量 `HISTORY_DAYS`（默认 7 天，即一周）控制。

- **不想用 AI 总结（省钱）？** 不配置 `DEEPSEEK_API_KEY` 即可，会直接推送新闻原始列表。

- **语音播报没声音 / 链接打不开？** 多半是还没开启 GitHub Pages（见上方「开启语音播报」）。开启后次日链接即可用；当天那次链接会 404，不影响文字内容。文字推送与语音相互独立，任一失败都不影响另一项。

- **语音音色/语种？** 默认 `zh-CN-XiaoxiaoNeural`（中文女声）。可在工作流设置 `TTS_VOICE` 环境变量换声线；edge-tts 支持多语种，新闻含英文也可正常朗读。

- **定时有点延迟？** GitHub 免费版定时任务可能延迟几分钟到十几分钟，属正常现象，不影响使用。

- **费用？** GitHub Actions 对公开/私有仓库都有免费额度（本任务每天仅几十秒，远用不完）；DeepSeek 每天总结成本约几分钱；Server酱个人版免费。

---

## 更新记录

### 2026-07-10（本次修改）

对原「每日 AI 新闻推送」做了以下 4 项调整：

1. **推送时间调整**：由每天北京时间 08:00 改为 **06:30**。
   - 对应 `daily-news.yml` 的 cron 由 `0 0 * * *` 改为 `30 22 * * *`（GitHub 用 UTC，北京 06:30 = UTC 22:30）。
2. **内容改为 4 个板块，每板块 8 条**：
   - 一、科技新闻
   - 二、Vibe Coding
   - 三、AI 应用
   - 四、AI 动向
   - 实现：脚本新增 `TOPICS` 配置，每个板块用 Google News 中/英搜索 RSS 聚合（科技新闻板块额外接入机器之心、The Verge），每板块各取 8 条后分别调用 DeepSeek 总结。
3. **新闻内容更详细**：DeepSeek 提示词改为每条 **2-4 句话**，要求写明"发生了什么、涉及哪些公司/人物/数据、为什么重要"，并按板块分别生成详细 Markdown 报道。
4. **推送标题改为「每日科技」**：由原来「每日 AI 要闻」改为「每日科技 {日期}」，工作流名称也由 `Daily AI News` 改为 `Daily Tech News`。

> 相关参数：每板块条数由 `TOPICS` 中各板块的 `n` 控制；新闻时间窗口由 `HOURS_BACK`（默认 48 小时）控制；跨天去重保留天数由 `HISTORY_DAYS`（默认 3 天）控制。

---

### 2026-07-10（第二次修改）

对上一版做了 3 项进一步调整：

1. **板块间 / 历史中去重**：新增标题归一化（忽略大小写、空白、标点）+ 全局去重，确保同一新闻不会同时出现在多个板块；并引入 `history.json` 持久化历史，已推送过的标题在 `HISTORY_DAYS`（默认 3 天）内不再重复推送（工作流新增写回 `history.json` 的步骤与 `contents: write` 权限）。
2. **不足目标条数按实际推送**：某板块当天抓不到满额（如不足 8 条），按实际条数生成，不再强行凑数。
3. **第三、四板块合并**：原「AI 应用」与「AI 动向」合并为 **「三、AI 应用与动向」**，共推送 **10 条**。最终结构：科技新闻(8) + Vibe Coding(8) + AI 应用与动向(10) = 26 条。

---

### 2026-07-10（第三次修改）

对上一版做了 4 项调整：

1. **新增「OPC 一人公司」板块**：聚焦一人公司 / 独立开发者 / 个体创业 / 数字游民的政策、热点、新闻（中英文 Google News 聚合，时间窗放宽到 7 天以匹配其较低更新频率）。
2. **重新排序并调整条数**：
   - 一、Vibe Coding（6 条）
   - 二、OPC 一人公司（6 条）
   - 三、AI（8 条，由「AI 应用与动向」拆回单一 AI 板块）
   - 四、科技新闻（8 条）
   - 总计 **28 条**。
3. **跨天去重窗口改为一周**：`HISTORY_DAYS` 默认由 3 天改为 **7 天**，已推送标题一周内不再重复。
4. **新增语音播报**：用免费 edge-tts 将新闻合成 mp3，经 GitHub Pages 生成公开链接随推送发送「🎧 语音播报」入口（需一次性开启 Pages，详见 README「开启语音播报」）。语音合成与文字推送相互独立，任一方失败都不影响另一方；旧音频按 7 天自动清理。

> 相关参数：每板块条数由各板块 `n` 控制；OPC 板块时间窗由 `hours_back`（168 小时）控制；跨天去重天数 `HISTORY_DAYS`（默认 7）；语音开关 `ENABLE_TTS`、音色 `TTS_VOICE`。
