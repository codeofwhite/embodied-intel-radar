# 具身智能行业与求职情报雷达

面向具身智能求职者的公开信息采集与分析工具：从公开招聘页面提取岗位、来源和能力要求，以可解释规则整理公司、研究事件与求职线索。

## 功能

- 招聘采集：保留原始链接、来源等级、采集时间和解析限制。
- 岗位分析：职责、能力分组、入门门槛依据，以及基于岗位文本生成的模拟面试问题。
- 行业观察：公司目录、公开事件和社媒搜索入口；社媒线索始终待核实。
- 私有部署功能：个人链接收件箱、刷新队列、上传和可选飞书通知。

公开版默认深圳示例，技能列表为 Python / Linux / SQL，不代表作者履历；公司名称优先加分默认关闭。其余排序规则是示例启发式，不是录用概率。

## 开始使用

Python 3 + requests；前端要求 Node >=22.13.0，依赖版本见 package-lock.json。

```bash
python3 -m unittest discover -s collector/tests -v
python3 collector/jobscan.py collect --dry-run
```

需要实际采集时，阅读 [采集器说明](collector/README.md)。该流程写入本地数据库并访问公开网站。前端新环境需自行安装依赖：

```bash
npm ci
cp .openai/hosting.example.json .openai/hosting.json
npm run lint
npm run build
npm run dev
```

hosting.json 的 project_id 必须替换为自己的部署标识；模板不连接作者站点。本地开发使用演示身份，不能当作生产认证。完整界面读取 Worker + D1 API，需要在自己的环境配置 DB 绑定并应用 drizzle/ 中现有迁移。不要为启动项目重新生成迁移。

**源码公开不等于服务适合匿名公开。** 收件箱读取、写入、删除及刷新接口没有独立的用户隔离，依赖私有站点入口的访问控制。请保持完整服务私有；匿名网站需先设计认证、授权和数据隔离。公开代码不包含作者的部署、数据库或个人链接。

## 示例与分析方法

- [岗位字段示例](examples/demo-job.json)：人工构造，不是真实招聘，也非完整 UI 演示快照。
- [配置模板](examples/config/)：真实凭证存入被忽略的 collector/secrets/，不要提交。
- [统计与证据边界](docs/methodology.md)
- [行业与求职阅读指南](docs/industry-guide.md)
- [第三方声明](docs/third-party-notices.md)

## 数据边界

只访问公开页面，不绕过登录、验证码或反爬。岗位数量是可解析样本，不代表全市场；至少两个不同日期的快照才能分析变化。模拟面试问题不是公司真实题目。仓库中的来源目录与 market_evidence.csv 是历史材料，未经本次联网复核，不应作为当前岗位开放或行业增长的依据。

## 发布状态

这是从私有项目整理的公开版，不携带私有项目的 Git 历史。Python 60 项测试、前端 lint 和生产构建均通过。许可证尚待确认，已有第三方许可声明保留。验证结果见 docs/verification.md。
