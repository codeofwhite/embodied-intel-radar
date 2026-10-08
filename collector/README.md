# Radar collector

这是行业雷达的招聘采集层。公开版不包含个人历史数据库。
默认技能与优先级是演示设置，请按自己的目标修改 collector/config.json。

## 数据边界

- 只请求公开页面，遵守 `robots.txt`，不绕过登录、验证码或反爬。
- SQLite 与原始 JSONL 是证据源；`collector/data/jobs.json` 是可重建的线上快照导出。
- 公司官网标记为“公司官方”；招聘平台和高校转发页保留原链接并降低来源等级。
- `company_registry.json` 统一维护整机公司、科技大厂和国内机器人产业链公司的官网、招聘入口、上市状态与行情映射。
- 官网列表适配器会拆分宇树科技和大疆的单个岗位；动态页面若无法稳定解析，仍会写入 `career_links.json` 供网页直接打开。
- 网站导出会从岗位原文提炼职责、要求、能力分组和有依据的模拟面试问题。模拟题不是公司真实面试原题。
- 单次成功解析仅表示本次能够获取，不等于岗位仍开放。
- 至少两个不同日期的快照后才允许展示新增、下架或招聘扩张趋势。

## 命令

```bash
python3 -m unittest discover -s collector/tests -v
python3 collector/jobscan.py collect --dry-run
python3 collector/jobscan.py collect
python3 collector/jobscan.py report
python3 collector/jobscan.py export-site
```

## 飞书推送

飞书自定义机器人 Webhook 是私密凭证。项目不会复用
其他工具的凭证文件，也不会把地址写入版本控制。私密地址存放在
collector/secrets/feishu.json，格式如下：

~~~json
{
  "webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/替换为本地真实地址"
}
~~~

机器人安全设置使用自定义关键词“具身雷达”。也可以不创建文件，改用环境变量
FEISHU_RADAR_WEBHOOK_URL。先预览卡片，再实际发送：

~~~bash
python3 collector/feishu_notify.py --dry-run
python3 collector/feishu_notify.py
~~~

默认只发送每个快照一次，并在 collector/data/feishu_notify_state.json
记录最后成功发送的快照。需要重复测试时显式添加 --force。如果数据库已有两个快照，
卡片只突出相对上一次快照新增的岗位；首次快照则标记为“本次收录”，不声称招聘趋势。

## 持续刷新与行业线索

统一刷新命令会依次更新招聘快照、网站招聘 JSON、公司/研究事件、
X / 小红书搜索线索，并在有新招聘快照时调用飞书通知：

~~~bash
python3 collector/radar_refresh.py --dry-run
python3 collector/radar_refresh.py
~~~

事件结果保存到 collector/data/events.json，社媒线索保存到
collector/data/social.json，步骤状态保存到 collector/data/refresh_status.json。
这些运行产物默认不进入 Git。X / 小红书线索只来自公开搜索索引，不请求登录后正文，
不绕过登录、验证码或 robots.txt。搜索结果必须同时包含就业意图与具身/机器人方向
信号才会进入快照；未通过过滤时，网页仍提供直达平台搜索入口和私有链接收件箱。
X 官方 API 默认关闭，项目不依赖付费 API。飞书卡片只附加招人、面试、岗位能力、
薪酬强度或团队变化这几类高价值线索，并明确标为待核实。

每六小时运行的 systemd 用户单元保存在 collector/systemd/。启用后可检查：

~~~bash
systemctl --user status embodied-radar.timer
journalctl --user -u embodied-radar.service
~~~

线上网站使用 Worker + D1 保存最新快照。网页“立即刷新”会创建排队任务，本机轮询器
接单后运行完整采集流程，并把招聘、事件、社媒线索、行情与步骤状态签名上传。它不是
浏览器内的假刷新。

行情使用 Alpha Vantage 的真实日线收盘数据，不是盘中实时行情。观察池优先覆盖
国内具身整机、工业机器人、执行器、传感器与运动控制公司；按标的做当日缓存并设置
25 次请求保护，避免刷新按钮重复消耗免费配额。港股公司仍保留在公司库中，但在当前
数据源不稳定支持港股代码时不伪造或展示价格。API Key 存在
collector/secrets/market.json：

~~~json
{"api_key": "你的 Alpha Vantage API Key"}
~~~

线上同步配置存在 collector/secrets/online.json，包含私有站点 URL、上传密钥和
Sites 访问令牌，全部被 Git 忽略。常用命令：

~~~bash
python3 collector/market_scan.py --dry-run
python3 collector/market_scan.py
python3 collector/publish_online.py
python3 collector/online_poll.py
~~~

每六小时自动采集仍由 embodied-radar.timer 执行；网页刷新队列由
embodied-radar-online-poll.timer 每两分钟检查一次。两者都只处理公开数据源，
X / 小红书仍仅保存公开搜索索引线索；用户手动保存的链接单独存放在站点 D1 中，
不会混入本地招聘数据库或岗位计数。

迁移首版可显式读取旧数据库：

```bash
python3 collector/jobscan.py --db /path/to/previous/jobs.sqlite export-site
```

## 公开版运行说明

依赖 Python 3 和 requests。默认配置为深圳招聘示例；技能列表不是作者履历。
运行采集、刷新及通知命令会写入本地数据，可能访问网络或发送通知；首次使用请先阅读命令说明。
systemd 示例假定仓库位于 ~/embodied-intel-radar-public，其他目录请修改 WorkingDirectory 和 ExecStart。本仓库不会自动启用定时器。
配置模板位于 examples/config/，真实值只能放在被忽略的 collector/secrets/ 下。
