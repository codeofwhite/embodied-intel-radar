<div align="center">

<img src="site/assets/brand.svg" width="76" height="76" alt="Embodied Compass logo">

# Embodied Compass

### Find your direction in embodied AI.

Source-linked **jobs, companies and research signals** — in one explorable map.

[Public website](https://codeofwhite.github.io/embodied-intel-radar/) · [中文介绍](README.zh-CN.md) · [How it works](docs/methodology.md) · [Contribute a source](https://github.com/codeofwhite/embodied-intel-radar/issues)

[![Publish Compass](https://github.com/codeofwhite/embodied-intel-radar/actions/workflows/pages.yml/badge.svg)](https://github.com/codeofwhite/embodied-intel-radar/actions/workflows/pages.yml)
[![Daily refresh](https://github.com/codeofwhite/embodied-intel-radar/actions/workflows/refresh-public.yml/badge.svg)](https://github.com/codeofwhite/embodied-intel-radar/actions/workflows/refresh-public.yml)
![No model API required](https://img.shields.io/badge/model_API-not_required-d4efdc?labelColor=102b32)

<img src="docs/images/overview.svg" width="100%" alt="Embodied Compass: opportunities, companies and research, with traceable sources. Interface concept illustration; not a screenshot.">

<sub>Interface concept illustration, not a live screenshot. An <strong>IPPLab</strong> project.</sub>

</div>

## A clearer view of a fast-moving field

Finding a path into embodied AI often means jumping between career pages, company
websites, release notes and social platforms. Embodied Compass brings those public
signals together, while keeping the original source and collection date visible.

Start with a role. Explore its skills. Follow the company. Read the release.
Then return to the original source before you act.

## Explore the compass

| Explore | What you can do | What the data means |
| --- | --- | --- |
| **Opportunities** | Search by role, company or skill; filter by city, specialty, role type and official source | Parsed public listings, not guaranteed openings |
| **Companies** | Browse the ecosystem and open company or career pages | A source directory, not proof of current hiring |
| **Research** | Follow source-linked open-source releases and research or industry leads | A release is not independent performance validation |
| **Social signals** | Read separately labelled search-index leads when available | Unverified leads; excluded from job counts |

The public interface supports **Chinese and English**. Source text stays in its
original language. No sign-in is needed. Personal match scores and private saved
links are excluded. The current collector focuses on China, with Shenzhen-first
career sources and some adjacent AI roles; this is not a global market census.

## Open locally in one command

Python 3 is enough to serve the included public snapshot. No frontend build or
package installation is needed for the public website.

```bash
git clone https://github.com/codeofwhite/embodied-intel-radar.git
cd embodied-intel-radar
python3 -m http.server 8080 --directory site --bind 127.0.0.1
```

Open **<http://127.0.0.1:8080>**. This reads the committed snapshot; it does not
start a collector or connect to the author's private database.

## Public data → public snapshot → public website

```text
Public career pages / company sources / release and research indexes
                              ↓
              Existing Python collectors (robots-aware, rate-limited)
                              ↓
                Field-allowlisted public JSON export
                              ↓
              GitHub Pages · search, filter, follow the source
```

GitHub Actions attempts a refresh every day at **08:00 China time (00:00 UTC)**.
The page shows actual collection dates; schedules can be delayed or disabled by
GitHub. Failed required collection or invalid exports leave the last published
snapshot intact. Optional sections retain their own timestamps if collection
fails. No paid model API is required.

For your own deployment, choose **GitHub Actions** in **Settings → Pages**, then
run **Publish Compass**. The first deployment requires this repository setting.
See the [deployment guide](docs/deployment.md) for permissions, failure behavior,
and refresh commands. The workflow checks for the hosted runner's existing
`requests` dependency and fails explicitly if it is unavailable.

## Keep the evidence attached

- **A page that loads is not necessarily an open job.** Check deadlines and the
  employer's original listing. Missing dates, old posts and extraction conflicts
  remain visible.
- **Counts describe collected samples.** Search coverage and parsers are limited.
  Social leads and company directory entries are not counted as jobs.
- **Source tiers describe provenance.** They do not certify accuracy. Automated
  extraction and heuristic analysis can be wrong.
- **A snapshot is not a trend.** The public refresh workflow does not accumulate a
  multi-day database or claim hiring growth, recruiting probability or investment value.
- **Public means public sources.** No login, CAPTCHA or access-control bypassing.
  Links and short extracted descriptions remain attributed to their sources.

[Methodology](docs/methodology.md) · [Reading guide](docs/industry-guide.md) · [Collector details](collector/README.md)

## For developers

The standalone public UI lives in `site/`. The retained React/Worker/D1 application
in `app/` is a separate **private deployment** with inbox and refresh features. Its
routes do not provide multi-user isolation; do not expose the full private service
anonymously. The public website never calls those APIs.

With the existing Python 3 + `requests` development environment:

```bash
python3 -m unittest discover -s collector/tests -v
node --check site/app.js
```

To refresh locally, follow the exact [public collection commands](docs/deployment.md#local-checks--本地检查).
Collection writes local data and makes external requests. `radar_refresh.py` also
includes optional notification/private publishing steps, so the public workflow
calls only the specific collectors it needs.

## Help improve the map

Good contributions are concrete: a public company career URL, a broken source,
a reproducible parser bug, better source labels, or an accessibility improvement.

[Open an issue](https://github.com/codeofwhite/embodied-intel-radar/issues) with the
original URL, what you expected, and what you observed. Please omit resumes,
private messages, contact details and access credentials.

## Credits and licensing

Created as an **IPPLab** project. Project branding is independent of the lab name;
IPPLab attribution appears on the website and project illustration.

Third-party code retains its notices: [third-party notices](docs/third-party-notices.md).
A repository-wide license has not yet been selected. Public visibility does not
by itself grant unrestricted redistribution rights. Third-party source content
remains subject to its original terms.
