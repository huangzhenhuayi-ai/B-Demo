# B站选题关键词热度排查工具

这是一个本地运行的 MVP 工具：输入一个或多个关键词，自动采集 B站公开视频搜索结果，并输出两份 CSV：

- `bilibili_videos_*.csv`：逐条视频明细
- `bilibili_keyword_summary_*.csv`：每个关键词的热度评分和执行建议

可视化界面由 `bilibili_keyword_app.py` 启动，页面文件在 `web/` 目录；命令行采集脚本是 `bilibili_keyword_probe.py`。

工具只读取公开可访问的视频搜索和视频统计数据，不处理登录、验证码或绕风控场景。建议小批量、低频率使用。

## 采集的数据

明细表会尽量记录这些字段：

| 字段 | 含义 |
|---|---|
| keyword | 搜索关键词 |
| rank | 搜索结果排名 |
| bvid / aid | 视频 ID |
| title | 视频标题 |
| url | 视频链接 |
| author | UP 主 |
| category | 分区 |
| publish_date | 发布时间 |
| age_days | 距今多少天 |
| duration_seconds | 视频时长 |
| views | 播放量 |
| danmaku | 弹幕数 |
| comments | 评论数 |
| likes | 点赞数 |
| coins | 投币数 |
| favorites | 收藏数 |
| shares | 分享数 |
| description / tags | 简介和标签 |

汇总表会输出：

| 字段 | 含义 |
|---|---|
| demand_score | 需求分，主要看播放和互动中位数 |
| growth_score | 增长分，主要看 30 天 / 90 天内新增内容比例 |
| competition_score | 竞争分，主要看头部集中度和高播放视频比例 |
| opportunity_score | 机会分，综合需求、增长、结果深度和竞争 |
| recommendation | `可执行`、`小样本测试` 或 `暂不建议` |
| reason | 简短原因 |

## 快速开始

已经安装好本地 Python 后，可以直接运行：

```powershell
python .\bilibili_keyword_app.py
```

浏览器打开：

```text
http://127.0.0.1:8765
```

命令行模式仍然可用：

```powershell
python .\bilibili_keyword_probe.py --keyword "AI副业" --pages 1
```

如果当前终端还没刷新 PATH，可以先关闭 PowerShell 再重新打开；或者临时使用完整路径：

```powershell
& "C:\Users\HUANG ZHEN\AppData\Local\Programs\Python\Python313\python.exe" .\bilibili_keyword_probe.py --keyword "AI副业" --pages 1
```

运行完成后，到 `outputs` 目录查看 CSV 文件。CSV 使用 `utf-8-sig` 编码，通常可以直接用 Excel 打开且不乱码。

## 多关键词采集

方式一：逗号分隔。

```powershell
python .\bilibili_keyword_probe.py --keyword "AI副业,普通人副业,AI工具赚钱" --pages 1
```

方式二：使用文件。可以复制并修改 `keywords.example.txt`。

```powershell
python .\bilibili_keyword_probe.py --keywords-file .\keywords.example.txt --pages 1
```

## 常用参数

```text
--keyword / -k          单个关键词，可重复传入，也可用逗号分隔
--keywords-file / -f    关键词文件，每行一个关键词
--pages / -p            每个关键词采集页数，默认 1
--max-results           每个关键词最多保留多少条结果，适合小样本测试
--order                 搜索排序，默认 totalrank
--output-dir / -o       输出目录，默认 outputs
--sleep                 请求间隔秒数，默认 0.8
--no-enrich             只采集搜索页数据，不逐条补全点赞/投币/分享等统计
```

B站搜索排序可选：

| 值 | 含义 |
|---|---|
| totalrank | 综合排序 |
| click | 最多播放 |
| pubdate | 最新发布 |
| dm | 最多弹幕 |
| stow | 最多收藏 |

## 评分口径

第一版评分是启发式模型，用来快速排查选题，不代表平台官方热度：

```text
demand_score = 播放中位数 + 互动中位数 + 结果数量
growth_score = 近 30/90 天内容占比 + 常青内容补偿
competition_score = 头部视频播放集中度 + 高播放视频比例 + P75 播放门槛
opportunity_score = 需求 + 增长 + 结果深度 - 竞争
```

建议看法：

| opportunity_score | 建议 |
|---|---|
| 75-100 | 可执行 |
| 55-74 | 小样本测试 |
| 0-54 | 暂不建议 |

## 注意事项

- 建议每次先从 1-3 个关键词、每个关键词 1 页开始。
- 如果出现请求失败、风控或网络错误，先降低频率，例如 `--sleep 2`。
- 不建议高频批量采集，也不要绕过登录、验证码或访问限制。
- 小红书版本建议后续做成浏览器辅助采集，避免不稳定和合规风险。

## 故障处理

如果脚本提示 `handshake operation timed out` 或 `operation has timed out`，通常是当前网络访问 B站不稳定。可以先在浏览器打开：

```text
https://www.bilibili.com
```

如果浏览器也打不开，换一个能正常访问 B站的网络后再运行。如果浏览器能打开但脚本失败，可以尝试：

```powershell
python .\bilibili_keyword_probe.py --keyword "AI副业" --pages 1 --max-results 5 --sleep 2
```
