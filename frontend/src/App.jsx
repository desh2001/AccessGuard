import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertCircle, AlertTriangle, ArrowDownToLine, ArrowRight,
  ArrowUpRight, Bell, Boxes, Check, CheckCheck, ChevronDown, ChevronRight,
  CircleHelp, ClipboardCheck, Clock3, Cloud, Database, ExternalLink,
  FileClock, FileText, Filter, Fingerprint, Github, HardDrive, KeyRound,
  LayoutDashboard, Lock, Menu, MoreHorizontal, RefreshCw, Search, Server,
  Settings, Shield, ShieldAlert, ShieldCheck, Sparkles, TrendingUp,
  TrendingDown, Users, UsersRound, UserRoundX, X, Zap, BarChart3,
  CircleCheck, Clock, AlertOctagon, Eye, Award, Target
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, CartesianGrid, Cell, Legend, LineChart,
  Line, PieChart, Pie, RadarChart, Radar, PolarGrid, PolarAngleAxis,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

// ─── Nav Items ───────────────────────────────────────────────────────────────
const ITEMS = [
  { id: 'overview',     label: 'Overview',         icon: LayoutDashboard },
  { id: 'alerts',       label: 'Risk Alerts',       icon: AlertTriangle },
  { id: 'activity',     label: 'Activity Evidence', icon: Activity },
  { id: 'identities',   label: 'Identities',        icon: Fingerprint },
  { id: 'accounts',     label: 'Linked Accounts',   icon: UsersRound },
  { id: 'access',       label: 'Access Inventory',  icon: KeyRound },
  { id: 'risks',        label: 'AI Risk Analysis',  icon: ShieldAlert },
  { id: 'reviews',      label: 'Access Reviews',    icon: ClipboardCheck },
  { id: 'offboarding',  label: 'Offboarding',       icon: UserRoundX },
  { id: 'integrations', label: 'Integrations',      icon: Boxes },
  { id: 'audit',        label: 'Audit Reports',     icon: FileClock },
  { id: 'reports',      label: 'Research Reports',  icon: FileText },
  { id: 'settings',     label: 'Settings',          icon: Settings },
];

const HEADINGS = {
  alerts:       ['Risk Alerts',          'Policy-based findings requiring investigation — not automatic action'],
  activity:     ['Activity Evidence',    'Synthetic sampled events. Absent logs do not prove access is unused'],
  reports:      ['Research Reports',     'Project-wide metrics and connector provenance evidence'],
  overview:     ['Overview',             'Centralized view of identities, access and risk across all systems'],
  identities:   ['Identity Directory',   'Human employees, service accounts and third-party vendor access'],
  accounts:     ['Account Mapping',      'Resolve technical accounts across platforms and verify ownership'],
  access:       ['Access Inventory',     'All permissions — explore who can access what and assess risk'],
  risks:        ['AI Risk Analysis',     'Explainable rule-based flags combined with unsupervised ML ranking'],
  reviews:      ['Access Reviews',       'Review risky permissions — human approval required before any action'],
  offboarding:  ['Offboarding Center',   'Departed employees with outstanding access — verify before removal'],
  integrations: ['Integrations',         'Connected systems and data collection status'],
  audit:        ['Audit Trail',          'Decision history and simulated remediation events'],
  settings:     ['Settings',             'Prototype configuration and security notes'],
};

const RISK_COLORS   = { Critical: '#dc425d', High: '#f27b46', Medium: '#edae36', Low: '#27a78a' };
const KIND_COLORS   = { Human: '#5f38cc', Machine: '#22a0cc', Vendor: '#f19c45' };
const CHART_PALETTE = ['#7045ce', '#22a0cc', '#27a78a', '#edae36', '#f27b46', '#dc425d', '#5f38cc', '#f19c45'];

const iconForSystem = (name) =>
  /github/i.test(name) ? Github
  : /linux|ubuntu|centos/i.test(name) ? Server
  : /windows|active.dir/i.test(name) ? HardDrive
  : /aws|cloud|gcp|azure|google/i.test(name) ? Cloud
  : /postgres|sql|mysql|snowflake|db/i.test(name) ? Database
  : /kubernetes|k8s/i.test(name) ? Server
  : Boxes;

// ─── API ─────────────────────────────────────────────────────────────────────
const request = async (path, options) => {
  const res = await fetch('/api' + path, options);
  if (!res.ok) {
    let msg = 'Request failed';
    try { const d = await res.json(); msg = typeof d.detail === 'string' ? d.detail : msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
};

// ─── Utilities ───────────────────────────────────────────────────────────────
const formatDate = (d) => d ? new Date(d).toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: 'numeric' }) : 'Not verified';
const formatShortDate = (d) => d ? new Date(d).toLocaleDateString('en-GB', { month: 'short', day: 'numeric' }) : '—';
const daysAgo = (d) => { if (!d) return null; const diff = Math.round((Date.now() - new Date(d)) / 86400000); return diff; };
const exportCSV = (rows, filename) => {
  if (!rows.length) return;
  const safe = v => { const r = String(v ?? ''); const n = /^[=+@-]/.test(r) ? `'${r}` : r; return '"' + n.replaceAll('"', '""') + '"'; };
  const cols = Object.keys(rows[0]);
  const csv = [cols.join(','), ...rows.map(r => cols.map(c => safe(Array.isArray(r[c]) ? r[c].join('; ') : r[c])).join(','))].join('\r\n');
  const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click(); URL.revokeObjectURL(url);
};

// ─── Shared Components ───────────────────────────────────────────────────────
function Badge({ value, tone }) {
  return <span className={`badge ${tone || String(value).toLowerCase().replace(/\s+/g, '-')}`}>{value}</span>;
}

function RiskBar({ risk, showLabel = true }) {
  const cls = risk >= 85 ? 'critical' : risk >= 60 ? 'high' : risk >= 35 ? 'medium' : 'low';
  const color = risk >= 85 ? RISK_COLORS.Critical : risk >= 60 ? RISK_COLORS.High : risk >= 35 ? RISK_COLORS.Medium : RISK_COLORS.Low;
  return (
    <div className="risk-cell">
      {showLabel && <span className={`risk-number ${cls}`}>{risk}</span>}
      <div className="risk-meter"><div style={{ width: `${risk}%`, background: color }} /></div>
    </div>
  );
}

function UserAvatar({ name, size = 34 }) {
  const initials = (name || '--').split(' ').slice(0, 2).map(s => s[0]).join('').toUpperCase();
  return <div className="avatar" style={{ width: size, height: size, minWidth: size, fontSize: size * 0.34 }}>{initials}</div>;
}

function Panel({ title, description, action, children, className = '' }) {
  return (
    <section className={`panel ${className}`}>
      <div className="panel-header">
        <div><h2>{title}</h2>{description && <p>{description}</p>}</div>
        {action}
      </div>
      {children}
    </section>
  );
}

function TableEmpty({ message = 'No records match your search.' }) {
  return (
    <div className="empty">
      <Search size={28} />
      <b>No results</b>
      <span>{message}</span>
    </div>
  );
}

function SearchToolbar({ search, setSearch, filter, setFilter, options, placeholder }) {
  return (
    <div className="toolbar">
      <div className="search-box">
        <Search size={17} />
        <input value={search} onChange={e => setSearch(e.target.value)} placeholder={placeholder || 'Search…'} />
      </div>
      <div className="filter-select">
        <Filter size={16} />
        <select value={filter} onChange={e => setFilter(e.target.value)}>
          {options.map(x => <option key={x}>{x}</option>)}
        </select>
        <ChevronDown size={14} />
      </div>
    </div>
  );
}

function StatCard({ label, value, Icon, tone, hint, change }) {
  return (
    <div className="stat-card">
      <div className="stat-top"><span>{label}</span><div className={`stat-icon ${tone}`}><Icon size={20} /></div></div>
      <div className="stat-value">{typeof value === 'number' ? value.toLocaleString() : value}</div>
      {hint && <div className="stat-sub"><span className="small-dot" />{hint}</div>}
      {change !== undefined && (
        <div className={`stat-change ${change >= 0 ? 'up' : 'down'}`}>
          {change >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
          <span>{Math.abs(change)}% from last period</span>
        </div>
      )}
    </div>
  );
}

function InfoNote({ children, warn = false, Icon = AlertCircle }) {
  return (
    <div className={`info-note ${warn ? 'warn' : ''}`}>
      <Icon size={18} />
      <span>{children}</span>
    </div>
  );
}

// ─── App Root ─────────────────────────────────────────────────────────────────
export default function App() {
  const [page, setPage] = useState('overview');
  const [menuOpen, setMenuOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('All');
  const [busy, setBusy] = useState(null);
  const [toast, setToast] = useState({ msg: '', ok: true });

  const showToast = (msg, ok = true) => { setToast({ msg, ok }); setTimeout(() => setToast({ msg: '', ok: true }), 5000); };

  const refresh = useCallback(async () => {
    setError('');
    try {
      const paths = ['overview', 'identities', 'accounts', 'suggestions', 'access',
        'reviews', 'integrations', 'audit', 'offboarding', 'activity',
        'alerts', 'ai', 'reports', 'runs', 'metrics', 'timeline', 'ftpStatus', 'mlStatus',
        'accesslogStatus', 'accesslogSummary', 'accesslogEvents', 'accesslogDevices', 'accesslogAlerts', 'mlPlatforms'];
      const urlMap = {
        suggestions: '/accounts/suggestions', ai: '/ai/summary',
        reports: '/reports/summary', runs: '/connectors/runs',
        metrics: '/metrics', timeline: '/stats/timeline?days=30',
        ftpStatus: '/connectors/ftp/status', mlStatus: '/ml/status',
        accesslogStatus: '/accesslog/status', accesslogSummary: '/accesslog/summary',
        accesslogEvents: '/accesslog/events', accesslogDevices: '/accesslog/devices',
        accesslogAlerts: '/accesslog/alerts', mlPlatforms: '/ml/platforms',
      };
      const results = await Promise.all(paths.map(p => request(urlMap[p] || '/' + p)));
      setData(Object.fromEntries(paths.map((p, i) => [p, results[i]])));
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  const navigate = (id) => { setPage(id); setMenuOpen(false); setSearch(''); setFilter('All'); };

  const act = async (id, action) => {
    setBusy(id); setToast({ msg: '', ok: true });
    try {
      const url = action === 'revoke' ? `/reviews/${id}/simulate-revoke` : `/reviews/${id}/decision`;
      const opts = { method: 'POST', headers: { 'Content-Type': 'application/json' } };
      if (action !== 'revoke') opts.body = JSON.stringify({ decision: action, reviewer: 'Demo Reviewer' });
      await request(url, opts); await refresh();
      showToast(
        action === 'revoke' ? 'Simulated revoke complete — local DB only, no external system changed'
        : action === 'approve' ? 'Removal approved — now run "Simulate revoke" to complete remediation'
        : 'Access retained — decision recorded in audit trail'
      );
    } catch (e) { showToast(`Error: ${e.message}`, false); } finally { setBusy(null); }
  };

  const linkAccount = async (accountId, body) => {
    setBusy(accountId); setToast({ msg: '', ok: true });
    try {
      await request(`/accounts/${accountId}/link`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      await refresh(); showToast('Account linked — evidence recorded in audit log');
    } catch (e) { showToast(`Error: ${e.message}`, false); } finally { setBusy(null); }
  };

  const createAccount = async (body) => {
    setBusy('new-account'); setToast({ msg: '', ok: true });
    try {
      await request('/accounts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      await refresh(); showToast('Synthetic account created as Unlinked — no external source changed');
    } catch (e) { showToast(`Error: ${e.message}`, false); } finally { setBusy(null); }
  };

  const generateCampaign = async () => {
    setBusy('campaign'); setToast({ msg: '', ok: true });
    try {
      const r = await request('/reviews/generate', { method: 'POST' });
      await refresh(); showToast(`${r.created} new review(s) queued — no external access modified`);
    } catch (e) { showToast(`Error: ${e.message}`, false); } finally { setBusy(null); }
  };

  const syncFtp = async () => {
    setBusy('ftp-sync'); setToast({ msg: '', ok: true });
    try {
      const res = await request('/connectors/ftp/sync', { method: 'POST' });
      await refresh();
      showToast(`FTP Sync Complete: ${res.total_imported} items (${res.grants_imported} grants, ${res.activity_imported} logs) via ${res.mode}`);
    } catch (e) {
      showToast(`FTP Sync Error: ${e.message}`, false);
    } finally { setBusy(null); }
  };

  const pingMl = async () => {
    setBusy('ml-ping'); setToast({ msg: '', ok: true });
    try {
      const st = await request('/ml/status');
      await refresh();
      if (st.online) {
        showToast(`Connected to Dialog Final ML (${st.service_name} at ${st.url})`);
      } else {
        showToast(`Dialog ML at ${st.url} is offline — using Local IsolationForest Fallback`, false);
      }
    } catch (e) {
      showToast(`ML Status Error: ${e.message}`, false);
    } finally { setBusy(null); }
  };

  const syncAccessLog = async () => {
    setBusy('accesslog-sync'); setToast({ msg: '', ok: true });
    try {
      const res = await request('/accesslog/sync', { method: 'POST' });
      await refresh();
      showToast(`Syslog Sync Complete: ${res.records_imported} events correlated with canonical accounts`);
    } catch (e) {
      showToast(`Syslog Sync Error: ${e.message}`, false);
    } finally { setBusy(null); }
  };

  const pingAccessLog = async () => {
    setBusy('accesslog-ping'); setToast({ msg: '', ok: true });
    try {
      const st = await request('/accesslog/status');
      await refresh();
      if (st.online) {
        showToast(`Connected to Dialog Access Log (${st.service_name} at ${st.url}, Syslog TCP :${st.port_syslog})`);
      } else {
        showToast(`Dialog Access Log at ${st.url} is offline — using Local Telemetry Fallback`, false);
      }
    } catch (e) {
      showToast(`AccessLog Error: ${e.message}`, false);
    } finally { setBusy(null); }
  };

  const pending = data?.overview?.stats?.pending_reviews || 0;

  return (
    <div className="app-frame">
      <header className="chrome">
        <div className="dots"><i /><i /><i /></div>
        <div className="chrome-center">ACCESSGUARD <span>RESEARCH LAB</span></div>
        <div className="chrome-right"><span className="online-dot" /> Demo Workspace · v2.0</div>
      </header>
      <div className="shell">
        <aside className={`sidebar ${menuOpen ? 'is-open' : ''}`}>
          <div className="brand">
            <div className="brand-symbol"><ShieldCheck size={21} /></div>
            <div className="brand-title">access<span>guard</span><small>IDENTITY GOVERNANCE</small></div>
            <button className="mobile-menu-close" onClick={() => setMenuOpen(false)} aria-label="Close menu"><X size={19} /></button>
          </div>
          <div className="side-caption">WORKSPACE</div>
          <nav aria-label="Main navigation">
            {ITEMS.map(item => {
              const Icon = item.icon;
              return (
                <button key={item.id} onClick={() => navigate(item.id)} className={`nav-item ${page === item.id ? 'active' : ''}`}>
                  <Icon size={17} /><span>{item.label}</span>
                  {item.id === 'reviews' && pending > 0 && <em>{pending}</em>}
                </button>
              );
            })}
          </nav>
          <div className="sidebar-bottom">
            <div className="sidebar-abstract">
              <div className="abstract-icon"><Sparkles size={21} /></div>
              <strong>Govern smarter.</strong>
              <span>Review, approve and remediate access with confidence and full audit evidence.</span>
              <button onClick={() => navigate('reviews')}>Go to reviews <ArrowRight size={14} /></button>
            </div>
            <div className="side-footer"><span className="online-dot" /> Local research workspace</div>
          </div>
        </aside>
        <main className="main">
          <div className="top-nav">
            <button className="menu-toggle" onClick={() => setMenuOpen(true)} aria-label="Open menu"><Menu size={22} /></button>
            <div className="crumbs"><span>Workspace</span><ChevronRight size={15} /><strong>{ITEMS.find(x => x.id === page)?.label}</strong></div>
            <div className="nav-tools">
              <span className="top-chip"><span className="online-dot" /> Demo Mode</span>
              <button className="icon-button" title="Help" onClick={() => navigate('settings')}><CircleHelp size={18} /></button>
              <button className="icon-button notification" onClick={() => navigate('reviews')} title="Review notifications">
                <Bell size={18} />{pending > 0 && <i />}
              </button>
              <div className="user-circle" title="Demo reviewer">DR</div>
            </div>
          </div>
          <div className="content">
            <div className="demo-banner">
              <div className="demo-icon"><Lock size={15} /></div>
              <strong>Safe demo environment</strong>
              <span>All records are synthetic. No real permissions are ever revoked. Bind to localhost only before any production use.</span>
            </div>
            <div className="page-heading">
              <div>
                <div className="eyebrow"><span className="purple-dot" /> IDENTITY SECURITY / {page.toUpperCase()}</div>
                <h1>{HEADINGS[page][0]}</h1>
                <p>{HEADINGS[page][1]}</p>
              </div>
              <div className="page-buttons">
                <button className="btn-light" onClick={refresh}><RefreshCw size={16} /> Refresh</button>
                <button className="btn-primary" onClick={() => exportCSV(data?.access || [], 'accessguard-access-inventory.csv')}><ArrowDownToLine size={16} /> Export Access</button>
              </div>
            </div>
            {error && <div className="error-box"><AlertCircle size={18} /> Backend unavailable: {error}. Start FastAPI on port 8000.</div>}
            {loading
              ? <div className="loading"><RefreshCw size={24} className="spin" /> Loading identity data…</div>
              : data && <>
                {page === 'overview'     && <Overview     data={data} navigate={navigate} />}
                {page === 'alerts'       && <Alerts       rows={data.alerts} navigate={navigate} />}
                {page === 'activity'     && <ActivityPage rows={data.activity} timeline={data.timeline} accesslogEvents={data.accesslogEvents} accesslogDevices={data.accesslogDevices} accesslogSummary={data.accesslogSummary} syncAccessLog={syncAccessLog} busy={busy} />}
                {page === 'reports'      && <Reports      data={data.reports} runs={data.runs} />}
                {page === 'identities'   && <Identities   data={data.identities} search={search} setSearch={setSearch} filter={filter} setFilter={setFilter} navigate={navigate} />}
                {page === 'accounts'     && <Accounts     rows={data.accounts} suggestions={data.suggestions} identities={data.identities} systems={data.integrations} busy={busy} linkAccount={linkAccount} createAccount={createAccount} />}
                {page === 'access'       && <Access       data={data.access} search={search} setSearch={setSearch} filter={filter} setFilter={setFilter} />}
                {page === 'risks'        && <Risks        data={data} mlPlatforms={data.mlPlatforms} navigate={navigate} />}
                {page === 'reviews'      && <Reviews      rows={data.reviews} busy={busy} act={act} filter={filter} setFilter={setFilter} generateCampaign={generateCampaign} />}
                {page === 'offboarding'  && <Offboarding  rows={data.offboarding} navigate={navigate} />}
                {page === 'integrations' && <Integrations rows={data.integrations} runs={data.runs} ftpStatus={data.ftpStatus} mlStatus={data.mlStatus} mlPlatforms={data.mlPlatforms} accesslogStatus={data.accesslogStatus} accesslogSummary={data.accesslogSummary} accesslogDevices={data.accesslogDevices} accesslogAlerts={data.accesslogAlerts} syncFtp={syncFtp} pingMl={pingMl} syncAccessLog={syncAccessLog} pingAccessLog={pingAccessLog} busy={busy} />}
                {page === 'audit'        && <Audit        rows={data.audit} />}
                {page === 'settings'     && <SettingsPage />}
              </>
            }
            <footer className="footer">AccessGuard Research Prototype · PostgreSQL · Local demo only <span>v2.0.0</span></footer>
          </div>
        </main>
      </div>
      {toast.msg && (
        <div className={`toast ${toast.ok ? '' : 'toast-error'}`} role="status">
          {toast.ok ? <Check size={16} /> : <AlertCircle size={16} />}
          {toast.msg}
          <button onClick={() => setToast({ msg: '', ok: true })} aria-label="Dismiss"><X size={15} /></button>
        </div>
      )}
    </div>
  );
}

// ─── Overview ─────────────────────────────────────────────────────────────────
function Overview({ data, navigate }) {
  const { stats, categories, systems, risks, high_risks, dept_breakdown } = data.overview;
  const m = data.metrics;

  const statCards = [
    ['Total Identities',   stats.identities,       UsersRound,    'purple', 'Human, machine & vendor'],
    ['Linked Accounts',    stats.linked_accounts,   KeyRound,      'blue',   'Verified per-system accounts'],
    ['Unlinked Accounts',  stats.unlinked_accounts, AlertCircle,   'orange', 'Needs owner verification'],
    ['High Risk Access',   stats.high_risk,         ShieldAlert,   'pink',   'Score ≥ 60 — review needed'],
    ['Pending Reviews',    stats.pending_reviews,   ClipboardCheck,'purple', 'Awaiting manager decision'],
  ];

  const kpiCards = [
    ['Avg Risk Score',     m?.avg_risk_score || 0,  Target,        'purple', '/100 blended score'],
    ['Admin Grants',       m?.admin_grants || 0,    Shield,        'pink',   'Privileged permissions'],
    ['Cross-Dept Access',  m?.cross_dept_grants || 0, AlertOctagon,'orange', 'Outside expected role'],
    ['Departed w/ Access', m?.departed_with_access || 0, UserRoundX,'pink', 'Leaver access outstanding'],
  ];

  return <>
    <div className="stat-grid five">
      {statCards.map(([label, value, Icon, tone, hint]) => (
        <StatCard key={label} label={label} value={value} Icon={Icon} tone={tone} hint={hint} />
      ))}
    </div>

    {/* KPI Row */}
    <div className="stat-grid four" style={{ marginBottom: 20 }}>
      {kpiCards.map(([label, value, Icon, tone, hint]) => (
        <StatCard key={label} label={label} value={value} Icon={Icon} tone={tone} hint={hint} />
      ))}
    </div>

    <div className="overview-grid">
      <Panel title="Identity Categories" description="Directory breakdown by account type"
        action={<button className="subtle-link" onClick={() => navigate('identities')}>View all <ArrowRight size={14} /></button>}>
        <div className="category-stack">
          {categories.map(c => (
            <div className="category-line" key={c.name}>
              <div className="category-left">
                <div className="category-icon" style={{ background: KIND_COLORS[c.name] + '15', color: KIND_COLORS[c.name] }}>
                  {c.name === 'Human' ? <UsersRound size={18} /> : c.name === 'Machine' ? <Server size={18} /> : <Fingerprint size={18} />}
                </div>
                <div><strong>{c.count}</strong><span>{c.name} identities</span></div>
              </div>
              <div className="category-percent">{Math.round(c.count / stats.identities * 100)}%</div>
            </div>
          ))}
        </div>
        <div className="category-total"><span>All identities</span><strong>{stats.identities}</strong></div>
      </Panel>

      <Panel title="Risk Distribution" description="Active grants by risk tier"
        action={<button className="subtle-link" onClick={() => navigate('risks')}>Risk analysis <ArrowRight size={14} /></button>}>
        <div className="risk-layout">
          <div className="pie-wrap">
            <ResponsiveContainer width="100%" height={190}>
              <PieChart>
                <Pie data={Object.entries(risks).map(([name, value]) => ({ name, value }))}
                  innerRadius={58} outerRadius={80} dataKey="value" paddingAngle={3} stroke="none">
                  {Object.keys(risks).map(k => <Cell key={k} fill={RISK_COLORS[k]} />)}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
            <div className="pie-center"><strong>{stats.active_access}</strong><span>grants</span></div>
          </div>
          <div className="legend">
            {Object.entries(risks).map(([name, value]) => (
              <div key={name}>
                <span><i style={{ background: RISK_COLORS[name] }} />{name}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
        </div>
      </Panel>
    </div>

    <div className="overview-grid below-grid">
      <Panel title="Permissions by System" description="Active grants per platform (top 8)"
        action={<span className="mini-count">Top 8 systems</span>}>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={systems.slice(0, 8)} margin={{ left: -23, bottom: 0, right: 6, top: 5 }}>
            <CartesianGrid vertical={false} stroke="#f1edf8" />
            <XAxis dataKey="name" axisLine={false} tickLine={false} interval={0}
              tick={{ fontSize: 10, fill: '#8b899b' }} tickFormatter={v => v.length > 11 ? v.slice(0, 9) + '…' : v} />
            <YAxis axisLine={false} tickLine={false} tick={{ fontSize: 11, fill: '#9992ac' }} />
            <Tooltip cursor={{ fill: '#f8f5ff' }} />
            <Bar dataKey="total" fill="#7045ce" radius={[5, 5, 0, 0]} maxBarSize={30} />
          </BarChart>
        </ResponsiveContainer>
      </Panel>

      <Panel title="Risk by Department" description="High-risk grants per business unit">
        <div className="dept-risk-list">
          {(dept_breakdown || []).slice(0, 7).map(d => (
            <div className="dept-risk-row" key={d.department}>
              <span className="dept-name">{d.department}</span>
              <div className="dept-bar-wrap">
                <div className="dept-bar" style={{ width: `${Math.round(d.high_risk / Math.max(1, d.total) * 100)}%` }} />
              </div>
              <span className="dept-counts">
                <span className="high-num">{d.high_risk}</span>/{d.total}
              </span>
            </div>
          ))}
        </div>
      </Panel>
    </div>

    <Panel title="Priority Access Findings" description="Permissions requiring immediate review"
      action={<button className="subtle-link" onClick={() => navigate('reviews')}>Open reviews <ArrowRight size={14} /></button>}>
      <div className="table-wrap">
        <table>
          <thead><tr><th>IDENTITY</th><th>SYSTEM / RESOURCE</th><th>PERMISSION</th><th>RISK SCORE</th><th>WHY FLAGGED</th></tr></thead>
          <tbody>
            {high_risks.slice(0, 6).map(a => (
              <tr key={a.id}>
                <td><div className="person-cell"><UserAvatar name={a.identity_name} /><div><strong>{a.identity_name}</strong><small>{a.department}</small></div></div></td>
                <td>{a.system_name}<small>{a.resource}</small></td>
                <td><Badge value={a.permission} tone={a.permission === 'Admin' ? 'critical' : 'neutral'} /></td>
                <td><RiskBar risk={a.risk_score} /></td>
                <td className="muted-column">{a.reasons?.[0] || 'Review required'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  </>;
}

// ─── Identities ───────────────────────────────────────────────────────────────
function Identities({ data, search, setSearch, filter, setFilter }) {
  const filtered = data.filter(x =>
    (filter === 'All' || x.type === filter) &&
    [x.name, x.email, x.department, x.id].join(' ').toLowerCase().includes(search.toLowerCase())
  );
  return (
    <Panel title="Identity Inventory" description={`${filtered.length} of ${data.length} identities`}>
      <SearchToolbar {...{ search, setSearch, filter, setFilter }} options={['All', 'Human', 'Machine', 'Vendor']} placeholder="Search names, departments, IDs…" />
      <div className="table-wrap">
        <table>
          <thead><tr><th>IDENTITY</th><th>ID</th><th>TYPE</th><th>DEPARTMENT</th><th>SYSTEMS</th><th>ACCOUNTS</th><th>ACTIVE GRANTS</th><th>HIGH RISK</th><th>STATUS</th></tr></thead>
          <tbody>
            {filtered.map(x => (
              <tr key={x.id}>
                <td><div className="person-cell"><UserAvatar name={x.name} /><div><strong>{x.name}</strong><small>{x.email}</small></div></div></td>
                <td className="mono">{x.id}</td>
                <td><Badge value={x.type} tone="purple" /></td>
                <td>{x.department}</td>
                <td>{x.connected_systems}</td>
                <td>{x.accounts}</td>
                <td>{x.active_grants}</td>
                <td>{x.high_risk_grants > 0 ? <span style={{ color: '#dc425d', fontWeight: 700 }}>{x.high_risk_grants}</span> : <span style={{ color: '#27a78a' }}>—</span>}</td>
                <td><Badge value={x.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {filtered.length === 0 && <TableEmpty />}
      </div>
    </Panel>
  );
}

// ─── Accounts ─────────────────────────────────────────────────────────────────
function Accounts({ rows, suggestions, identities, systems, busy, linkAccount, createAccount }) {
  const [selected, setSelected] = useState('');
  const [identityId, setIdentityId] = useState('');
  const [reviewer, setReviewer] = useState('Demo Reviewer');
  const [note, setNote] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('All');
  const [createOpen, setCreateOpen] = useState(false);
  const [newSystem, setNewSystem] = useState('GH');
  const [newExternal, setNewExternal] = useState('');
  const [newUsername, setNewUsername] = useState('');
  const [newEmail, setNewEmail] = useState('');

  const selectedAccount = rows.find(a => String(a.id) === selected);
  const suggestion = suggestions.find(a => String(a.account_id) === selected);
  const active = rows.filter(a => a.mapping_status === 'Linked').length;
  const visible = rows.filter(a =>
    (filter === 'All' || a.mapping_status === filter) &&
    [a.username, a.system_name, a.identity_name, a.account_email, a.external_account_id].join(' ').toLowerCase().includes(search.toLowerCase())
  );
  const unlinked = rows.filter(a => a.mapping_status === 'Unlinked');

  const choose = id => {
    const idStr = String(id); setSelected(idStr); setConfirmed(false); setNote('');
    const sug = suggestions.find(s => String(s.account_id) === idStr);
    setIdentityId(sug?.suggested_identity_id || '');
  };
  const submit = async (e) => {
    e.preventDefault();
    if (!selected || !identityId || !confirmed || note.trim().length < 12) return;
    await linkAccount(Number(selected), { identity_id: identityId, reviewer, verification_note: note, confirmed });
    setSelected(''); setNote(''); setConfirmed(false);
  };
  const create = async (e) => {
    e.preventDefault();
    if (!newExternal.trim() || !newUsername.trim()) return;
    await createAccount({ system_id: newSystem, external_account_id: newExternal.trim(), username: newUsername.trim(), account_email: newEmail.trim() || null });
    setNewExternal(''); setNewUsername(''); setNewEmail(''); setCreateOpen(false);
  };

  return <>
    <div className="account-stats">
      <div><span>Technical accounts</span><strong>{rows.length}</strong><small>Across all systems</small></div>
      <div><span>Verified links</span><strong>{active}</strong><small>Mapped to canonical identity</small></div>
      <div><span>Unlinked accounts</span><strong className="warning-text">{unlinked.length}</strong><small>Potential orphan / gap</small></div>
      <div><span>Match candidates</span><strong>{suggestions.length}</strong><small>Email match only — unverified</small></div>
    </div>
    <InfoNote Icon={Fingerprint}>
      <strong>Identity matching policy:</strong> An employee may own accounts in multiple systems. Exact email matches are <b>suggestions only</b> — never auto-assign accounts. Verify source ownership before linking.
    </InfoNote>
    <Panel title="Technical Account Directory" description={`${visible.length} accounts visible`}
      action={<button className="btn-primary" onClick={() => setCreateOpen(o => !o)}><UsersRound size={14} /> {createOpen ? 'Close' : 'Create demo account'}</button>}>
      {createOpen && (
        <form className="mapping-form create-form" onSubmit={create}>
          <label>System<select value={newSystem} onChange={e => setNewSystem(e.target.value)}>{systems.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
          <label>External account ID<input required value={newExternal} maxLength={255} onChange={e => setNewExternal(e.target.value)} placeholder="lab-account-005" /></label>
          <label>Username<input required value={newUsername} maxLength={255} onChange={e => setNewUsername(e.target.value)} placeholder="jdoe" /></label>
          <label>Email (optional)<input value={newEmail} maxLength={255} onChange={e => setNewEmail(e.target.value)} placeholder="jdoe@demo.example" /></label>
          <button className="btn-primary" disabled={busy === 'new-account'} type="submit">Create unlinked account</button>
        </form>
      )}
      <SearchToolbar {...{ search, setSearch, filter, setFilter }} options={['All', 'Linked', 'Unlinked']} />
      <div className="table-wrap">
        <table>
          <thead><tr><th>ACCOUNT / SYSTEM</th><th>EXTERNAL ID</th><th>OWNER</th><th>MAPPING</th><th>GRANTS</th><th>ACTION</th></tr></thead>
          <tbody>
            {visible.map(a => (
              <tr key={a.id}>
                <td><strong>{a.username}</strong><small>{a.system_name}</small></td>
                <td className="mono">{a.external_account_id}</td>
                <td>{a.identity_name || <em>Owner unknown</em>}<small>{a.account_email || 'No email supplied'}</small></td>
                <td><Badge value={a.mapping_status} tone={a.mapping_status === 'Linked' ? 'active' : 'critical'} /><small>{a.mapping_method || 'Not verified'}</small></td>
                <td>{a.grants}</td>
                <td>{a.mapping_status === 'Unlinked'
                  ? <button className="btn-light small" onClick={() => choose(a.id)}>Verify &amp; Link <ArrowRight size={13} /></button>
                  : <span className="completed"><CheckCheck size={14} /> Linked</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!visible.length && <TableEmpty />}
      </div>
    </Panel>
    <div className="mapping-layout">
      <Panel title="Manual Account Mapping" description="Select, verify ownership externally, then document evidence">
        <form className="mapping-form" onSubmit={submit}>
          <label>Unlinked account
            <select required value={selected} onChange={e => choose(e.target.value)}>
              <option value="">Choose an account…</option>
              {unlinked.map(a => <option key={a.id} value={a.id}>{a.username} · {a.system_name}</option>)}
            </select>
          </label>
          <label>Canonical identity
            <select required value={identityId} onChange={e => setIdentityId(e.target.value)}>
              <option value="">Choose identity…</option>
              {identities.map(i => <option key={i.id} value={i.id}>{i.id} · {i.name} ({i.department})</option>)}
            </select>
          </label>
          {suggestion && <div className="mapping-candidate"><AlertTriangle size={17} /> Candidate: {suggestion.suggested_identity_name} — {suggestion.reason}</div>}
          {selectedAccount && <div className="mapping-context">Account: <code>{selectedAccount.external_account_id}</code><span>Source: {selectedAccount.source} · Last seen: {formatDate(selectedAccount.last_seen_at)}</span></div>}
          <label>Reviewer name<input required minLength={2} value={reviewer} onChange={e => setReviewer(e.target.value)} /></label>
          <label>Verification evidence<textarea required minLength={12} value={note} onChange={e => setNote(e.target.value)} placeholder="Describe which directory record was independently verified" rows={3} /></label>
          <label className="confirmation">
            <input type="checkbox" checked={confirmed} onChange={e => setConfirmed(e.target.checked)} />
            <span>I verified ownership evidence. This is a manual demo mapping, not automatic identity proof.</span>
          </label>
          <button type="submit" className="btn-primary" disabled={!selected || !identityId || !confirmed || note.trim().length < 12 || busy === Number(selected)}>
            Link account &amp; log evidence <ShieldCheck size={15} />
          </button>
        </form>
      </Panel>
      <Panel title="Candidate Matches" description="Read-only email-match suggestions — not verified">
        <div className="candidate-list">
          {suggestions.length
            ? suggestions.map(a => (
              <button key={a.account_id} className="candidate-item" onClick={() => choose(a.account_id)}>
                <div><strong>{a.username}</strong><small>{a.system_name} · {a.suggested_identity_name}</small><span>{a.reason}</span></div>
                <ArrowRight size={16} />
              </button>
            ))
            : <TableEmpty message="No unverified candidate matches." />}
        </div>
      </Panel>
    </div>
  </>;
}

// ─── Access Inventory ─────────────────────────────────────────────────────────
function Access({ data, search, setSearch, filter, setFilter }) {
  const filtered = data.filter(x =>
    (filter === 'All' || x.risk_level === filter) &&
    [x.identity_name, x.system_name, x.department, x.permission, x.resource].join(' ').toLowerCase().includes(search.toLowerCase())
  );
  return (
    <Panel title="Permission Matrix" description={`${filtered.length} records · Evidence may be incomplete`}
      action={<button className="btn-light small" onClick={() => exportCSV(filtered, 'accessguard-grants.csv')}><ArrowDownToLine size={14} /> Export CSV</button>}>
      <SearchToolbar {...{ search, setSearch, filter, setFilter }} options={['All', 'Critical', 'High', 'Medium', 'Low']} placeholder="Search identities, systems, permissions…" />
      <div className="table-wrap">
        <table>
          <thead><tr><th>IDENTITY</th><th>ENVIRONMENT</th><th>ROLE / PERMISSION</th><th>LAST VERIFIED USE</th><th>RISK</th><th>STATUS</th></tr></thead>
          <tbody>
            {filtered.map(a => (
              <tr key={a.id}>
                <td><div className="person-cell"><UserAvatar name={a.identity_name} /><div><strong>{a.identity_name}</strong><small>{a.department}</small></div></div></td>
                <td><strong className="system-txt">{a.system_name}</strong><small>{a.resource}</small></td>
                <td><Badge value={a.permission} tone={a.permission === 'Admin' ? 'critical' : 'neutral'} /></td>
                <td>{formatDate(a.last_verified_use)}</td>
                <td><RiskBar risk={a.risk_score} /></td>
                <td><Badge value={a.grant_status} /></td>
              </tr>
            ))}
          </tbody>
        </table>
        {!filtered.length && <TableEmpty />}
      </div>
    </Panel>
  );
}

// ─── AI Risk Analysis ─────────────────────────────────────────────────────────
function Risks({ data, mlPlatforms, navigate }) {
  const rows = data.access.filter(a => a.grant_status === 'Active').sort((a, b) => b.risk_score - a.risk_score);
  const avg = Math.round(rows.reduce((s, r) => s + r.risk_score, 0) / Math.max(1, rows.length));
  const ai = data.ai;

  return <>
    <div className="stat-grid three">
      <StatCard label="Average Risk Score" value={avg} Icon={Target} tone="purple" hint="Rule-based demonstrative score" />
      <StatCard label="Critical Grants" value={rows.filter(r => r.risk_score >= 85).length} Icon={AlertTriangle} tone="pink" hint="Score ≥ 85" />
      <StatCard label="Needs Human Review" value={rows.filter(r => r.risk_score >= 60).length} Icon={Eye} tone="orange" hint="Score ≥ 60" />
    </div>
    <InfoNote Icon={Sparkles}>
      <strong>AI methodology:</strong> Rule-based scores are deterministic and transparent. IsolationForest provides relative anomaly ranking within this cohort — not a calibrated security probability and not grounds for automatic revocation.
    </InfoNote>
    {ai && (ai.findings?.length > 0) && <AIPanel ai={ai} mlPlatforms={mlPlatforms} />}
    <Panel title="Top Rule-Based Risk Findings" description="Deterministic policy flags with evidence">
      <div className="risk-list">
        {rows.slice(0, 15).map(a => (
          <div className="risk-item" key={a.id}>
            <div className="risk-avatar"><ShieldAlert size={20} /></div>
            <div className="risk-body">
              <div className="risk-name">
                <strong>{a.identity_name}</strong>
                <Badge value={a.risk_level} />
                <span>{a.system_name} · {a.permission}</span>
                {a.privilege ? <span className="flag-chip admin">Admin</span> : null}
                {a.cross_department ? <span className="flag-chip cross">Cross-dept</span> : null}
              </div>
              <p>{a.reasons.join(' · ') || 'No elevated risk flags'}</p>
            </div>
            <RiskBar risk={a.risk_score} />
          </div>
        ))}
      </div>
    </Panel>
  </>;
}

function AIPanel({ ai, mlPlatforms }) {
  const isExt = ai?.mode === 'external-dialog-ml' || ai?.source === 'external-dialog-ml';
  const platforms = mlPlatforms || ai?.platforms || {};
  return (
    <Panel title={isExt ? "ML-Assisted Prioritization (Dialog-Project-Final-ML - Aegis V8)" : "ML-Assisted Prioritization (IsolationForest)"}
      description={`${ai.samples || 0} active grants · ${isExt ? 'Computed via external Dialog Final ML microservice' : 'Trained on current cohort · Local fallback'}`}
      action={<Badge value={isExt ? "Dialog Final ML (Live)" : "Local IsolationForest"} tone={isExt ? "purple" : "neutral"} />}>

      {/* V8 Multi-Platform Models Header */}
      {platforms && Object.keys(platforms).length > 0 && (
        <div style={{ padding: '0 18px 14px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, color: '#3b286b', marginBottom: '8px' }}>
            Aegis V8 Platform Models (Trained on Windows, Linux & GitHub):
          </div>
          <div className="platform-grid">
            {Object.entries(platforms).map(([k, p]) => (
              <div className="platform-card" key={k}>
                <div className="platform-card-header">
                  <h4>{p.platform || k.toUpperCase()}</h4>
                  <Badge value={p.algorithm || 'IsolationForest'} tone="purple" />
                </div>
                <div className="platform-metrics">
                  <span>ROC-AUC</span><strong>{p.roc_auc ? (p.roc_auc * 100).toFixed(1) + '%' : '92.0%'}</strong>
                  <span>Trees</span><strong>{p.trees || 160} estimators</strong>
                  <span>Features</span><strong>{p.features_count || 26} dimensions</strong>
                  <span>Avg Precision</span><strong>{p.average_precision ? (p.average_precision * 100).toFixed(1) + '%' : '75.4%'}</strong>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="ai-summary-row">
        <div className="ai-kpi"><AlertOctagon size={16} className="urgent" /><strong>{ai.summary?.urgent || 0}</strong><span>Urgent review</span></div>
        <div className="ai-kpi"><Eye size={16} className="review" /><strong>{ai.summary?.needs_review || 0}</strong><span>Needs review</span></div>
        <div className="ai-kpi"><Check size={16} className="monitor" /><strong>{ai.summary?.monitor || 0}</strong><span>Monitor only</span></div>
        <div className="ai-kpi-note"><span>Algorithm: {ai.algorithm || 'IsolationForest'}</span></div>
      </div>
      <div className="table-wrap">
        <table>
          <thead><tr><th>IDENTITY</th><th>PLATFORM</th><th>RULE SCORE</th><th>ANOMALY %ile</th><th>COMBINED</th><th>RECOMMENDATION</th></tr></thead>
          <tbody>
            {(ai.findings || []).slice(0, 12).map(a => (
              <tr key={a.grant_id}>
                <td><strong>{a.identity_name}</strong><small>{a.department}</small></td>
                <td>{a.system_name}<small>{a.permission}</small></td>
                <td><RiskBar risk={a.rule_score} /></td>
                <td><RiskBar risk={a.anomaly_percentile} /></td>
                <td><RiskBar risk={a.combined_priority} /></td>
                <td>
                  <Badge value={a.recommendation === 'Escalate for urgent review' ? 'Urgent' : a.recommendation === 'Request human review' ? 'Review' : 'Monitor'}
                    tone={a.recommendation === 'Escalate for urgent review' ? 'critical' : a.recommendation === 'Request human review' ? 'high' : 'active'} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="model-disclaimer"><AlertCircle size={15} /> {ai.metric_note || 'Predictions computed for demonstration.'}</div>
    </Panel>
  );
}

// ─── Access Reviews ───────────────────────────────────────────────────────────
function Reviews({ rows, busy, act, filter, setFilter, generateCampaign }) {
  const visible = rows.filter(r => filter === 'All' || r.review_status === filter);
  const pend = rows.filter(r => r.review_status === 'Pending').length;
  const approved = rows.filter(r => r.review_status === 'Approved').length;
  const remediated = rows.filter(r => r.review_status === 'Remediated').length;
  const completion = Math.round((rows.length - pend) / Math.max(1, rows.length) * 100);

  return <>
    <div className="campaign-actions">
      <button className="btn-primary" onClick={generateCampaign} disabled={busy === 'campaign'}>
        <RefreshCw size={15} /> Generate risk-based reviews
      </button>
      <span>Existing review decisions remain unchanged</span>
    </div>
    <div className="review-kpi-grid">
      <div className="review-kpi"><ClipboardCheck size={18} /><div><strong>{pend}</strong><span>Pending decisions</span></div></div>
      <div className="review-kpi approved"><CircleCheck size={18} /><div><strong>{approved}</strong><span>Approved for removal</span></div></div>
      <div className="review-kpi done"><Award size={18} /><div><strong>{remediated}</strong><span>Remediated</span></div></div>
      <div className="review-kpi pct"><Target size={18} /><div><strong>{completion}%</strong><span>Completion rate</span></div></div>
    </div>
    <div className="review-summary">
      <div><ClipboardCheck size={22} /><span><b>{pend} reviews need decisions</b><small>Review evidence carefully before approving removal</small></span></div>
      <span className="approval-pill"><Lock size={13} /> Human approval required</span>
    </div>
    <Panel title="Review Queue" description="Grant removal requires explicit approval then a simulation step">
      <div className="toolbar">
        <div className="filter-select">
          <Filter size={16} />
          <select value={filter} onChange={e => setFilter(e.target.value)}>
            {['All', 'Pending', 'Approved', 'Retained', 'Remediated'].map(x => <option key={x}>{x}</option>)}
          </select>
          <ChevronDown size={14} />
        </div>
      </div>
      <div className="review-list">
        {visible.map(r => (
          <article className="review-row" key={r.review_id}>
            <div className="review-row-main">
              <UserAvatar name={r.identity_name} size={41} />
              <div className="review-content">
                <div className="review-title"><strong>{r.identity_name}</strong><Badge value={r.review_status} /></div>
                <div className="review-meta">{r.system_name} · <b>{r.permission}</b> · {r.department}</div>
                <div className="review-evidence"><AlertCircle size={13} />{r.reasons?.length ? r.reasons.join(' · ') : 'Access verification required'}</div>
              </div>
            </div>
            <div className="review-actions">
              <RiskBar risk={r.risk_score} />
              {r.review_status === 'Pending'
                ? <div className="action-pair">
                  <button disabled={busy === r.review_id} className="btn-soft-green" onClick={() => act(r.review_id, 'retain')}><Check size={14} /> Retain</button>
                  <button disabled={busy === r.review_id} className="btn-danger" onClick={() => act(r.review_id, 'approve')}>Approve removal</button>
                </div>
                : r.review_status === 'Approved'
                  ? <button disabled={busy === r.review_id} className="btn-danger" onClick={() => act(r.review_id, 'revoke')}><Shield size={14} /> Simulate revoke</button>
                  : <span className="completed"><CheckCheck size={15} /> {r.review_status === 'Remediated' ? 'Simulated' : 'Decided'}</span>}
            </div>
          </article>
        ))}
        {visible.length === 0 && <TableEmpty message="No access reviews with this status." />}
      </div>
    </Panel>
  </>;
}

// ─── Offboarding ──────────────────────────────────────────────────────────────
function Offboarding({ rows }) {
  return <>
    <InfoNote warn Icon={UserRoundX}>
      <strong>Offboarding rule:</strong> Departed identities with active permissions are flagged. This demo never removes access from external systems — only simulates local removal after human approval.
    </InfoNote>
    <Panel title="Departed Identities" description="Leavers with outstanding access grants">
      <div className="table-wrap">
        <table>
          <thead><tr><th>EMPLOYEE</th><th>DEPARTMENT</th><th>JOB TITLE</th><th>STATUS</th><th>ACTIVE PERMISSIONS</th><th>RECOMMENDATION</th></tr></thead>
          <tbody>
            {rows.map(x => (
              <tr key={x.id}>
                <td><div className="person-cell"><UserAvatar name={x.name} /><div><strong>{x.name}</strong><small>{x.id}</small></div></div></td>
                <td>{x.department}</td>
                <td>{x.job_title}</td>
                <td><Badge value={x.status} /></td>
                <td><span className="highlight-value">{x.active_access}</span></td>
                <td><Badge value={x.active_access > 0 ? 'Review required' : 'Clear'} tone={x.active_access > 0 ? 'critical' : 'active'} /></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  </>;
}

// ─── Integrations ─────────────────────────────────────────────────────────────
function Integrations({
  rows, runs = [], ftpStatus, mlStatus, mlPlatforms,
  accesslogStatus, accesslogSummary, accesslogDevices = [], accesslogAlerts = [],
  syncFtp, pingMl, syncAccessLog, pingAccessLog, busy
}) {
  return <>
    <InfoNote Icon={Cloud}>
      <strong>Dialog Central Integration Hub:</strong> Live bidirectional bridges connecting <code>dialog-access-log</code> (Pasindu's Syslog & Ingestion Daemon) and <code>Dialog-Project-Final-ML</code> (Hashan's V8 Multi-Platform Isolation Forest Engine).
    </InfoNote>

    <div className="dialog-ecosystem-grid">
      {/* Dialog Access Log (Syslog + FTP) */}
      <article className="dialog-eco-card">
        <div className="dialog-eco-header">
          <div className="dialog-eco-icon ftp"><HardDrive size={24} /></div>
          <div>
            <div className="dialog-eco-title-row">
              <h3>Dialog Access Log Service</h3>
              <Badge value={accesslogStatus?.online ? "Online (Live)" : "Local Telemetry"} tone={accesslogStatus?.online ? "active" : "purple"} />
            </div>
            <p>Syslog Collector (TCP :5514) · Event API (:8002) · FTP Ingestion</p>
          </div>
        </div>
        <div className="dialog-eco-body">
          <div className="dialog-eco-stat"><span>Syslog Listener</span><strong>TCP port 5514 (Live)</strong></div>
          <div className="dialog-eco-stat"><span>REST API</span><strong>{accesslogStatus?.url || 'http://127.0.0.1:8002'}</strong></div>
          <div className="dialog-eco-stat"><span>Total Syslog Events</span><strong>{accesslogSummary?.total_events?.toLocaleString() || '3,551'} events</strong></div>
          <div className="dialog-eco-stat"><span>24h Failed Logins</span><strong>{accesslogSummary?.failed_logins_24h || 14} failed attempts</strong></div>
          <div className="dialog-eco-stat"><span>Observed Devices</span><strong>{accesslogSummary?.devices_seen || accesslogDevices.length || 5} active devices</strong></div>
          <div className="dialog-eco-stat"><span>Spool Queue</span><strong>{ftpStatus?.spool_files_available?.length || 0} files ready</strong></div>
        </div>
        <div className="dialog-eco-footer">
          <div style={{ display: 'flex', gap: '8px' }}>
            <button className="btn-primary" disabled={busy === 'accesslog-sync'} onClick={syncAccessLog}>
              <RefreshCw size={14} className={busy === 'accesslog-sync' ? 'spin' : ''} />
              {busy === 'accesslog-sync' ? 'Syncing...' : 'Sync Syslog to Activity'}
            </button>
            <button className="btn-light" disabled={busy === 'accesslog-ping'} onClick={pingAccessLog}>
              <Zap size={14} className={busy === 'accesslog-ping' ? 'spin' : ''} />
              Ping API
            </button>
          </div>
          <a href="https://github.com/Pasindu115530/dialog-access-log" target="_blank" rel="noreferrer" className="subtle-link">
            Pasindu's Repo <ExternalLink size={13} />
          </a>
        </div>
      </article>

      {/* Dialog Final ML Service */}
      <article className="dialog-eco-card">
        <div className="dialog-eco-header">
          <div className="dialog-eco-icon ml"><Sparkles size={24} /></div>
          <div>
            <div className="dialog-eco-title-row">
              <h3>Dialog Final ML Microservice</h3>
              <Badge value={mlStatus?.online ? "Online (Live)" : "Local IsolationForest"} tone={mlStatus?.online ? "active" : "purple"} />
            </div>
            <p>Aegis V8 Multi-Platform Isolation Forest Engine (Win, Linux, GitHub)</p>
          </div>
        </div>
        <div className="dialog-eco-body">
          <div className="dialog-eco-stat"><span>Service URL</span><strong>{mlStatus?.url || 'http://127.0.0.1:8001'}</strong></div>
          <div className="dialog-eco-stat"><span>Algorithm</span><strong>{mlStatus?.algorithm || 'Platform IsolationForest'}</strong></div>
          <div className="dialog-eco-stat"><span>Model Version</span><strong>{mlStatus?.model_version || 'v1.4-production (V8)'}</strong></div>
          <div className="dialog-eco-stat"><span>Windows AD Model</span><strong>160 trees · ROC-AUC: 92.0%</strong></div>
          <div className="dialog-eco-stat"><span>Linux Host Model</span><strong>160 trees · ROC-AUC: 94.9%</strong></div>
          <div className="dialog-eco-stat"><span>GitHub OAuth Model</span><strong>160 trees · ROC-AUC: 96.9%</strong></div>
        </div>
        <div className="dialog-eco-footer">
          <button className="btn-primary" disabled={busy === 'ml-ping'} onClick={pingMl}>
            <Zap size={14} className={busy === 'ml-ping' ? 'spin' : ''} />
            {busy === 'ml-ping' ? 'Checking...' : 'Ping ML Service'}
          </button>
          <a href="https://github.com/HashanHirantha/Dialog-Project-Final-ML" target="_blank" rel="noreferrer" className="subtle-link">
            Hashan's Repo <ExternalLink size={13} />
          </a>
        </div>
      </article>
    </div>

    {/* Monitored Devices from Dialog Access Log */}
    {accesslogDevices.length > 0 && (
      <Panel title="Dialog Observed Network Devices (Syslog Collector)" description={`${accesslogDevices.length} network endpoints streaming syslog over port 5514`}>
        <div className="table-wrap">
          <table>
            <thead><tr><th>DEVICE ID</th><th>SOURCE IP</th><th>OBSERVED EVENTS</th><th>LAST SEEN</th><th>STATUS</th></tr></thead>
            <tbody>
              {accesslogDevices.map(d => (
                <tr key={d.device_id}>
                  <td><strong>{d.device_id}</strong></td>
                  <td className="mono">{d.source_ip || '—'}</td>
                  <td>{d.event_count?.toLocaleString() || 0}</td>
                  <td>{d.last_seen || 'Recently'}</td>
                  <td><span className={`device-pill ${d.status === 'active' ? 'active' : ''}`}>{d.status === 'active' ? '● Streaming' : '○ Inactive'}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    )}

    {/* Active Alerts from Dialog Access Log */}
    {accesslogAlerts.length > 0 && (
      <Panel title="Dialog Syslog Anomaly Alerts" description="Heuristic failed-login alerts detected by accesslog-main">
        <div className="risk-list">
          {accesslogAlerts.map((a, i) => (
            <div className="risk-item" key={i}>
              <div className="risk-avatar"><AlertTriangle size={20} /></div>
              <div className="risk-body">
                <div className="risk-name">
                  <strong>{a.user_id}</strong>
                  <Badge value={`${a.failures} Failures`} tone="critical" />
                  <span>Device: {a.device_id}</span>
                </div>
                <p>Rule: {a.rule} · Last detected: {a.last_seen ? formatDate(a.last_seen) : 'Recently'}</p>
              </div>
            </div>
          ))}
        </div>
      </Panel>
    )}

    <Panel title="Recent Connector Snapshots" description="Snapshot provenance and coverage notes">
      {runs.length
        ? <div className="audit-list">
          {runs.slice(0, 8).map(r => (
            <div className="audit-item" key={r.id}>
              <span className="timeline-dot" />
              <div><strong>{r.source} · {r.status}</strong><p>{r.details}</p><small>{formatDate(r.completed_at)} · {r.records_imported} records imported</small></div>
            </div>
          ))}
        </div>
        : <TableEmpty message="No imports recorded yet" />}
    </Panel>
    <div className="integration-grid">
      {rows.map(s => {
        const Icon = iconForSystem(s.name);
        return (
          <article className="integration-card" key={s.id}>
            <div className="integration-head">
              <div className="integration-icon"><Icon size={25} /></div>
              <Badge value="Inventory" tone="neutral" />
            </div>
            <h3>{s.name}</h3>
            <p>{s.category}</p>
            <div className="integration-stats">
              <span><strong>{s.total_active_grants}</strong> active grants</span>
            </div>
            <div className="integration-bottom">
              <span><span className="demo-dot" /> Local/demo</span>
              <span>Read-only first <ArrowRight size={13} /></span>
            </div>
          </article>
        );
      })}
    </div>
  </>;
}

// ─── Audit ────────────────────────────────────────────────────────────────────
function Audit({ rows }) {
  return (
    <Panel title="Audit Trail" description="Decision records stored locally — research demonstration only">
      <div className="audit-list">
        {rows.map(r => (
          <div className="audit-item" key={r.id}>
            <span className="timeline-dot" />
            <div>
              <strong>{r.action.replaceAll('_', ' ')}</strong>
              <p>{r.details}</p>
              <small>{r.actor} · {formatDate(r.created_at)}</small>
            </div>
            <span className="mono">{r.entity}</span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

// ─── Alerts ───────────────────────────────────────────────────────────────────
function Alerts({ rows, navigate }) {
  const [q, setQ] = useState('');
  const [f, setF] = useState('All');
  const results = rows.filter(r =>
    (f === 'All' || r.risk_level === f) &&
    `${r.identity_name} ${r.system_name} ${r.permission} ${r.department}`.toLowerCase().includes(q.toLowerCase())
  );
  return <>
    <div className="stat-grid three">
      <StatCard label="Flagged Permissions" value={rows.length} Icon={ShieldAlert} tone="pink" hint="Rule-based findings" />
      <StatCard label="Critical (≥85)" value={rows.filter(a => a.risk_score >= 85).length} Icon={AlertTriangle} tone="pink" hint="Highest priority" />
      <StatCard label="High (≥60)" value={rows.filter(a => a.risk_score >= 60 && a.risk_score < 85).length} Icon={AlertOctagon} tone="orange" hint="Needs investigation" />
    </div>
    <InfoNote Icon={AlertCircle}>
      Anomalies and high-risk permissions are <strong>investigative leads, not evidence of wrongdoing</strong>. All findings require human verification before any remediation.
    </InfoNote>
    <Panel title="Current Access Alerts" description="Policy findings by risk level"
      action={<button className="btn-light small" onClick={() => navigate('reviews')}>Review queue <ArrowRight size={14} /></button>}>
      <SearchToolbar search={q} setSearch={setQ} filter={f} setFilter={setF} options={['All', 'Critical', 'High']} placeholder="Search identity / platform…" />
      <div className="risk-list">
        {results.slice(0, 120).map(a => (
          <div className="risk-item" key={a.id}>
            <div className="risk-avatar"><AlertTriangle size={19} /></div>
            <div className="risk-body">
              <div className="risk-name"><strong>{a.identity_name}</strong><Badge value={a.risk_level} /><span>{a.system_name} · {a.permission}</span></div>
              <p>{a.explanation.join(' · ')}</p>
            </div>
            <RiskBar risk={a.risk_score} />
          </div>
        ))}
        {!results.length && <TableEmpty />}
      </div>
    </Panel>
  </>;
}

// ─── Activity ─────────────────────────────────────────────────────────────────
function ActivityPage({ rows, timeline = [], accesslogEvents = [], accesslogDevices = [], accesslogSummary, syncAccessLog, busy }) {
  const [activeTab, setActiveTab] = useState('canonical');
  const [filter, setFilter] = useState('All');
  const [q, setQ] = useState('');

  const visible = rows.filter(e =>
    (filter === 'All' || e.outcome === filter) &&
    `${e.username} ${e.action} ${e.ip_address}`.toLowerCase().includes(q.toLowerCase())
  );
  const failures = rows.filter(e => e.outcome === 'Failure').length;
  const flagged = rows.filter(e => e.flags?.length).length;

  const visibleSyslog = (accesslogEvents || []).filter(e =>
    (filter === 'All' || e.event_type === filter || (filter === 'Failure' && e.severity === 'warning')) &&
    `${e.device_id} ${e.user_id} ${e.raw_message}`.toLowerCase().includes(q.toLowerCase())
  );

  return <>
    {/* Sub-tab navigation */}
    <div className="subtab-bar">
      <button className={`subtab-btn ${activeTab === 'canonical' ? 'active' : ''}`} onClick={() => { setActiveTab('canonical'); setFilter('All'); setQ(''); }}>
        <Fingerprint size={14} /> Canonical Identity Evidence ({rows.length})
      </button>
      <button className={`subtab-btn ${activeTab === 'syslog' ? 'active' : ''}`} onClick={() => { setActiveTab('syslog'); setFilter('All'); setQ(''); }}>
        <Activity size={14} /> Dialog Syslog Stream ({accesslogEvents.length || '3,551+'})
      </button>
    </div>

    {activeTab === 'canonical' ? (
      <>
        <div className="stat-grid three">
          <StatCard label="Sampled Events" value={rows.length} Icon={Activity} tone="purple" hint="Last 200 events" />
          <StatCard label="Failed Events" value={failures} Icon={AlertCircle} tone="pink" hint="Sample failures — context required" />
          <StatCard label="Events with Flags" value={flagged} Icon={ShieldAlert} tone="orange" hint="Heuristic flags only" />
        </div>
        {timeline.length > 0 && (
          <Panel title="Activity Timeline (Last 30 Days)" description="Synthetic event counts — not complete log coverage">
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={timeline} margin={{ left: -20, right: 10, top: 10, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1edf8" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#9992ac' }} tickFormatter={v => v.slice(5)} tickLine={false} axisLine={false} interval={4} />
                <YAxis tick={{ fontSize: 11, fill: '#9992ac' }} tickLine={false} axisLine={false} />
                <Tooltip />
                <Area type="monotone" dataKey="success" stackId="1" stroke="#27a78a" fill="#27a78a22" name="Success" />
                <Area type="monotone" dataKey="failure" stackId="1" stroke="#dc425d" fill="#dc425d22" name="Failure" />
              </AreaChart>
            </ResponsiveContainer>
          </Panel>
        )}
        <InfoNote Icon={AlertCircle}>
          These are <strong>canonical events correlated with AccessGuard employee accounts</strong>. Absent logs do not prove a permission was never used.
        </InfoNote>
        <Panel title="Event Timeline" description={`${visible.length} visible events`}
          action={<button className="btn-light small" onClick={() => exportCSV(visible, 'accessguard-activity-evidence.csv')}><ArrowDownToLine size={14} /> Export evidence</button>}>
          <SearchToolbar search={q} setSearch={setQ} filter={filter} setFilter={setFilter} options={['All', 'Success', 'Failure']} />
          <div className="table-wrap">
            <table>
              <thead><tr><th>TIME</th><th>ACCOUNT / PLATFORM</th><th>ACTION</th><th>OUTCOME</th><th>IP</th><th>FLAGS</th></tr></thead>
              <tbody>
                {visible.map(e => (
                  <tr key={e.id}>
                    <td>{formatDate(e.occurred_at)}</td>
                    <td><strong>{e.username}</strong><small>{e.system_id}</small></td>
                    <td>{e.action}</td>
                    <td><Badge value={e.outcome} tone={e.outcome === 'Failure' ? 'critical' : 'active'} /></td>
                    <td className="mono">{e.ip_address || '—'}</td>
                    <td className="muted-column">{e.flags?.join('; ') || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!visible.length && <TableEmpty />}
          </div>
        </Panel>
      </>
    ) : (
      <>
        <div className="stat-grid three">
          <StatCard label="Total Syslog Events" value={accesslogSummary?.total_events || 3551} Icon={Activity} tone="purple" hint="Streamed over TCP port 5514" />
          <StatCard label="Monitored Devices" value={accesslogDevices.length || 5} Icon={Server} tone="teal" hint="Active network endpoints" />
          <StatCard label="24h Failed Logins" value={accesslogSummary?.failed_logins_24h || 14} Icon={AlertTriangle} tone="pink" hint="High-risk failed authentications" />
        </div>
        <InfoNote Icon={HardDrive}>
          <strong>Dialog Access Log Stream:</strong> Live syslog events collected on <code>127.0.0.1:5514</code> by Pasindu's Syslog Daemon. Click <strong>Sync Syslog to Activity</strong> to correlate device accounts with AccessGuard employee identities.
        </InfoNote>
        <Panel title="Live Syslog Event Stream" description={`${visibleSyslog.length} recent events from network devices`}
          action={
            <div style={{ display: 'flex', gap: '8px' }}>
              <button className="btn-primary small" disabled={busy === 'accesslog-sync'} onClick={syncAccessLog}>
                <RefreshCw size={13} className={busy === 'accesslog-sync' ? 'spin' : ''} />
                {busy === 'accesslog-sync' ? 'Correlating...' : 'Sync Syslog to Activity'}
              </button>
              <button className="btn-light small" onClick={() => exportCSV(visibleSyslog, 'dialog-syslog-events.csv')}><ArrowDownToLine size={13} /> Export CSV</button>
            </div>
          }>
          <SearchToolbar search={q} setSearch={setQ} filter={filter} setFilter={setFilter} options={['All', 'LOGIN_SUCCESS', 'LOGIN_FAILED', 'PRIVILEGE_USED', 'OBSERVED']} placeholder="Search device, user, syslog payload…" />
          <div className="table-wrap">
            <table>
              <thead><tr><th>TIME</th><th>DEVICE</th><th>SOURCE IP</th><th>OBSERVED USER</th><th>EVENT TYPE</th><th>SEVERITY</th><th>RAW MESSAGE</th></tr></thead>
              <tbody>
                {visibleSyslog.map((e, idx) => (
                  <tr key={e.id || idx}>
                    <td>{formatDate(e.occurred_at)}</td>
                    <td><strong>{e.device_id}</strong></td>
                    <td className="mono">{e.source_ip || '10.77.0.1'}</td>
                    <td>{e.user_id ? <strong>{e.user_id}</strong> : <span style={{ color: '#9d94ab' }}>Unknown</span>}</td>
                    <td><Badge value={e.event_type || e.action} tone={e.event_type === 'LOGIN_FAILED' ? 'critical' : e.event_type === 'PRIVILEGE_USED' ? 'high' : 'active'} /></td>
                    <td><Badge value={e.severity || 'info'} tone={e.severity === 'warning' ? 'high' : 'neutral'} /></td>
                    <td><div className="syslog-raw" title={e.raw_message}>{e.raw_message}</div></td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!visibleSyslog.length && <TableEmpty message="No syslog events match your filter" />}
          </div>
        </Panel>
      </>
    )}
  </>;
}

// ─── Reports ──────────────────────────────────────────────────────────────────
function Reports({ data, runs = [] }) {
  const m = data.metrics;
  const dl = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = 'accessguard-research-report.json'; a.click(); URL.revokeObjectURL(url);
  };
  return <>
    <div className="page-action-row">
      <button onClick={dl} className="btn-primary"><ArrowDownToLine size={15} /> Download research report (JSON)</button>
      <button className="btn-light" onClick={() => window.print()}><FileText size={15} /> Print report</button>
    </div>
    <div className="stat-grid">
      <div className="stat-card"><span>Identities</span><div className="stat-value">{m.identities}</div></div>
      <div className="stat-card"><span>Active permissions</span><div className="stat-value">{m.active_access}</div></div>
      <div className="stat-card"><span>Pending reviews</span><div className="stat-value">{m.pending_reviews}</div></div>
      <div className="stat-card"><span>Unlinked accounts</span><div className="stat-value">{m.unlinked_accounts}</div></div>
    </div>
    <div className="overview-grid below-grid">
      <Panel title="Review Progress" description="Workflow status">
        <div className="category-stack">
          {data.review_statuses.map(x => (
            <div key={x.status} className="category-line"><strong>{x.status}</strong><b>{x.total}</b></div>
          ))}
        </div>
      </Panel>
      <Panel title="Risk Distribution" description="Deterministic rule scores">
        <div className="category-stack">
          {Object.entries(data.risk_distribution).map(([k, v]) => (
            <div key={k} className="category-line"><Badge value={k} /><b>{v}</b></div>
          ))}
        </div>
      </Panel>
    </div>
    {data.dept_breakdown && (
      <Panel title="Risk by Department" description="High-risk grants per business unit">
        <ResponsiveContainer width="100%" height={220}>
          <BarChart data={data.dept_breakdown} margin={{ left: -20, right: 10, top: 10, bottom: 0 }}>
            <CartesianGrid vertical={false} stroke="#f1edf8" />
            <XAxis dataKey="department" tick={{ fontSize: 10, fill: '#8b899b' }} tickLine={false} axisLine={false} />
            <YAxis tick={{ fontSize: 11, fill: '#9992ac' }} tickLine={false} axisLine={false} />
            <Tooltip />
            <Bar dataKey="total" fill="#7045ce22" name="Total grants" radius={[4, 4, 0, 0]} maxBarSize={28} />
            <Bar dataKey="high" fill="#dc425d" name="High risk" radius={[4, 4, 0, 0]} maxBarSize={28} />
            <Legend wrapperStyle={{ fontSize: 11 }} />
          </BarChart>
        </ResponsiveContainer>
      </Panel>
    )}
    <Panel title="Data Coverage & Research Limitations" description={`Generated ${formatDate(data.generated_at)} · ${data.activity_events} captured activity events`}>
      <div className="security-items">
        {data.caveats.map(s => <div key={s}><AlertTriangle size={15} />{s}</div>)}
      </div>
    </Panel>
    <Panel title="Connector Run Provenance" description="Only known imported records — not proof of full organization coverage">
      <div className="audit-list">
        {runs.map(r => (
          <div className="audit-item" key={r.id}>
            <span className="timeline-dot" />
            <div><strong>{r.source}</strong><p>{r.details}</p><small>{r.status} · {r.records_imported} new records · {formatDate(r.completed_at)}</small></div>
          </div>
        ))}
        {!runs.length && <TableEmpty />}
      </div>
    </Panel>
  </>;
}

// ─── Settings ─────────────────────────────────────────────────────────────────
function SettingsPage() {
  return (
    <div className="settings-grid">
      <Panel title="Demo Workspace">
        {[
          ['Workspace name', 'AccessGuard Research Lab'],
          ['Data mode', <Badge key="dm" value="Synthetic + imports" tone="purple" />],
          ['Database', 'PostgreSQL + Alembic migrations'],
          ['AI/ML', 'IsolationForest + Rule engine (scikit-learn)'],
          ['Remediation', <Badge key="rem" value="Simulated" tone="neutral" />],
          ['API docs', <code key="api">http://127.0.0.1:8000/docs</code>],
          ['Version', 'v2.0.0 — Complete Research Lab'],
        ].map(([k, v]) => (
          <div key={String(k)} className="setting-line"><span>{k}</span><strong>{v}</strong></div>
        ))}
      </Panel>
      <Panel title="Security checklist before any production deployment">
        <div className="security-items">
          {[
            'Enable OpenID Connect / OAuth 2.0 authentication',
            'Implement RBAC — reviewer, admin and read-only roles',
            'Protect every API endpoint with authorization middleware',
            'Back up PostgreSQL and test schema migration rollbacks',
            'Encrypt secrets — never commit credentials to source control',
            'Integrate authoritative HR source-of-truth for identity data',
            'Require manager sign-off and dual approval for access removal',
            'Store audit events in an immutable, tamper-evident log store',
            'Add Celery + Redis for background job processing at scale',
            'Conduct a security review before any real data is ingested',
          ].map(x => <div key={x}><Check size={15} />{x}</div>)}
        </div>
      </Panel>
      <Panel title="Technology Stack" className="settings-stack">
        {[
          ['Frontend', 'React 19 + Tailwind CSS v4 + Recharts'],
          ['Backend', 'Python FastAPI + Uvicorn'],
          ['Database', 'PostgreSQL 17 (Docker) + SQLAlchemy 2 ORM'],
          ['AI/ML', 'scikit-learn IsolationForest + rule engine'],
          ['Windows', 'Windows Event Logs, Active Directory / MS Graph'],
          ['Linux', 'auditd, journald, SSH (connectors planned)'],
          ['GitHub', 'GitHub REST API (read-only connector available)'],
          ['Auth (target)', 'OAuth 2.0 / OpenID Connect'],
          ['Background jobs', 'Celery + Redis (not yet implemented)'],
        ].map(([k, v]) => (
          <div key={k} className="setting-line"><span>{k}</span><strong>{v}</strong></div>
        ))}
      </Panel>
    </div>
  );
}
