# Hosting Embodied Compass / 部署具身罗盘

## Public website / 公开网站

The public application is the buildless `site/` directory. It reads only
`site/data/snapshot.json`. It does not call the private Worker, use D1, read the
personal inbox, accept uploads or trigger collection from a visitor's browser.
It requires neither a running laptop nor a paid model API.

公开页面只读取脱敏 JSON；岗位收藏、备注、个人评分与私有服务访问凭证不会发布。
公开版与原有 `app/` 完整服务分开运行。行情不在公开版首期范围内。

1. In **Settings → Pages → Build and deployment → Source**, select **GitHub Actions**.
2. In **Actions**, open **Publish Compass** and run it on `main`.
3. Wait for the `github-pages` deployment to succeed. Use the URL returned by
   the deployment; for this repository the expected URL is
   <https://codeofwhite.github.io/embodied-intel-radar/>.

首次启用需要仓库管理员操作；普通 `GITHUB_TOKEN` 不能自动创建 Pages 设置。
网站发布完成以后不需要保留本地预览进程。GitHub 服务、访问网络和配额仍可能影响可用性，
“长期托管”不代表承诺任何地区、任何时刻均可访问。

For forks, replace the hard-coded repository, contribution and metadata links
in `site/index.html` and both READMEs with your own. Asset and data URLs are
relative, so deployment under a repository subpath works without a frontend build.

## Daily refresh / 每日更新

`refresh-public.yml` attempts collection at 00:00 UTC (08:00 Asia/Shanghai).
GitHub schedules may be delayed. Public repositories can have inactive scheduled
workflows disabled by GitHub; check **Actions** if data becomes stale.

The workflow checks for the runner's existing Python `requests` package. It does
not install packages, call model APIs, read secrets, send notifications, or upload
to the private service. If a runner image removes `requests`, the dependency check
fails visibly; an environment change is then needed before collection can resume.

Jobs are collected with the existing low-rate, robots-aware collector (20-minute
limit). Research and social sections each have a five-minute limit. The exporter
uses field allowlists and removes personal scoring and private URL credentials.
Only `site/data/snapshot.json` is committed; databases, raw pages and logs remain
ignored. A `workflow_run` trigger then publishes the committed snapshot, because
commits made with `GITHUB_TOKEN` do not themselves trigger another push workflow.

招聘采集或导出失败时，工作流失败，原站点和上次成功 JSON 保留。事件或社媒步骤失败时，
保留上次公开的对应部分和原采集时间。成功采集但没有合格线索时显示空列表。
公司信息来自现有来源目录，不代表每次采集都复核了全部公司资料。
没有累积多日数据库；公开网站不声称招聘增减或市场趋势。

The refresh workflow needs **Contents: write**, and the publish workflow needs
**Pages: write** and **ID token: write**. Repository or organization policies,
branch protection, and environment approval rules may require administrator action.
Never work around these by embedding a personal token in source code.

## Local checks / 本地检查

From the repository root, with the existing Python 3 + requests environment:

```bash
python3 -m unittest discover -s collector/tests -v
node --check site/app.js
python3 -m http.server 8080 --directory site --bind 127.0.0.1
```

Open <http://127.0.0.1:8080>. The public website needs no Node installation or
framework build to serve; Node above is only a JavaScript syntax check.

To collect and replace the public snapshot locally (network access and filesystem writes):

```bash
timeout 1200s python3 collector/jobscan.py collect
python3 collector/jobscan.py export-site
timeout 300s python3 collector/intel_scan.py events
timeout 300s python3 collector/intel_scan.py social
python3 scripts/export-public-snapshot.py
```

Do not use `radar_refresh.py` for the public workflow: it also runs optional
notification and private publication steps. Existing public collector behavior,
parsing limits and source health remain relevant; inspect the logs and verify the
original listing before making a hiring claim.

## Repository presentation / 仓库展示

Suggested About description:

> Find your direction in embodied AI. Source-linked jobs, companies & research signals. 具身罗盘 · An IPPLab project.

Website: the successful Pages deployment URL above.

Topics: `embodied-ai`, `robotics`, `job-search`, `research-tools`, `open-source`,
`github-pages`, `career`, `data-collection`.

GitHub's **Settings → General → Social preview** accepts a raster preview image.
`docs/images/overview.svg` is an editable README illustration, not a screenshot or
a platform social-preview upload. The project has no new repository-wide license;
retain the third-party notices and confirm licensing before redistribution.

## Private full service / 私有完整服务

The retained React application under `app/` uses Worker + D1 APIs. Its inbox and
refresh routes rely on a private entry point, and do not isolate multiple users.
Keep it private. A public frontend does not make those routes safe for anonymous use.
The public website does not change or deploy the existing private Site.
