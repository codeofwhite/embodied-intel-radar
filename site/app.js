/* Public, read-only explorer. Source strings are rendered with textContent. */
const translations = {
  en: {
    navExplore: 'Explore', navMethod: 'Our approach', heroTitle: 'Find your direction\nin embodied AI.',
    heroSub: 'A role worth exploring. A team worth following. A release worth reading. Connect the dots, with sources attached.',
    heroAction: 'Explore the compass ↗', heroSource: 'View on GitHub ↗', heroNote: 'Public sources · Traceable signals · No sign-in',
    metricJobs: 'Indexed roles', metricJobsNote: 'Parseable public-page samples', metricCompanies: 'Company directory',
    metricCompaniesNote: 'With public entry points', metricEvents: 'Research & industry', metricEventsNote: 'Original sources included',
    metricDate: 'Jobs collected', loading: 'Loading the public snapshot…', exploreTitle: 'Less noise. A little more direction.',
    tabJobs: 'Opportunities', tabCompanies: 'Companies', tabEvents: 'Research', tabSocial: 'Social signals',
    cityLabel: 'City', categoryLabel: 'Specialty', typeLabel: 'Role type', allCities: 'All cities', allCategories: 'All specialties',
    allTypes: 'All role types', officialOnly: 'Official company sources', search: 'Search roles, companies, skills…',
    loadMore: 'Show more ↓', methodTitle: 'Sources first. Clear boundaries.', methodIntro: 'An evolving map to help you make your own decisions.',
    readMethod: 'Read the methodology ↗', collectTitle: 'Start with public sources',
    collectBody: 'Career pages, company websites, open-source releases and paper indexes. Follow the original link to check the details.',
    organizeTitle: 'Turn information into leads', organizeBody: 'Explore by city, specialty and skill. Official sources, reposts and social leads are labelled separately.',
    verifyTitle: 'Verify before you act', verifyBody: 'An accessible page does not mean a role is still open. Extraction can be wrong; check the original and its deadline before applying.',
    contributeTitle: 'Found a good source? Help improve the map.', contributeBody: 'Add a career page, report a broken link or improve a collector.',
    contributeAction: 'Contribute on GitHub ↗', footerTagline: 'Find your direction in embodied AI.',
    footerNotice: 'Public-page samples, not the whole market. No hiring or investment advice. Daily refresh attempts; actual collection times are shown.',
    jobsNote: 'Collected pages are leads, not confirmed openings. Missing dates and old listings are flagged. Filtering uses source-language text; personal match scores are excluded.',
    companiesNote: 'Company profiles are a source directory, not a live hiring claim. Verify company details and openings on the original website.',
    eventsNote: 'Public releases and research leads. A publication or release is not independent evidence of performance.',
    socialNote: 'Unverified public search-index leads. These are not job records and are not included in the role count.',
    empty: 'No matching records. Try a different search or clear the filters.', missing: 'Not stated', openJob: 'View original ↗',
    openCompany: 'Company / careers ↗', details: 'Responsibilities & requirements', fetched: 'Collected', published: 'Published',
    error: 'The snapshot could not be loaded. Retry later or open the public JSON file.', stale: 'Snapshot is over 3 days old; verify sources.',
    freshness: 'Snapshot loaded · daily refresh attempts', noDate: 'Collection time unavailable', results: 'records',
    clear: 'Clear filters', unavailable: 'No collection recorded',
  },
  zh: {
    navExplore: '探索雷达', navMethod: '信息如何而来', heroTitle: '下一步，\n走向具身智能。',
    heroSub: '从一份岗位，到一家值得关注的公司，再到一次技术更新。把散落的信息，变成有来源的方向。',
    heroAction: '找到你的方向 ↗', heroSource: '查看开源项目 ↗', heroNote: '公开信息 · 来源可追溯 · 无需登录',
    metricJobs: '收录岗位', metricJobsNote: '可解析的公开样本', metricCompanies: '公司目录', metricCompaniesNote: '带有公开访问入口',
    metricEvents: '研究与行业动态', metricEventsNote: '保留原始来源', metricDate: '岗位采集时间', loading: '正在读取公开快照…',
    exploreTitle: '少一点噪声，多一点方向。', tabJobs: '岗位机会', tabCompanies: '公司地图', tabEvents: '研究动态', tabSocial: '社媒线索',
    cityLabel: '城市', categoryLabel: '方向', typeLabel: '岗位类型', allCities: '全部城市', allCategories: '全部方向', allTypes: '全部类型',
    officialOnly: '仅公司官方', search: '搜索岗位、公司、技能…', loadMore: '查看更多 ↓',
    methodTitle: '信息有出处，判断有边界。', methodIntro: '一张持续整理的地图，帮助你自己做判断。', readMethod: '阅读完整方法说明 ↗',
    collectTitle: '从公开来源出发', collectBody: '招聘页面、公司官网、开源发布与论文索引。保留原链接，便于回到一手信息。',
    organizeTitle: '把信息整理成线索', organizeBody: '按城市、岗位方向和技能查看；官方来源、转发和社媒线索分别标注。',
    verifyTitle: '把最终判断留给原文', verifyBody: '页面能访问不代表岗位仍开放。自动提取可能出错；申请前核实原文和截止时间。',
    contributeTitle: '发现了好来源？一起补全地图。', contributeBody: '欢迎补充公司招聘入口、报告失效链接，或改进采集规则。',
    contributeAction: '到 GitHub 参与 ↗', footerTagline: '找到你的具身智能方向。',
    footerNotice: '公开网页样本，不代表全市场；非录用或投资建议。每日定时尝试更新，以实际采集时间为准。',
    jobsNote: '岗位是采集线索，不保证仍开放。缺失日期、历史岗位与字段冲突均保留标记；公开版不展示个人匹配分。',
    companiesNote: '公司资料是来源目录，不代表当前正在招聘。公司信息和具体岗位请以官网为准。',
    eventsNote: '来自公开发布与研究索引。论文或版本发布不等于技术效果已经获得独立验证。',
    socialNote: '仅公开搜索索引线索，均待核实；不计入岗位数量，也不包含私人收藏。',
    empty: '没有符合条件的信息，试试其他关键词或清除筛选。', missing: '未注明', openJob: '查看原文 ↗', openCompany: '官网 / 招聘 ↗',
    details: '职责与要求', fetched: '采集于', published: '发布于', error: '公开快照暂时无法读取，请稍后重试，或直接打开 JSON 文件。',
    stale: '快照已超过 3 天，请核实原文。', freshness: '快照已加载 · 每日尝试更新', noDate: '采集时间未记录', results: '条信息', clear: '清除筛选', unavailable: '暂无采集记录',
  },
};
const $ = (id) => document.getElementById(id);
let language = 'zh';
try { language = localStorage.getItem('embodied-compass-language') === 'en' ? 'en' : 'zh'; } catch { /* Browser storage is optional. */ }
let snapshot = null;
let tab = 'jobs';
let pageSize = 12;
let failed = false;
const t = (key) => translations[language][key] || key;

function element(tag, className, value) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (value !== undefined) node.textContent = String(value);
  return node;
}
function safeURL(raw) {
  try { const value = new URL(raw); return value.protocol === 'https:' && !value.username && !value.password ? value.href : ''; }
  catch { return ''; }
}
function date(value, short = false) {
  if (!value || !Number.isFinite(Date.parse(value))) return t('noDate');
  return new Intl.DateTimeFormat(language === 'zh' ? 'zh-CN' : 'en-GB', {
    year: 'numeric', month: short ? '2-digit' : 'short', day: '2-digit', timeZone: 'Asia/Shanghai',
    ...(short ? {} : { hour: '2-digit', minute: '2-digit' }),
  }).format(new Date(value));
}
function setOptions(id, values, allKey) {
  const select = $(id);
  const selected = select.value;
  select.replaceChildren(new Option(t(allKey), ''));
  [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b, 'zh-CN')).forEach((value) => select.add(new Option(value, value)));
  if ([...select.options].some((option) => option.value === selected)) select.value = selected;
}
function filters() {
  const items = snapshot?.[tab] || [];
  setOptions('city', items.flatMap((item) => String(item.location || item.city || '').split(/\s*[/、,]\s*/)), 'allCities');
  setOptions('category', items.map((item) => item.category || item.companyType || item.eventType || item.signalType), 'allCategories');
  setOptions('job-type', items.map((item) => item.employmentType), 'allTypes');
  $('city').parentElement.hidden = !['jobs', 'companies'].includes(tab);
  $('job-type').parentElement.hidden = tab !== 'jobs';
  $('official').parentElement.hidden = tab === 'companies';
}
function filteredItems() {
  const query = $('search').value.trim().toLocaleLowerCase();
  return (snapshot?.[tab] || []).filter((item) => {
    const searchable = [item.title, item.company, item.name, item.location, item.city, item.category,
      item.focus, item.workSummary, item.whatHappened, ...(item.skills || [])].filter(Boolean).join(' ').toLocaleLowerCase();
    return (!query || searchable.includes(query))
      && (!$('city').value || String(item.location || item.city || '').includes($('city').value))
      && (!$('category').value || [item.category, item.companyType, item.eventType, item.signalType].includes($('category').value))
      && (!$('job-type').value || item.employmentType === $('job-type').value)
      && (!$('official').checked || item.sourceTier === '公司官方');
  });
}
function card(item) {
  const article = element('article', 'record');
  const head = element('div', 'record-head');
  head.append(element('span', 'record-company', item.company || item.companyType || item.project || item.domain || 'PUBLIC SOURCE'));
  const source = item.sourceTier || item.platform || item.careerKind || t('tabCompanies');
  head.append(element('span', `source${source === '公司官方' ? ' is-official' : ''}`, source));
  article.append(head, element('h3', '', item.title || item.name || t('missing')));
  const sub = [item.location || item.city, item.employmentType, item.education, item.experience].filter(Boolean);
  if (sub.length) article.append(element('p', 'record-sub', sub.join(' · ')));
  const body = item.workSummary || item.whatHappened || item.focus;
  if (body) article.append(element('p', 'record-body', body.slice(0, 280)));
  const tags = [item.category, item.eventType, item.signalType, ...(item.skills || []).slice(0, 5)].filter(Boolean);
  if (tags.length) { const group = element('div', 'tags'); tags.forEach((tag) => group.append(element('span', 'tag', tag))); article.append(group); }
  const flags = [...(item.qualityFlags || [])];
  if (item.listingStatus) flags.unshift(item.listingStatus);
  if (item.datePosted && (Date.now() - Date.parse(item.datePosted)) / 86400000 > 180 && !flags.includes('发布日期较旧')) flags.push('发布日期较旧');
  if (tab === 'social') flags.push(item.verification || '搜索索引线索·待核实');
  if (flags.length) article.append(element('p', 'quality', [...new Set(flags)].join(' · ')));
  const detailItems = [...(item.responsibilities || []), ...(item.requirements || [])];
  if (detailItems.length) {
    const details = element('details'); details.append(element('summary', '', t('details')));
    const list = element('ul'); detailItems.slice(0, 12).forEach((value) => list.append(element('li', '', value))); details.append(list); article.append(details);
  }
  const foot = element('div', 'record-foot');
  const sourceDate = item.lastSeen || item.discoveredAt || snapshot.sectionUpdatedAt[tab === 'companies' ? 'jobs' : tab];
  foot.append(element('span', '', `${t('fetched')} ${date(sourceDate, true)}${item.datePosted || item.publishedAt ? ` · ${t('published')} ${date(item.datePosted || item.publishedAt, true)}` : ''}`));
  const url = safeURL(item.url || item.careerUrl || item.officialUrl);
  if (url) { const link = element('a', '', t(tab === 'companies' ? 'openCompany' : 'openJob')); link.href = url; link.target = '_blank'; link.rel = 'noopener noreferrer'; foot.append(link); }
  article.append(foot);
  return article;
}
function render() {
  $('results').setAttribute('aria-labelledby', `tab-${tab}`);
  $('evidence-note').textContent = t(`${tab}Note`);
  if (!snapshot) {
    const message = element('p', 'empty', t(failed ? 'error' : 'loading'));
    if (failed) { const link = element('a', '', ' JSON ↗'); link.href = 'data/snapshot.json'; message.append(link); }
    $('results').replaceChildren(message);
    return;
  }
  $('count-jobs').textContent = snapshot.jobs.length;
  $('count-companies').textContent = snapshot.companies.length;
  $('count-events').textContent = snapshot.events.length;
  $('snapshot-date').textContent = date(snapshot.generatedAt, true);
  $('freshness').textContent = t(Date.now() - Date.parse(snapshot.generatedAt) > 3 * 86400000 ? 'stale' : 'freshness');
  const items = filteredItems();
  $('result-count').textContent = `${items.length} ${t('results')}`;
  const updated = snapshot.sectionUpdatedAt[tab === 'companies' ? 'jobs' : tab];
  $('section-date').textContent = updated ? `${t('fetched')} ${date(updated)} (UTC+8)` : t('unavailable');
  $('results').replaceChildren(...items.slice(0, pageSize).map(card));
  if (!items.length) {
    const empty = element('div', 'empty'); empty.append(element('p', '', t('empty')));
    const clear = element('button', 'button secondary', t('clear')); clear.type = 'button';
    clear.addEventListener('click', () => { ['search', 'city', 'category', 'job-type'].forEach((id) => { $(id).value = ''; }); $('official').checked = false; render(); });
    empty.append(clear); $('results').append(empty);
  }
  $('load-more').hidden = pageSize >= items.length;
}
function applyLanguage() {
  document.documentElement.lang = language === 'zh' ? 'zh-CN' : 'en';
  document.querySelectorAll('[data-i18n]').forEach((node) => { node.textContent = t(node.dataset.i18n); });
  $('search').placeholder = t('search'); $('search').setAttribute('aria-label', t('search'));
  ['city', 'category', 'job-type'].forEach((id, index) => $(id).setAttribute('aria-label', t(['cityLabel', 'categoryLabel', 'typeLabel'][index])));
  $('language').textContent = language === 'zh' ? 'EN' : '中文';
  $('language').setAttribute('aria-label', language === 'zh' ? 'Switch to English' : '切换到中文');
  filters(); render();
}
function changeTab(next) {
  tab = next; pageSize = 12;
  ['city', 'category', 'job-type'].forEach((id) => { $(id).value = ''; }); $('official').checked = false;
  document.querySelectorAll('[data-tab]').forEach((button) => { const active = button.dataset.tab === tab; button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1; });
  filters(); render();
}
document.querySelectorAll('[data-tab]').forEach((button) => {
  button.addEventListener('click', () => changeTab(button.dataset.tab));
  button.addEventListener('keydown', (event) => {
    const tabs = [...document.querySelectorAll('[data-tab]')]; const index = tabs.indexOf(button);
    let next = null;
    if (event.key === 'ArrowRight') next = tabs[(index + 1) % tabs.length];
    if (event.key === 'ArrowLeft') next = tabs[(index + tabs.length - 1) % tabs.length];
    if (event.key === 'Home') next = tabs[0]; if (event.key === 'End') next = tabs.at(-1);
    if (next) { event.preventDefault(); next.click(); next.focus(); }
  });
});
['search', 'city', 'category', 'job-type', 'official'].forEach((id) => $(id).addEventListener(id === 'search' ? 'input' : 'change', () => { pageSize = 12; render(); }));
$('language').addEventListener('click', () => { language = language === 'zh' ? 'en' : 'zh'; try { localStorage.setItem('embodied-compass-language', language); } catch { /* No storage required to browse. */ } applyLanguage(); });
$('load-more').addEventListener('click', () => { pageSize += 12; render(); });
applyLanguage();
fetch('data/snapshot.json', { cache: 'no-cache' }).then((response) => {
  if (!response.ok) throw new Error(`Snapshot HTTP ${response.status}`);
  return response.json();
}).then((value) => {
  if (value.schemaVersion !== 1 || !['jobs', 'companies', 'events', 'social'].every((key) => Array.isArray(value[key])) || !value.sectionUpdatedAt || !Number.isFinite(Date.parse(value.generatedAt))) throw new Error('Unsupported snapshot');
  snapshot = value; filters(); render();
}).catch((error) => { console.error('Public snapshot load failed:', error); failed = true; render(); });
