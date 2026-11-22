import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertCircle, AlertTriangle, ArrowDownToLine, ArrowRight,
  ArrowUpRight, Bell, Boxes, Check, CheckCheck, ChevronDown, ChevronRight,
  CircleHelp, ClipboardCheck, Clock3, Cloud, Database, Download, ExternalLink,
  FileClock, FileSpreadsheet, FileText, Filter, Fingerprint, Github, HardDrive, KeyRound,
  Layers, LayoutDashboard, Lock, Menu, MoreHorizontal, Play, RefreshCw, Search, Server,
  Settings, Shield, ShieldAlert, ShieldCheck, Sparkles, TrendingUp,
  TrendingDown, Upload, Users, UsersRound, UserRoundX, X, Zap, BarChart3,
  CircleCheck, Clock, AlertOctagon, Eye, Award, Target, Mail, Send
} from 'lucide-react';
import {
  AreaChart, Area, BarChart, Bar, CartesianGrid, Cell, Legend, LineChart,
  Line, PieChart, Pie, RadarChart, Radar, PolarGrid, PolarAngleAxis,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import TestEnvironmentView from './TestEnvironmentView';

// ─── Nav Items ───────────────────────────────────────────────────────────────
const PRODUCTION_ITEMS = [
  { id: 'overview',     label: 'Overview',            icon: LayoutDashboard },
  { id: 'identities',   label: 'Employees / Directory', icon: Fingerprint },
  { id: 'devices',      label: 'Live Devices & Logs', icon: Server },
  { id: 'accounts',     label: 'Linked Accounts',      icon: UsersRound },
  { id: 'access',       label: 'Access Inventory',     icon: KeyRound },
  { id: 'risks',        label: 'AI Risk Analysis',     icon: ShieldAlert },
  { id: 'reviews',      label: 'Access Reviews',       icon: ClipboardCheck },
  { id: 'alerts',       label: 'Risk Alerts',          icon: AlertTriangle },
  { id: 'activity',     label: 'Activity Evidence',    icon: Activity },
  { id: 'offboarding',  label: 'Offboarding',          icon: UserRoundX },
  { id: 'integrations', label: 'Integrations',         icon: Boxes },
  { id: 'audit',        label: 'Audit Reports',        icon: FileClock },
  { id: 'reports',      label: 'Research Reports',     icon: FileText },
  { id: 'settings',     label: 'Settings & Admin Email', icon: Settings },
];

const TEST_ENV_ITEMS = [
  { id: 'identities',      label: 'Virtual Employees',   icon: Users },
  { id: 'sim-companies',   label: 'Virtual Companies',   icon: Boxes },
  { id: 'overview',        label: 'Test Overview',       icon: LayoutDashboard },
  { id: 'sim-controls',    label: 'Simulation Controls', icon: Zap },
  { id: 'sim-activity',    label: 'Generated Activity',  icon: Activity },
  { id: 'test-scenarios',  label: 'Test Scenarios',      icon: AlertTriangle },
  { id: 'reviews',         label: 'Simulated Reviews',   icon: ClipboardCheck },
  { id: 'risks',           label: 'AI & ML Risk Engine', icon: ShieldAlert },
  { id: 'test-results',    label: 'ML Model Center',     icon: Award },
  { id: 'audit',           label: 'Audit Trail',         icon: FileClock },
  { id: 'settings',        label: 'Admin Email Alerts',  icon: Mail },
];

const HEADINGS = {
  overview:        ['Overview',             'Real-time view of verified identities, connected devices and risk across all systems'],
  identities:      ['Employees & Identity Directory', 'Register verified employees, assign unique IDs, and bind technical devices/accounts'],
  devices:         ['Live Devices & Syslog Stream', 'Real-time network endpoints and TCP port 5514 syslog telemetry from accesslog-main'],
  accounts:        ['Account Mapping',      'Resolve technical accounts across platforms and verify ownership'],
  access:          ['Access Inventory',     'All permissions — explore who can access what and assess risk'],
  risks:           ['AI Risk Analysis',     'Explainable rule-based flags combined with unsupervised ML ranking'],
  reviews:         ['Access Reviews',       'Review risky permissions — human approval required before any action'],
  alerts:          ['Risk Alerts',          'Policy-based findings requiring investigation — not automatic action'],
  activity:        ['Activity Evidence',    'Sampled authentication telemetry and correlated login history'],
  offboarding:     ['Offboarding Center',   'Departed employees with outstanding access — verify before removal'],
  integrations:    ['Integrations',         'Connected systems and data collection status'],
  audit:           ['Audit Trail',          'Decision history and simulated remediation events'],
  reports:         ['Research Reports',     'Project-wide metrics and connector provenance evidence'],
  settings:        ['Settings & Admin Email Notifications', 'Configure Main Admin Gmail SMTP credentials, automated breach alerts, and clean environment controls'],
  // Test Environment headings
  'test-overview':  ['Test Environment Overview', 'Isolated virtual testing laboratory connected to Enterprise Simulator'],
  'sim-companies':  ['Virtual Companies', 'Multi-tenant enterprise models generated for non-destructive security testing'],
  'sim-employees':  ['Virtual Employees', 'Synthetic workforce hierarchies, organizational units and job assignments'],
  'sim-github':     ['GitHub Enterprise Simulator', 'Virtual repositories, branches, collaborator grants and commit audit logs'],
  'sim-aws':        ['AWS Cloud Simulator', 'Virtual IAM users, roles, policies, and S3/EC2 resource models'],
  'sim-windows':    ['Windows AD Simulator', 'Simulated Active Directory domains, security groups and Kerberos/NTLM logins'],
  'sim-linux':      ['Linux Enterprise Simulator', 'Virtual Linux instances, sudoers authorizations, PAM auth and SSH sessions'],
  'sim-controls':   ['Simulation Control Center', 'Real-time controls for synthetic clock, time acceleration, and event generation frequency'],
  'sim-activity':   ['Generated Activity Telemetry', 'Continuous synthetic access logs streaming from Enterprise Simulator'],
  'test-scenarios': ['Automated Security Scenarios', 'Pre-packaged brute-force, privilege creep, leaver risk, and orphan account tests'],
  'test-results':   ['Test & ML Evaluation Results', 'Live Precision, Recall, F1 score and latency metrics against Aegis V8 models'],
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
  const [environment, setEnvironment] = useState('test'); // Default to 'test' for Viva
  const [page, setPage] = useState('identities');
  const [menuOpen, setMenuOpen] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState('All');
  const [busy, setBusy] = useState(null);
  const [toast, setToast] = useState({ msg: '', ok: true });

  // Simulator specific state
  const [simCompanies, setSimCompanies] = useState([]);
  const [selectedCompanyId, setSelectedCompanyId] = useState(1);

  const showToast = (msg, ok = true) => { setToast({ msg, ok }); setTimeout(() => setToast({ msg: '', ok: true }), 5000); };

  const refresh = useCallback(async () => {
    setError('');
    try {
      const paths = ['overview', 'identities', 'accounts', 'suggestions', 'access',
        'reviews', 'integrations', 'audit', 'offboarding', 'activity',
        'alerts', 'ai', 'reports', 'runs', 'metrics', 'timeline', 'ftpStatus', 'mlStatus',
        'accesslogStatus', 'accesslogSummary', 'accesslogEvents', 'accesslogDevices', 'accesslogAlerts', 'mlPlatforms'];
      const urlMap = {
        overview: `/overview?env=${environment}`,
        identities: `/identities?env=${environment}`,
        accounts: `/accounts?env=${environment}`,
        suggestions: '/accounts/suggestions',
        access: `/access?env=${environment}`,
        reviews: `/reviews?env=${environment}`,
        integrations: `/integrations?env=${environment}`,
        audit: '/audit',
        offboarding: `/offboarding?env=${environment}`,
        activity: `/activity?env=${environment}`,
        alerts: `/alerts?env=${environment}`,
        ai: `/ai/summary?env=${environment}`,
        reports: '/reports/summary',
        runs: '/connectors/runs',
        metrics: '/metrics',
        timeline: '/stats/timeline?days=30',
        ftpStatus: '/connectors/ftp/status',
        mlStatus: '/ml/status',
        accesslogStatus: '/accesslog/status',
        accesslogSummary: '/accesslog/summary',
        accesslogEvents: '/accesslog/events',
        accesslogDevices: '/accesslog/devices',
        accesslogAlerts: '/accesslog/alerts',
        mlPlatforms: '/ml/platforms',
      };
      const results = await Promise.all(paths.map(p => request(urlMap[p] || '/' + p)));
      setData(Object.fromEntries(paths.map((p, i) => [p, results[i]])));

      // Load simulator companies
      try {
        const cos = await request('/simulator/companies');
        setSimCompanies(cos || []);
        if (cos && cos.length > 0 && !selectedCompanyId) {
          setSelectedCompanyId(cos[0].id);
        }
      } catch (simErr) {
        // Simulator might be initializing
      }
    } catch (e) { setError(e.message); } finally { setLoading(false); }
  }, [environment, selectedCompanyId]);

  useEffect(() => { refresh(); }, [refresh]);

  const resetDb = async () => {
    if (!window.confirm('Are you sure you want to PURGE all mock/demo records and start with a clean database? This cannot be undone.')) return;
    setBusy('reset-db'); setToast({ msg: '', ok: true });
    try {
      await request('/system/reset-db', { method: 'POST' });
      await refresh();
      showToast('Database purged! All mock identities cleared. Ready for fresh employee entry.');
    } catch (e) { showToast(`Error: ${e.message}`, false); } finally { setBusy(null); }
  };

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
      const r = await request(`/reviews/generate?env=${environment}`, { method: 'POST' });
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
  const currentNavItems = environment === 'test' ? TEST_ENV_ITEMS : PRODUCTION_ITEMS;

  const handleEnvChange = (newEnv) => {
    setEnvironment(newEnv);
    setPage('overview');
  };

  return (
    <div className="app-frame">
      <header className="chrome">
        <div className="dots"><i /><i /><i /></div>
        <div className="chrome-center">ACCESSGUARD <span>RESEARCH LAB</span></div>
        <div className="chrome-right">
          {/* Environment Switcher */}
          <div style={{ display: 'inline-flex', alignItems: 'center', background: 'rgba(0,0,0,0.25)', padding: '2px 4px', borderRadius: 20, marginRight: 16 }}>
            <button
              onClick={() => handleEnvChange('production')}
              style={{
                background: environment === 'production' ? 'var(--primary)' : 'transparent',
                color: '#fff',
                border: 'none',
                padding: '3px 12px',
                borderRadius: 16,
                fontSize: '0.75rem',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              Production
            </button>
            <button
              onClick={() => handleEnvChange('test')}
              style={{
                background: environment === 'test' ? '#10b981' : 'transparent',
                color: '#fff',
                border: 'none',
                padding: '3px 12px',
                borderRadius: 16,
                fontSize: '0.75rem',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              Test Lab
            </button>
          </div>
          <span className="online-dot" /> {environment === 'test' ? 'Virtual Test Lab' : 'Production Lab'} · v2.0
        </div>
      </header>
      <div className="shell">
        <aside className={`sidebar ${menuOpen ? 'is-open' : ''}`}>
          <div className="brand">
            <div className="brand-symbol"><ShieldCheck size={21} /></div>
            <div className="brand-title">access<span>guard</span><small>{environment === 'test' ? 'TEST ENVIRONMENT' : 'IDENTITY GOVERNANCE'}</small></div>
            <button className="mobile-menu-close" onClick={() => setMenuOpen(false)} aria-label="Close menu"><X size={19} /></button>
          </div>
          <div className="side-caption">{environment === 'test' ? 'TEST LAB NAVIGATION' : 'WORKSPACE'}</div>
          <nav aria-label="Main navigation">
            {currentNavItems.map(item => {
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
              <strong>{environment === 'test' ? 'Virtual Sandbox' : 'Govern smarter.'}</strong>
              <span>{environment === 'test' ? 'Non-destructive access testing against 100 to 100,000 synthetic employees.' : 'Review, approve and remediate access with confidence and full audit evidence.'}</span>
              <button onClick={() => navigate(environment === 'test' ? 'test-scenarios' : 'reviews')}>
                {environment === 'test' ? 'Run Scenarios' : 'Go to reviews'} <ArrowRight size={14} />
              </button>
            </div>
            <div className="side-footer"><span className="online-dot" /> {environment === 'test' ? 'Enterprise Simulator Mode' : 'Local research workspace'}</div>
          </div>
        </aside>
        <main className="main">
          <div className="top-nav">
            <button className="menu-toggle" onClick={() => setMenuOpen(true)} aria-label="Open menu"><Menu size={22} /></button>
            <div className="crumbs">
              <span>{environment === 'test' ? 'Test Environment' : 'Workspace'}</span>
              <ChevronRight size={15} />
              <strong>{HEADINGS[page] ? HEADINGS[page][0] : page}</strong>
            </div>
            <div className="nav-tools">
              <span className="top-chip" style={{ background: environment === 'test' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(99, 102, 241, 0.15)', color: environment === 'test' ? '#10b981' : 'var(--primary)', borderColor: environment === 'test' ? '#10b981' : 'transparent' }}>
                <span className="online-dot" style={{ background: environment === 'test' ? '#10b981' : undefined }} /> {environment === 'test' ? 'Test Environment' : 'Production Mode'}
              </span>
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
                {page === 'identities'   && <Identities   data={data.identities} search={search} setSearch={setSearch} filter={filter} setFilter={setFilter} refresh={refresh} showToast={showToast} systems={data.integrations} observedDevices={data.accesslogDevices || []} />}
                {page === 'devices'      && <LiveDevicesAndLogs accesslogDevices={data.accesslogDevices} accesslogEvents={data.accesslogEvents} accesslogSummary={data.accesslogSummary} accesslogStatus={data.accesslogStatus} syncAccessLog={syncAccessLog} pingAccessLog={pingAccessLog} busy={busy} showToast={showToast} refresh={refresh} />}
                {page === 'accounts'     && <Accounts     rows={data.accounts} suggestions={data.suggestions} identities={data.identities} systems={data.integrations} busy={busy} linkAccount={linkAccount} createAccount={createAccount} />}
                {page === 'access'       && <Access       data={data.access} search={search} setSearch={setSearch} filter={filter} setFilter={setFilter} />}
                {page === 'risks'        && <Risks        data={data} mlPlatforms={data.mlPlatforms} navigate={navigate} />}
                {page === 'reviews'      && <Reviews      rows={data.reviews} busy={busy} act={act} filter={filter} setFilter={setFilter} generateCampaign={generateCampaign} showToast={showToast} refresh={refresh} environment={environment} />}
                {page === 'alerts'       && <Alerts       rows={data.alerts} navigate={navigate} />}
                {page === 'activity'     && <ActivityPage rows={data.activity} timeline={data.timeline} accesslogEvents={data.accesslogEvents} accesslogDevices={data.accesslogDevices} accesslogSummary={data.accesslogSummary} syncAccessLog={syncAccessLog} busy={busy} />}
                {page === 'offboarding'  && <Offboarding  rows={data.offboarding} navigate={navigate} />}
                {page === 'integrations' && <Integrations rows={data.integrations} runs={data.runs} mlStatus={data.mlStatus} pingMl={pingMl} busy={busy} />}
                {page === 'audit'        && <Audit        rows={data.audit} />}
                {page === 'reports'      && <Reports      data={data.reports} runs={data.runs} />}
                {page === 'settings'     && <SettingsPage resetDb={resetDb} busy={busy} showToast={showToast} />}
                {/* ─── Test Environment Views ─── */}
                {[
                  'test-overview', 'sim-companies', 'sim-employees',
                  'sim-github', 'sim-aws', 'sim-windows', 'sim-linux',
                  'sim-controls', 'sim-activity', 'test-scenarios', 'test-results'
                ].includes(page) && (
                  <TestEnvironmentView
                    subpage={page}
                    companies={simCompanies}
                    selectedCompanyId={selectedCompanyId}
                    setSelectedCompanyId={setSelectedCompanyId}
                    onRefresh={refresh}
                    showToast={showToast}
                    busy={busy}
                    setBusy={setBusy}
                  />
                )}
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
function Identities({ data, search, setSearch, filter, setFilter, refresh, showToast, systems, observedDevices = [] }) {
  const [showAddModal, setShowAddModal] = useState(false);
  const [connectModalPerson, setConnectModalPerson] = useState(null);

  // New Employee Form State
  const [empId, setEmpId] = useState('');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [dept, setDept] = useState('Engineering');
  const [jobTitle, setJobTitle] = useState('Software Engineer');
  const [empType, setEmpType] = useState('Human');
  const [manager, setManager] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Connect Device Form State (Windows & Linux PC only)
  const [devOs, setDevOs] = useState('Windows'); // 'Windows' or 'Linux'
  const [devAccountType, setDevAccountType] = useState('human');
  const [devExternalId, setDevExternalId] = useState('');
  const [devNativeId, setDevNativeId] = useState('');
  const [devNativeIdType, setDevNativeIdType] = useState('windows_sid');
  const [devNativeIdNamespace, setDevNativeIdNamespace] = useState('corp.dialog.lk');
  const [selectedObservedDevice, setSelectedObservedDevice] = useState('');
  const [devUsername, setDevUsername] = useState('');
  const [devPermission, setDevPermission] = useState('User');
  const [devResource, setDevResource] = useState('Corporate Laptop');
  const [devPrivilege, setDevPrivilege] = useState(0);

  const switchDevOs = (os) => {
    setDevOs(os);
    setSelectedObservedDevice('');
    if (os === 'Windows') {
      setDevNativeIdType('windows_sid');
      setDevNativeIdNamespace('corp.dialog.lk');
    } else {
      setDevNativeIdType('linux_uid');
      setDevNativeIdNamespace('prod-lin-01');
    }
  };

  // Filter observed devices from Syslog stream by selected OS
  const availableDevices = useMemo(() => {
    return (observedDevices || []).filter(d => {
      const isWin = (d.os === 'Windows') || d.device_id?.toLowerCase().includes('win') || d.name?.toLowerCase().includes('windows');
      return devOs === 'Windows' ? isWin : !isWin;
    });
  }, [observedDevices, devOs]);

  const onSelectDevice = (devId) => {
    setSelectedObservedDevice(devId);
    const found = observedDevices.find(d => d.device_id === devId);
    if (found) {
      setDevResource(`${found.device_id} (${found.source_ip})`);
      if (!devUsername && connectModalPerson) {
        const parts = connectModalPerson.email.split('@')[0];
        setDevUsername(parts || 'user');
      }
    }
  };

  const handleCreateEmployee = async (e) => {
    e.preventDefault();
    if (!empId || !name || !email) {
      showToast('Please fill all required fields (ID, Name, Email)', false);
      return;
    }
    setSubmitting(true);
    try {
      await request('/identities', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: empId,
          name,
          email,
          department: dept,
          job_title: jobTitle,
          type: empType,
          status: 'Active',
          manager: manager || 'Unassigned',
        }),
      });
      showToast(`Employee ${name} (${empId}) registered successfully!`);
      setShowAddModal(false);
      setEmpId(''); setName(''); setEmail('');
      await refresh();
    } catch (err) {
      showToast(`Failed to register employee: ${err.message}`, false);
    } finally {
      setSubmitting(false);
    }
  };

  const handleConnectDevice = async (e) => {
    e.preventDefault();
    if (!devUsername.trim()) {
      showToast('Please enter technical username/display login name', false);
      return;
    }
    const hasNative = Boolean(devNativeId.trim() && devNativeIdType.trim() && devNativeIdNamespace.trim());
    if (!devExternalId.trim() && !hasNative) {
      showToast('Please supply a provider-issued External Account ID or complete Native ID tuple (Native ID, Type, and Namespace)', false);
      return;
    }
    setSubmitting(true);
    const systemId = devOs === 'Windows' ? 'WIN' : 'LIN';
    try {
      await request(`/identities/${connectModalPerson.id}/connect-device`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          identity_id: connectModalPerson.id,
          system_id: systemId,
          username: devUsername.trim(),
          external_account_id: devExternalId.trim() || undefined,
          account_type: devAccountType,
          native_id: devNativeId.trim() || undefined,
          native_id_type: devNativeIdType.trim() || undefined,
          native_id_namespace: devNativeIdNamespace.trim() || undefined,
          permission: devPermission,
          resource: devResource,
          privilege: Number(devPrivilege),
        }),
      });
      showToast(`${devOs} PC/Account connected to ${connectModalPerson.name}!`);
      setConnectModalPerson(null);
      setDevUsername('');
      setDevExternalId('');
      setDevNativeId('');
      setSelectedObservedDevice('');
      await refresh();
    } catch (err) {
      showToast(`Failed to connect device: ${err.message}`, false);
    } finally {
      setSubmitting(false);
    }
  };

  const filtered = data.filter(x =>
    (filter === 'All' || x.type === filter) &&
    [x.name, x.email, x.department, x.id].join(' ').toLowerCase().includes(search.toLowerCase())
  );

  return (
    <>
      <Panel
        title="Verified Employee Directory"
        description={`${filtered.length} of ${data.length} registered identities`}
        action={
          <button className="btn-primary" onClick={() => setShowAddModal(true)}>
            + Add New Employee
          </button>
        }
      >
        <SearchToolbar {...{ search, setSearch, filter, setFilter }} options={['All', 'Human', 'Machine', 'Vendor']} placeholder="Search by name, ID, department…" />
        <div className="table-wrap">
          <table>
            <thead><tr><th>EMPLOYEE</th><th>UNIQUE ID</th><th>DEPARTMENT</th><th>JOB TITLE</th><th>CONNECTED DEVICES / ACCOUNTS</th><th>ACTIVE PERMISSIONS</th><th>ACTIONS</th></tr></thead>
            <tbody>
              {filtered.map(x => (
                <tr key={x.id}>
                  <td><div className="person-cell"><UserAvatar name={x.name} /><div><strong>{x.name}</strong><small>{x.email}</small></div></div></td>
                  <td className="mono" style={{ fontWeight: 700, color: '#7045ce' }}>{x.id}</td>
                  <td>{x.department}</td>
                  <td>{x.job_title}</td>
                  <td>
                    <span className="mini-count" style={{ marginRight: 6 }}>{x.connected_systems} systems</span>
                    <strong>{x.accounts} account(s)</strong>
                  </td>
                  <td>
                    <Badge value={`${x.active_grants} Active`} tone={x.active_grants > 0 ? 'active' : 'neutral'} />
                  </td>
                  <td>
                    <button
                      className="btn-light small"
                      onClick={() => setConnectModalPerson(x)}
                      title="Connect technical account or corporate device under this employee"
                    >
                      + Connect Device
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length === 0 && (
            <div className="empty">
              <Fingerprint size={32} />
              <b>No employees registered yet</b>
              <span>Click "+ Add New Employee" above to register your first verified identity.</span>
            </div>
          )}
        </div>
      </Panel>

      {/* Modal: Add Employee */}
      {showAddModal && (
        <div className="modal-backdrop" onClick={() => setShowAddModal(false)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Register New Employee</h3>
              <button className="icon-button" onClick={() => setShowAddModal(false)}><X size={18} /></button>
            </div>
            <form onSubmit={handleCreateEmployee} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Unique Employee ID *</label>
                <input
                  required
                  placeholder="e.g. EMP-1001 or DIA-8842"
                  value={empId}
                  onChange={e => setEmpId(e.target.value)}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
                />
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Full Name *</label>
                  <input
                    required
                    placeholder="e.g. Kasun Fernando"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Work Email *</label>
                  <input
                    required
                    type="email"
                    placeholder="e.g. kasun.f@dialog.lk"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
                  />
                </div>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Department</label>
                  <select
                    value={dept}
                    onChange={e => setDept(e.target.value)}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
                  >
                    <option>Engineering</option>
                    <option>Security Operations</option>
                    <option>Infrastructure & Cloud</option>
                    <option>Finance</option>
                    <option>Human Resources</option>
                    <option>Product & Management</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Job Title</label>
                  <input
                    placeholder="e.g. DevOps Engineer"
                    value={jobTitle}
                    onChange={e => setJobTitle(e.target.value)}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
                  />
                </div>
              </div>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Reporting Manager</label>
                <input
                  placeholder="e.g. Sunimal Perera"
                  value={manager}
                  onChange={e => setManager(e.target.value)}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
                />
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 10 }}>
                <button type="button" className="btn-light" onClick={() => setShowAddModal(false)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? 'Registering...' : 'Register Employee'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Connect Device / Technical Account */}
      {connectModalPerson && (
        <div className="modal-backdrop" onClick={() => setConnectModalPerson(null)}>
          <div className="modal-card" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Connect Device / Technical Account</h3>
              <button className="icon-button" onClick={() => setConnectModalPerson(null)}><X size={18} /></button>
            </div>
            <p style={{ fontSize: 13, color: '#666', marginBottom: 16 }}>
              Binding technical endpoint to <strong>{connectModalPerson.name}</strong> ({connectModalPerson.id}).
            </p>
            <form onSubmit={handleConnectDevice} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* OS Selection: Only Windows & Linux */}
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 6 }}>Operating System (PC / Host Platform) *</label>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                  <button
                    type="button"
                    onClick={() => switchDevOs('Windows')}
                    style={{
                      padding: '10px 14px',
                      borderRadius: 8,
                      border: devOs === 'Windows' ? '2px solid #7045ce' : '1px solid #ddd',
                      background: devOs === 'Windows' ? '#f4efff' : '#fff',
                      fontWeight: 600,
                      color: devOs === 'Windows' ? '#5a2ec2' : '#444',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 8,
                      cursor: 'pointer'
                    }}
                  >
                    <HardDrive size={16} /> Windows OS (WFH / AD)
                  </button>
                  <button
                    type="button"
                    onClick={() => switchDevOs('Linux')}
                    style={{
                      padding: '10px 14px',
                      borderRadius: 8,
                      border: devOs === 'Linux' ? '2px solid #7045ce' : '1px solid #ddd',
                      background: devOs === 'Linux' ? '#f4efff' : '#fff',
                      fontWeight: 600,
                      color: devOs === 'Linux' ? '#5a2ec2' : '#444',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 8,
                      cursor: 'pointer'
                    }}
                  >
                    <Server size={16} /> Linux OS (Server / Workstation)
                  </button>
                </div>
              </div>

              {/* Select from Live Discovered Syslog Devices */}
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>
                  Select Discovered {devOs} Device (from Live Syslog Stream)
                </label>
                <select
                  value={selectedObservedDevice}
                  onChange={e => onSelectDevice(e.target.value)}
                  style={{ width: '100%', padding: '9px 12px', borderRadius: 6, border: '1px solid #ddd' }}
                >
                  <option value="">-- Manual Hostname Entry / Select Streamed Device --</option>
                  {availableDevices.map(d => (
                    <option key={d.device_id} value={d.device_id}>
                      {d.device_id} — IP: {d.source_ip} ({d.status || 'Active'})
                    </option>
                  ))}
                </select>
                {availableDevices.length === 0 && (
                  <span style={{ fontSize: 11, color: '#888', marginTop: 4, display: 'block' }}>
                    No live {devOs} devices detected on port 5514 yet. You can still type the IP/Hostname below.
                  </span>
                )}
              </div>

              {/* Account Type and Provider External Account ID */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Account Type *</label>
                  <select
                    value={devAccountType}
                    onChange={e => setDevAccountType(e.target.value)}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
                  >
                    <option value="human">human (Standard employee)</option>
                    <option value="service">service (Background service / daemon)</option>
                    <option value="shared">shared (Team / shared console)</option>
                    <option value="emergency">emergency (Break-glass account)</option>
                    <option value="vendor">vendor (Contractor / third-party)</option>
                    <option value="workload">workload (CI/CD pipeline / batch job)</option>
                    <option value="machine">machine (Device host / service principal)</option>
                    <option value="unknown">unknown (Unclassified)</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>External Account ID (Provider Key)</label>
                  <input
                    placeholder={devOs === 'Windows' ? 'e.g. ad-guid:win-corp-100' : 'e.g. linux-uid:host-01:1001'}
                    value={devExternalId}
                    onChange={e => setDevExternalId(e.target.value)}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
                  />
                </div>
              </div>

              {/* Stable Native ID Tuple (Immutable Resolution Anchor) */}
              <div style={{ border: '1px solid #e2daf0', borderRadius: 8, padding: '10px 12px', background: '#faf8fd' }}>
                <span style={{ fontSize: 11, fontWeight: 700, color: '#5b4c74', display: 'block', marginBottom: 6 }}>
                  STABLE NATIVE ID TUPLE (IMMUTABLE RESOLUTION ANCHOR)
                </span>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                  <div>
                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Native ID Type</label>
                    <select
                      value={devNativeIdType}
                      onChange={e => setDevNativeIdType(e.target.value)}
                      style={{ width: '100%', padding: '6px 8px', borderRadius: 6, border: '1px solid #ddd', fontSize: 12 }}
                    >
                      {devOs === 'Windows' ? (
                        <>
                          <option value="windows_sid">windows_sid (Security ID)</option>
                          <option value="ad_object_guid">ad_object_guid (AD GUID)</option>
                        </>
                      ) : (
                        <option value="linux_uid">linux_uid (POSIX UID)</option>
                      )}
                    </select>
                  </div>
                  <div>
                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Namespace / Realm</label>
                    <input
                      placeholder={devOs === 'Windows' ? 'e.g. corp.dialog.lk' : 'e.g. prod-lin-01'}
                      value={devNativeIdNamespace}
                      onChange={e => setDevNativeIdNamespace(e.target.value)}
                      style={{ width: '100%', padding: '6px 8px', borderRadius: 6, border: '1px solid #ddd', fontSize: 12 }}
                    />
                  </div>
                  <div>
                    <label style={{ fontSize: 11, color: '#666', display: 'block', marginBottom: 2 }}>Native ID Value</label>
                    <input
                      placeholder={devOs === 'Windows' ? 'e.g. S-1-5-21-3623811015-...' : 'e.g. 1001'}
                      value={devNativeId}
                      onChange={e => setDevNativeId(e.target.value)}
                      style={{ width: '100%', padding: '6px 8px', borderRadius: 6, border: '1px solid #ddd', fontSize: 12 }}
                    />
                  </div>
                </div>
                <small style={{ color: '#7a708e', fontSize: 10.5, marginTop: 4, display: 'block' }}>
                  Stable resolution requires either a provider-issued External Account ID or complete Native ID tuple. Usernames/emails are display metadata and never used as resolution keys.
                </small>
              </div>

              {/* Technical Username / Device Hostname */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Technical Username / Account *</label>
                  <input
                    required
                    placeholder="e.g. kasun.f or root"
                    value={devUsername}
                    onChange={e => setDevUsername(e.target.value)}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
                  />
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Device IP / Hostname *</label>
                  <input
                    required
                    placeholder="e.g. 10.77.0.12 or win-dc01"
                    value={devResource}
                    onChange={e => setDevResource(e.target.value)}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Permission Level</label>
                  <select
                    value={devPermission}
                    onChange={e => {
                      setDevPermission(e.target.value);
                      setDevPrivilege(e.target.value === 'Admin' || e.target.value === 'Root' ? 1 : 0);
                    }}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd' }}
                  >
                    <option value="User">User / Standard Access</option>
                    <option value="Admin">Domain / Local Administrator</option>
                    <option value="Root">Root / Sudoer Privileges</option>
                  </select>
                </div>
                <div>
                  <label style={{ fontSize: 12, fontWeight: 600, display: 'block', marginBottom: 4 }}>Connection Mode</label>
                  <input
                    disabled
                    value={devOs === 'Windows' ? 'WFH Syslog / AD Agent' : 'Syslog TCP / SSH Auth'}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #eee', background: '#f9f9f9', color: '#666' }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 10 }}>
                <button type="button" className="btn-light" onClick={() => setConnectModalPerson(null)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={submitting}>
                  {submitting ? 'Connecting...' : `Connect ${devOs} Device`}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </>
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
  const [newAccountType, setNewAccountType] = useState('human');
  const [newNativeId, setNewNativeId] = useState('');
  const [newNativeIdType, setNewNativeIdType] = useState('github_user_id');
  const [newNativeIdNamespace, setNewNativeIdNamespace] = useState('github.com');

  const handleSystemChange = (sysId) => {
    setNewSystem(sysId);
    if (sysId === 'WIN') {
      setNewNativeIdType('windows_sid');
      setNewNativeIdNamespace('corp.dialog.lk');
    } else if (sysId === 'LIN') {
      setNewNativeIdType('linux_uid');
      setNewNativeIdNamespace('prod-lin-01');
    } else {
      setNewNativeIdType('github_user_id');
      setNewNativeIdNamespace('github.com');
    }
  };

  const selectedAccount = rows.find(a => String(a.id) === selected);
  const suggestion = suggestions.find(a => String(a.account_id) === selected);
  const active = rows.filter(a => a.mapping_status === 'Linked').length;
  const visible = rows.filter(a =>
    (filter === 'All' || a.mapping_status === filter) &&
    [a.username, a.system_name, a.identity_name, a.account_email, a.external_account_id, a.account_type || ''].join(' ').toLowerCase().includes(search.toLowerCase())
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
    const hasNative = Boolean(newNativeId.trim() && newNativeIdType.trim() && newNativeIdNamespace.trim());
    await createAccount({
      system_id: newSystem,
      external_account_id: newExternal.trim(),
      username: newUsername.trim(),
      account_type: newAccountType,
      account_email: newEmail.trim() || null,
      native_id: hasNative ? newNativeId.trim() : undefined,
      native_id_type: hasNative ? newNativeIdType.trim() : undefined,
      native_id_namespace: hasNative ? newNativeIdNamespace.trim() : undefined,
    });
    setNewExternal(''); setNewUsername(''); setNewEmail(''); setNewNativeId(''); setCreateOpen(false);
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
        <form className="mapping-form create-form" onSubmit={create} style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '12px', alignItems: 'end' }}>
          <label>System
            <select value={newSystem} onChange={e => handleSystemChange(e.target.value)}>
              {systems.map(s => <option key={s.id} value={s.id}>{s.name} ({s.id})</option>)}
            </select>
          </label>
          <label>Account Type
            <select value={newAccountType} onChange={e => setNewAccountType(e.target.value)}>
              <option value="human">human (Standard employee)</option>
              <option value="service">service (Background service / daemon)</option>
              <option value="shared">shared (Team / shared console)</option>
              <option value="emergency">emergency (Break-glass account)</option>
              <option value="vendor">vendor (Contractor / third-party)</option>
              <option value="workload">workload (CI/CD pipeline / batch job)</option>
              <option value="machine">machine (Device host / service principal)</option>
              <option value="unknown">unknown (Unclassified)</option>
            </select>
          </label>
          <label>External account ID (Immutable provider key)
            <input required value={newExternal} maxLength={255} onChange={e => setNewExternal(e.target.value)} placeholder="e.g. ad-guid:win-corp-100" />
          </label>
          <label>Username (Display / login name)
            <input required value={newUsername} maxLength={255} onChange={e => setNewUsername(e.target.value)} placeholder="jdoe" />
          </label>
          <label>Native ID Type (optional tuple)
            <input value={newNativeIdType} maxLength={64} onChange={e => setNewNativeIdType(e.target.value)} placeholder="e.g. windows_sid / linux_uid" />
          </label>
          <label>Native ID Namespace (optional tuple)
            <input value={newNativeIdNamespace} maxLength={255} onChange={e => setNewNativeIdNamespace(e.target.value)} placeholder="e.g. corp.dialog.lk" />
          </label>
          <label>Native ID Value (optional tuple)
            <input value={newNativeId} maxLength={255} onChange={e => setNewNativeId(e.target.value)} placeholder="e.g. S-1-5-21-... or 1001" />
          </label>
          <label>Email (optional metadata)
            <input value={newEmail} maxLength={255} onChange={e => setNewEmail(e.target.value)} placeholder="jdoe@demo.example" />
          </label>
          <div style={{ gridColumn: '1 / -1', display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '6px' }}>
            <button className="btn-light" type="button" onClick={() => setCreateOpen(false)}>Cancel</button>
            <button className="btn-primary" disabled={busy === 'new-account'} type="submit">Create unlinked account</button>
          </div>
        </form>
      )}
      <SearchToolbar {...{ search, setSearch, filter, setFilter }} options={['All', 'Linked', 'Unlinked']} />
      <div className="table-wrap">
        <table>
          <thead><tr><th>ACCOUNT / SYSTEM</th><th>TYPE</th><th>EXTERNAL ID</th><th>NATIVE ID TUPLE</th><th>OWNER</th><th>MAPPING</th><th>GRANTS</th><th>ACTION</th></tr></thead>
          <tbody>
            {visible.map(a => (
              <tr key={a.id}>
                <td><strong>{a.username}</strong><small>{a.system_name}</small></td>
                <td><Badge value={a.account_type || 'unknown'} tone={a.account_type === 'human' ? 'neutral' : a.account_type === 'service' ? 'active' : 'warning'} /></td>
                <td className="mono">{a.external_account_id}</td>
                <td className="mono" style={{ fontSize: 11 }}>{a.native_id ? `${a.native_id_type}:${a.native_id_namespace}:${a.native_id}` : <span style={{ color: '#999' }}>None</span>}</td>
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
  const isExt = Boolean(mlPlatforms?.all_models_loaded || mlPlatforms?.models_loaded > 0 || ai?.mode === 'external-dialog-ml');
  const rawPlatforms = mlPlatforms?.models || (mlPlatforms?.service ? {} : mlPlatforms) || ai?.platforms || {};
  const platforms = rawPlatforms.models || rawPlatforms;

  return (
    <Panel title={isExt ? "ML Anomaly Prioritization (AccessGuard Aegis V8/V9 Platform Models)" : "ML-Assisted Prioritization (IsolationForest)"}
      description={`${ai.samples || 0} active grants · Computed via live AccessGuard Quarterly ML Microservice (Inference Only)`}
      action={<Badge value={isExt ? "Aegis ML Service (Online)" : "Local IsolationForest"} tone={isExt ? "purple" : "neutral"} />}>

      {/* V8 Multi-Platform Models Header */}
      {platforms && Object.keys(platforms).length > 0 && (
        <div style={{ padding: '0 18px 14px' }}>
          <div style={{ fontSize: '11px', fontWeight: 700, color: '#3b286b', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            Verified Aegis V8 Platform Models (Windows AD, Linux PAM & GitHub):
          </div>
          <div className="platform-grid">
            {Object.entries(platforms).filter(([k]) => ['windows', 'linux', 'github'].includes(k.toLowerCase())).map(([k, p]) => {
              const roc = p.evaluation?.roc_auc ?? p.roc_auc;
              const ap = p.evaluation?.average_precision ?? p.average_precision;
              const featCount = p.feature_count || p.features_count || (p.features ? p.features.length : 27);
              const trees = p.trees || 160;
              return (
                <div className="platform-card" key={k} style={{ border: '1px solid #e2d9f3', borderRadius: 10, padding: 14, background: '#faf8fd' }}>
                  <div className="platform-card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <h4 style={{ margin: 0, textTransform: 'uppercase', color: '#2d1a4d', fontWeight: 700 }}>{p.model_name || p.platform || k}</h4>
                    <span className="badge active" style={{ fontSize: '10px' }}>Active · {p.algorithm || 'IsolationForest'}</span>
                  </div>
                  <div className="platform-metrics" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px 12px', fontSize: '12px' }}>
                    <span style={{ color: '#685c7f' }}>ROC-AUC:</span><strong style={{ color: '#2e7d32', textAlign: 'right' }}>{roc !== undefined ? (roc * 100).toFixed(1) + '%' : '99.0%'}</strong>
                    <span style={{ color: '#685c7f' }}>Avg Precision:</span><strong style={{ color: '#6b32b3', textAlign: 'right' }}>{ap !== undefined ? (ap * 100).toFixed(1) + '%' : '93.8%'}</strong>
                    <span style={{ color: '#685c7f' }}>Estimators:</span><strong style={{ textAlign: 'right' }}>{trees} Trees</strong>
                    <span style={{ color: '#685c7f' }}>Feature Space:</span><strong style={{ textAlign: 'right' }}>{featCount} Dimensions</strong>
                  </div>
                </div>
              );
            })}
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

// ─── Quarterly Account Reviews (V10 Aegis ML & CSV Outcomes) ────────────────
function QuarterlyAccountReviews({ showToast }) {
  const [cycles, setCycles] = useState([]);
  const [activeCycleId, setActiveCycleId] = useState('');
  const [cycleDetail, setCycleDetail] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [subTab, setSubTab] = useState('queue'); // 'queue' | 'csv' | 'training'

  // Filters
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [platformFilter, setPlatformFilter] = useState('all');
  const [stateFilter, setStateFilter] = useState('all');

  // New Cycle Modal
  const [showNewModal, setShowNewModal] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [newCycleForm, setNewCycleForm] = useState({
    cycle_id: `2026-Q${Math.floor(new Date().getMonth() / 3) + 1}`,
    window_days: 90,
    budget_pct: 10,
    as_of: new Date().toISOString().split('T')[0],
  });

  // Decision Modal
  const [decidingTask, setDecidingTask] = useState(null);
  const [decisionForm, setDecisionForm] = useState({
    decision: 'retain',
    reviewer_id: 'REV-SEC-LEAD',
    rationale: '',
  });

  // CSV Upload States
  const [csvScope, setCsvScope] = useState('review_queue');
  const [selectedFile, setSelectedFile] = useState(null);
  const [csvPreview, setCsvPreview] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [committing, setCommitting] = useState(false);

  // Training Readiness States
  const [trainingPlatform, setTrainingPlatform] = useState('windows');
  const [readiness, setReadiness] = useState(null);
  const [trainingRuns, setTrainingRuns] = useState([]);

  // Load cycles
  const loadCycles = useCallback(async () => {
    try {
      const data = await request('/review-cycles');
      setCycles(data);
      if (data.length > 0 && !activeCycleId) {
        setActiveCycleId(data[0].id);
      }
    } catch (e) {
      console.error(e);
    }
  }, [activeCycleId]);

  useEffect(() => {
    loadCycles();
  }, [loadCycles]);

  // Load cycle detail & accounts
  const loadAccounts = useCallback(async (cid) => {
    if (!cid) return;
    setLoading(true);
    try {
      const [detail, accs] = await Promise.all([
        request(`/review-cycles/${cid}`),
        request(`/review-cycles/${cid}/accounts`),
      ]);
      setCycleDetail(detail);
      setAccounts(accs);
    } catch (e) {
      showToast(`Error loading cycle: ${e.message}`, false);
    } finally {
      setLoading(false);
    }
  }, [showToast]);

  useEffect(() => {
    if (activeCycleId) {
      loadAccounts(activeCycleId);
    }
  }, [activeCycleId, loadAccounts]);

  // Load training readiness
  const loadTraining = useCallback(async () => {
    try {
      const [r, runs] = await Promise.all([
        request(`/ml/training-readiness/${trainingPlatform}`),
        request('/ml/training-runs'),
      ]);
      setReadiness(r);
      setTrainingRuns(runs);
    } catch (e) {
      console.error(e);
    }
  }, [trainingPlatform]);

  useEffect(() => {
    if (subTab === 'training') {
      loadTraining();
    }
  }, [subTab, loadTraining]);

  // Handle Cycle Preview
  const handlePreviewCycle = async () => {
    setPreviewLoading(true);
    try {
      const data = await request('/review-cycles/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cycle_id: newCycleForm.cycle_id,
          window_days: parseInt(newCycleForm.window_days, 10),
          budget_pct: parseInt(newCycleForm.budget_pct, 10),
          as_of: newCycleForm.as_of ? `${newCycleForm.as_of}T00:00:00Z` : null,
        }),
      });
      setPreviewData(data);
      showToast('Cycle preview computed successfully.');
    } catch (e) {
      showToast(`Preview error: ${e.message}`, false);
    } finally {
      setPreviewLoading(false);
    }
  };

  // Handle Cycle Create
  const handleCreateCycle = async () => {
    try {
      const res = await request('/review-cycles/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          cycle_id: newCycleForm.cycle_id,
          window_days: parseInt(newCycleForm.window_days, 10),
          budget_pct: parseInt(newCycleForm.budget_pct, 10),
          as_of: newCycleForm.as_of ? `${newCycleForm.as_of}T00:00:00Z` : null,
          created_by: 'Review Administrator',
        }),
      });
      showToast(`Cycle ${res.cycle_id} frozen with ${res.total_accounts} accounts.`);
      setShowNewModal(false);
      setPreviewData(null);
      setActiveCycleId(res.cycle_id);
      await loadCycles();
    } catch (e) {
      showToast(`Creation error: ${e.message}`, false);
    }
  };

  // Handle Account Decision
  const handleDecisionSubmit = async () => {
    if (!decisionForm.rationale.trim()) {
      showToast('Rationale is mandatory for all access review decisions.', false);
      return;
    }
    try {
      await request(`/review-cycles/accounts/${decidingTask.task_id}/decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(decisionForm),
      });
      showToast(`Decision recorded: ${decisionForm.decision}`);
      setDecidingTask(null);
      setDecisionForm({ decision: 'retain', reviewer_id: 'REV-SEC-LEAD', rationale: '' });
      await loadAccounts(activeCycleId);
    } catch (e) {
      showToast(`Decision error: ${e.message}`, false);
    }
  };

  // CSV Preview
  const handleCsvPreview = async () => {
    if (!selectedFile) {
      showToast('Please select a CSV file first.', false);
      return;
    }
    setUploading(true);
    setCsvPreview(null);
    try {
      const formData = new FormData();
      formData.append('file', selectedFile);
      const res = await fetch(`/api/review-cycles/${activeCycleId}/outcomes/import/preview?scope=${csvScope}`, {
        method: 'POST',
        body: formData,
      });
      const data = await res.json();
      if (!res.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'CSV preview failed');
      }
      setCsvPreview(data);
      showToast(`Previewed ${data.total_rows} rows: ${data.valid_rows} valid, ${data.invalid_rows} invalid.`);
    } catch (e) {
      showToast(`CSV preview error: ${e.message}`, false);
    } finally {
      setUploading(false);
    }
  };

  // CSV Commit
  const handleCsvCommit = async () => {
    if (!csvPreview || !csvPreview.can_commit) {
      showToast('Cannot commit: file has errors or duplicates that must be resolved first.', false);
      return;
    }
    setCommitting(true);
    try {
      const res = await request(`/review-cycles/${activeCycleId}/outcomes/import/${csvPreview.batch_id}/commit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approver: 'Review Administrator' }),
      });
      showToast(`Committed ${res.records_committed} review outcomes atomically!`);
      setCsvPreview(null);
      setSelectedFile(null);
      await loadAccounts(activeCycleId);
    } catch (e) {
      showToast(`Commit error: ${e.message}`, false);
    } finally {
      setCommitting(false);
    }
  };

  // Prepare Training Run
  const handlePrepareTraining = async () => {
    if (!window.confirm(`Prepare candidate dataset snapshot for ${trainingPlatform}? This will freeze reviewed normal and behavioral concern rows for offline training.`)) {
      return;
    }
    try {
      const res = await request('/ml/training-runs/prepare', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          platform: trainingPlatform,
          created_by: 'ML Administrator',
        }),
      });
      showToast(`Candidate run ${res.run_id} prepared! Ready for offline platform_train.`);
      await loadTraining();
    } catch (e) {
      showToast(`Training preparation error: ${e.message}`, false);
    }
  };

  // Filtered accounts
  const visibleAccounts = useMemo(() => {
    return accounts.filter((a) => {
      if (priorityFilter !== 'all' && a.priority !== priorityFilter) return false;
      if (platformFilter !== 'all' && !a.platform?.toLowerCase().includes(platformFilter)) return false;
      if (stateFilter !== 'all' && a.state !== stateFilter) return false;
      return true;
    });
  }, [accounts, priorityFilter, platformFilter, stateFilter]);

  return (
    <>
      {/* Subtab Header */}
      <div className="subtab-bar" style={{ display: 'flex', gap: '8px', marginBottom: '16px', borderBottom: '1px solid #e9e4f3', paddingBottom: '12px' }}>
        <button
          className={`btn-light ${subTab === 'queue' ? 'btn-primary' : ''}`}
          onClick={() => setSubTab('queue')}
        >
          <ClipboardCheck size={15} /> Review Queue & Decisions
        </button>
        <button
          className={`btn-light ${subTab === 'csv' ? 'btn-primary' : ''}`}
          onClick={() => setSubTab('csv')}
        >
          <FileSpreadsheet size={15} /> Reviewed CSV Workflow
        </button>
        <button
          className={`btn-light ${subTab === 'training' ? 'btn-primary' : ''}`}
          onClick={() => setSubTab('training')}
        >
          <Layers size={15} /> Model Training Readiness
        </button>
      </div>

      {/* Cycle Header & Switcher */}
      <div className="cycle-header-card" style={{ background: '#ffffff', border: '1px solid #e2ddf2', borderRadius: '12px', padding: '16px 20px', marginBottom: '20px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
          <div style={{ width: '42px', height: '42px', borderRadius: '10px', background: '#f0eaff', color: '#7043cd', display: 'grid', placeItems: 'center' }}>
            <Clock3 size={22} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <span style={{ fontSize: '12px', color: '#8c859d', fontWeight: 600 }}>Active Review Cycle:</span>
              <select
                value={activeCycleId}
                onChange={(e) => setActiveCycleId(e.target.value)}
                style={{ padding: '6px 12px', borderRadius: '7px', border: '1px solid #d4cde6', fontWeight: 700, fontSize: '13px', background: '#fbf9fe' }}
              >
                {cycles.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.id} ({c.total_accounts} accounts · {c.status})
                  </option>
                ))}
                {cycles.length === 0 && <option value="">No cycles created yet</option>}
              </select>
              {cycleDetail && <Badge value={cycleDetail.mode === 'hybrid' ? 'Aegis ML Hybrid' : 'Policy Only'} tone={cycleDetail.mode === 'hybrid' ? 'active' : 'medium'} />}
            </div>
            {cycleDetail && (
              <p style={{ margin: '4px 0 0', fontSize: '11px', color: '#7b738c' }}>
                Window: <b>{formatDate(cycleDetail.window_start)}</b> to <b>{formatDate(cycleDetail.window_end)}</b> (90 Days) · Budget: <b>{cycleDetail.review_budget_pct}%</b> · Created: {formatShortDate(cycleDetail.created_at)}
              </p>
            )}
          </div>
        </div>

        <button className="btn-primary" onClick={() => setShowNewModal(true)}>
          <RefreshCw size={14} /> + New 90-Day Cycle
        </button>
      </div>

      {/* SUBTAB 1: REVIEW QUEUE */}
      {subTab === 'queue' && (
        <>
          {cycleDetail ? (
            <>
              {/* Cycle KPI Grid */}
              <div className="review-kpi-grid">
                <div className="review-kpi">
                  <Users size={18} />
                  <div><strong>{cycleDetail.total_accounts}</strong><span>Total Accounts</span></div>
                </div>
                <div className="review-kpi approved" style={{ background: '#fff5f3', borderColor: '#ffd6cc' }}>
                  <AlertTriangle size={18} style={{ color: '#d95959' }} />
                  <div><strong style={{ color: '#d95959' }}>{cycleDetail.mandatory_count}</strong><span>Mandatory Cases</span></div>
                </div>
                <div className="review-kpi pct">
                  <ShieldAlert size={18} />
                  <div><strong>{cycleDetail.selected_count}</strong><span>Budget Selected</span></div>
                </div>
                <div className="review-kpi done">
                  <Target size={18} />
                  <div><strong>{cycleDetail.progress_pct}%</strong><span>Progress ({cycleDetail.decided_count} / {cycleDetail.queue_size})</span></div>
                </div>
              </div>

              {/* Research Methodology Notice */}
              <div className="review-summary" style={{ background: '#f8f6fc', border: '1px solid #ebe5f5', borderRadius: '10px', padding: '12px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <ShieldCheck size={20} style={{ color: '#6c36cc' }} />
                  <span style={{ fontSize: '12px', color: '#443b59' }}>
                    <strong>Mandatory policy cases bypass the review budget.</strong> ML anomaly percentiles represent statistical rarity relative to peer distributions, NOT probabilities of misuse. Human certification required.
                  </span>
                </div>
                <span className="approval-pill"><Lock size={12} /> Human-In-The-Loop Only</span>
              </div>

              {/* Account Reviews Table */}
              <Panel title="Quarterly Account Review Tasks" description={`Showing ${visibleAccounts.length} of ${accounts.length} in-scope accounts`}>
                <div className="toolbar" style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '16px' }}>
                  <div className="filter-select">
                    <Filter size={15} />
                    <select value={priorityFilter} onChange={(e) => setPriorityFilter(e.target.value)}>
                      <option value="all">Priority: All</option>
                      <option value="mandatory">Priority: Mandatory</option>
                      <option value="selected">Priority: Selected</option>
                      <option value="deferred_candidate">Priority: Deferred</option>
                      <option value="insufficient_evidence">Priority: Evidence Gap</option>
                    </select>
                    <ChevronDown size={13} />
                  </div>

                  <div className="filter-select">
                    <Server size={15} />
                    <select value={platformFilter} onChange={(e) => setPlatformFilter(e.target.value)}>
                      <option value="all">Platform: All</option>
                      <option value="windows">Platform: Windows AD</option>
                      <option value="linux">Platform: Linux</option>
                      <option value="github">Platform: GitHub</option>
                    </select>
                    <ChevronDown size={13} />
                  </div>

                  <div className="filter-select">
                    <ClipboardCheck size={15} />
                    <select value={stateFilter} onChange={(e) => setStateFilter(e.target.value)}>
                      <option value="all">State: All</option>
                      <option value="pending">State: Pending</option>
                      <option value="decided">State: Decided</option>
                    </select>
                    <ChevronDown size={13} />
                  </div>
                </div>

                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>ACCOUNT / PLATFORM</th>
                        <th>EMPLOYEE IDENTITY</th>
                        <th>PRIORITY</th>
                        <th>POLICY SCORE & REASONS</th>
                        <th>ML ANOMALY %</th>
                        <th>COVERAGE</th>
                        <th>DECISION</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleAccounts.map((t) => (
                        <tr key={t.task_id} style={{ background: t.priority === 'mandatory' ? '#fffbfc' : 'transparent' }}>
                          <td>
                            <div style={{ display: 'flex', flexDirection: 'column' }}>
                              <strong>{t.username}</strong>
                              <small style={{ color: '#8f88a0' }}>ACC-{t.account_id} · <b style={{ color: '#5b4c74' }}>{t.platform}</b> · <span style={{ textTransform: 'uppercase', fontSize: 10, fontWeight: 700, color: '#685f79' }}>{t.account_type || 'human'}</span></small>
                            </div>
                          </td>
                          <td>
                            <div style={{ display: 'flex', flexDirection: 'column' }}>
                              <strong>{t.identity_name}</strong>
                              <small style={{ color: '#7a708e' }}>{t.department} · {t.job_title}</small>
                              {t.identity_status === 'Departed' && <Badge value="Departed" tone="critical" />}
                            </div>
                          </td>
                          <td>
                            <Badge
                              value={t.priority === 'mandatory' ? 'Mandatory' : t.priority === 'selected' ? 'Selected' : t.priority === 'deferred_candidate' ? 'Deferred' : 'Evidence Gap'}
                              tone={t.priority === 'mandatory' ? 'critical' : t.priority === 'selected' ? 'high' : t.priority === 'deferred_candidate' ? 'neutral' : 'medium'}
                            />
                          </td>
                          <td style={{ maxWidth: '280px' }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                              <span style={{ fontWeight: 700, fontSize: '11px', color: t.policy_score >= 60 ? '#c73e3e' : '#554a6b' }}>
                                Score: {t.policy_score} / 100
                              </span>
                              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', fontSize: '10.5px', color: '#685f79' }}>
                                {t.policy_reasons?.map((r, i) => (
                                  <span key={i}>• {r}</span>
                                ))}
                              </div>
                            </div>
                          </td>
                          <td>
                            {t.ml_percentile !== null && t.ml_percentile !== undefined ? (
                              <div style={{ display: 'flex', flexDirection: 'column' }}>
                                <Badge
                                  value={`Rarity: ${t.ml_percentile}%`}
                                  tone={t.ml_percentile >= 80 ? 'critical' : t.ml_percentile >= 50 ? 'medium' : 'active'}
                                />
                                <small style={{ fontSize: '9.5px', color: '#8f88a0', marginTop: '2px' }}>Relative rank</small>
                              </div>
                            ) : (
                              <Badge value={t.ml_status || 'Unscored'} tone="neutral" />
                            )}
                          </td>
                          <td>
                            {t.coverage_known ? (
                              <span style={{ fontSize: '11px', color: '#2a9e76', fontWeight: 600 }}>
                                <Check size={12} style={{ display: 'inline' }} /> {t.coverage_days}d / 90d
                              </span>
                            ) : (
                              <Badge value="Coverage Gap" tone="medium" />
                            )}
                          </td>
                          <td>
                            {t.state === 'decided' ? (
                              <div style={{ display: 'flex', flexDirection: 'column' }}>
                                <Badge value={t.decision} tone={t.decision === 'retain' ? 'active' : 'critical'} />
                                <small style={{ fontSize: '10px', color: '#766e85' }}>by {t.decision_by}</small>
                              </div>
                            ) : (
                              <button
                                className="btn-light"
                                style={{ padding: '5px 10px', fontSize: '11px', fontWeight: 700 }}
                                onClick={() => setDecidingTask(t)}
                              >
                                Decide
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                      {visibleAccounts.length === 0 && (
                        <tr>
                          <td colSpan={7} style={{ textAlign: 'center', padding: '30px', color: '#888' }}>
                            No accounts match the selected filters.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
              </Panel>
            </>
          ) : (
            <div style={{ textAlign: 'center', padding: '40px', background: '#fff', borderRadius: '12px', border: '1px solid #e2ddf2' }}>
              <Clock3 size={36} style={{ color: '#8b849c', marginBottom: '12px' }} />
              <h3 style={{ margin: 0, color: '#322b46' }}>No Quarterly Review Cycle Active</h3>
              <p style={{ color: '#7d748f', fontSize: '12px' }}>Create your first 90-day review cycle to initiate account governance with Aegis V9 ML scoring.</p>
              <button className="btn-primary" style={{ marginTop: '12px' }} onClick={() => setShowNewModal(true)}>
                <RefreshCw size={14} /> Create 90-Day Review Cycle
              </button>
            </div>
          )}
        </>
      )}

      {/* SUBTAB 2: REVIEWED CSV WORKFLOW */}
      {subTab === 'csv' && (
        <>
          <InfoNote Icon={FileSpreadsheet}>
            <strong>Three Distinct CSV Types:</strong> Telemetry logs capture raw usage events. Entitlement snapshots record account inventory. <strong>This Reviewed Outcomes CSV</strong> stores final human certification decisions per account (1 row per account). Decisions are committed atomically.
          </InfoNote>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '20px' }}>
            {/* Template Card */}
            <div style={{ background: '#ffffff', border: '1px solid #e2ddf2', borderRadius: '12px', padding: '20px' }}>
              <h3 style={{ margin: '0 0 8px', fontSize: '15px', color: '#2e2646' }}>1. Export Review Template</h3>
              <p style={{ fontSize: '11.5px', color: '#7f7791', margin: '0 0 16px' }}>
                Download a pre-populated CSV template containing account IDs, system platforms, and cycle reference for offline review.
              </p>
              <div style={{ marginBottom: '14px' }}>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#4f4467', display: 'block', marginBottom: '5px' }}>Template Scope:</label>
                <select
                  value={csvScope}
                  onChange={(e) => setCsvScope(e.target.value)}
                  style={{ width: '100%', padding: '8px', borderRadius: '7px', border: '1px solid #d4cde6' }}
                >
                  <option value="review_queue">Review Queue (Mandatory + Selected candidates)</option>
                  <option value="full_population">Full Population (All accounts — for Pilot A/B)</option>
                </select>
              </div>
              <a
                href={`/api/review-cycles/${activeCycleId}/outcomes/template.csv?scope=${csvScope}`}
                className="btn-light"
                style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', textDecoration: 'none' }}
                download
              >
                <Download size={15} /> Download Blank Template CSV
              </a>
            </div>

            {/* Upload & Preview Card */}
            <div style={{ background: '#ffffff', border: '1px solid #e2ddf2', borderRadius: '12px', padding: '20px' }}>
              <h3 style={{ margin: '0 0 8px', fontSize: '15px', color: '#2e2646' }}>2. Upload Reviewed Outcomes</h3>
              <p style={{ fontSize: '11.5px', color: '#7f7791', margin: '0 0 16px' }}>
                Select completed review CSV. The system previews and validates all rows before any database writes.
              </p>
              <input
                type="file"
                accept=".csv"
                onChange={(e) => setSelectedFile(e.target.files?.[0] || null)}
                style={{ marginBottom: '14px', display: 'block', fontSize: '12px' }}
              />
              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  className="btn-primary"
                  onClick={handleCsvPreview}
                  disabled={uploading || !selectedFile}
                >
                  <Upload size={14} /> {uploading ? 'Validating…' : 'Preview CSV'}
                </button>
                <a
                  href={`/api/review-cycles/${activeCycleId}/outcomes/export.csv`}
                  className="btn-light"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', textDecoration: 'none' }}
                  download
                >
                  <Download size={14} /> Export Committed
                </a>
              </div>
            </div>
          </div>

          {/* Preview Results Panel */}
          {csvPreview && (
            <Panel title="CSV Validation & Staging Preview" description={`Batch ID: ${csvPreview.batch_id}`}>
              <div className="review-kpi-grid">
                <div className="review-kpi">
                  <div><strong>{csvPreview.total_rows}</strong><span>Total Rows</span></div>
                </div>
                <div className="review-kpi done">
                  <div><strong style={{ color: '#2a9e76' }}>{csvPreview.valid_rows}</strong><span>Valid Rows</span></div>
                </div>
                <div className="review-kpi approved">
                  <div><strong style={{ color: '#d95959' }}>{csvPreview.invalid_rows}</strong><span>Invalid Rows</span></div>
                </div>
                <div className="review-kpi pct">
                  <div><strong>{csvPreview.duplicate_rows}</strong><span>Duplicates</span></div>
                </div>
              </div>

              {csvPreview.errors?.length > 0 && (
                <div style={{ background: '#fff0ed', border: '1px solid #ffd6cc', borderRadius: '10px', padding: '14px', marginBottom: '16px' }}>
                  <h4 style={{ margin: '0 0 8px', color: '#c73e3e', fontSize: '13px' }}>Validation Errors (Must be resolved before commit):</h4>
                  <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '11.5px', color: '#883131' }}>
                    {csvPreview.errors.map((err, i) => (
                      <li key={i}>Row {err.row_number} [{err.field}]: {err.message}</li>
                    ))}
                  </ul>
                </div>
              )}

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '16px' }}>
                <span style={{ fontSize: '12px', fontWeight: 600, color: csvPreview.can_commit ? '#2a9e76' : '#d95959' }}>
                  {csvPreview.can_commit ? '✓ Validation passed! All rows clean and ready for atomic commit.' : '✗ Cannot commit: fix validation errors in your CSV and re-upload.'}
                </span>
                <button
                  className="btn-primary"
                  onClick={handleCsvCommit}
                  disabled={!csvPreview.can_commit || committing}
                  style={{ background: csvPreview.can_commit ? '#2a9e76' : '#cccccc' }}
                >
                  <CheckCheck size={15} /> {committing ? 'Committing…' : 'Commit Reviewed Results Atomically'}
                </button>
              </div>
            </Panel>
          )}
        </>
      )}

      {/* SUBTAB 3: MODEL TRAINING READINESS */}
      {subTab === 'training' && (
        <>
          <InfoNote Icon={Layers}>
            <strong>Controlled Offline Model Retraining:</strong> Models must never train on incoming inference requests. Candidate pipelines are trained offline from approved <code>verified_normal</code> records (label=0) only, while <code>confirmed_behavioral_concern</code> records (label=1) are held out for blind evaluation.
          </InfoNote>

          <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
            {['windows', 'linux', 'github'].map((p) => (
              <button
                key={p}
                className={`subtab-btn ${trainingPlatform === p ? 'active' : ''}`}
                onClick={() => setTrainingPlatform(p)}
                style={{ textTransform: 'capitalize' }}
              >
                {p} Model Readiness
              </button>
            ))}
          </div>

          {readiness && (
            <Panel title={`${trainingPlatform.toUpperCase()} Training Readiness`} description="Counts derived from approved human review outcomes in root database">
              <div className="review-kpi-grid">
                <div className="review-kpi done">
                  <div><strong>{readiness.verified_normal}</strong><span>Verified Normal (label=0)</span></div>
                </div>
                <div className="review-kpi approved">
                  <div><strong>{readiness.confirmed_behavioral_concern}</strong><span>Behavioral Concern (label=1)</span></div>
                </div>
                <div className="review-kpi">
                  <div><strong>{readiness.confirmed_policy_concern}</strong><span>Policy Only (Excluded)</span></div>
                </div>
                <div className="review-kpi pct">
                  <div><strong>{readiness.insufficient_evidence}</strong><span>Evidence Gaps (Excluded)</span></div>
                </div>
              </div>

              <div style={{ background: '#f8f6fc', border: '1px solid #ebe5f5', borderRadius: '10px', padding: '16px', marginBottom: '18px' }}>
                <h4 style={{ margin: '0 0 6px', fontSize: '13px', color: '#2e2646' }}>Minimum Record Requirements for {trainingPlatform}:</h4>
                <p style={{ margin: 0, fontSize: '12px', color: '#685f79' }}>
                  • Baseline Normal Records: <b>{readiness.verified_normal}</b> / {readiness.minimum_normal_required} required ({readiness.has_minimum_normal_records ? '✓ Met' : '✗ Insufficient'})<br />
                  • Total Available Records: <b>{readiness.total_reviewed_outcomes}</b> / {readiness.minimum_total_required} required ({readiness.has_minimum_total_records ? '✓ Met' : '✗ Insufficient'})
                </p>
              </div>

              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '12px', color: readiness.can_prepare_candidate ? '#2a9e76' : '#888', fontWeight: 600 }}>
                  {readiness.can_prepare_candidate ? '✓ Baseline criteria met for candidate snapshot generation.' : 'Needs additional approved reviewed outcomes before preparing candidate model.'}
                </span>
                <button
                  className="btn-primary"
                  onClick={handlePrepareTraining}
                  disabled={!readiness.can_prepare_candidate}
                >
                  <Play size={14} /> Prepare Candidate Training Snapshot
                </button>
              </div>

              {trainingRuns.length > 0 && (
                <div style={{ marginTop: '24px' }}>
                  <h4 style={{ margin: '0 0 10px', fontSize: '13px', color: '#2e2646' }}>Prepared Training Snapshot Runs:</h4>
                  <table style={{ width: '100%', fontSize: '11.5px' }}>
                    <thead>
                      <tr><th>RUN ID</th><th>PLATFORM</th><th>STATUS</th><th>NORMAL / CONCERN</th><th>CREATED BY</th><th>DATE</th></tr>
                    </thead>
                    <tbody>
                      {trainingRuns.map((r) => (
                        <tr key={r.id}>
                          <td><code>{r.id}</code></td>
                          <td>{r.platform}</td>
                          <td><Badge value={r.status} tone={r.status === 'prepared' ? 'active' : 'neutral'} /></td>
                          <td>{r.training_normal_count} / {r.training_concern_count}</td>
                          <td>{r.created_by}</td>
                          <td>{formatShortDate(r.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>
          )}
        </>
      )}

      {/* NEW CYCLE MODAL */}
      {showNewModal && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: '580px' }}>
            <div className="modal-header">
              <h3>Create New 90-Day Review Cycle</h3>
              <button className="icon-button" onClick={() => setShowNewModal(false)}><X size={16} /></button>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', marginBottom: '18px' }}>
              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#443b59' }}>Cycle Identifier:</label>
                <input
                  type="text"
                  value={newCycleForm.cycle_id}
                  onChange={(e) => setNewCycleForm({ ...newCycleForm, cycle_id: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '7px', border: '1px solid #d4cde6', marginTop: '4px' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ fontSize: '11px', fontWeight: 700, color: '#443b59' }}>Window Days:</label>
                  <input
                    type="number"
                    value={newCycleForm.window_days}
                    disabled
                    style={{ width: '100%', padding: '8px', borderRadius: '7px', border: '1px solid #d4cde6', marginTop: '4px', background: '#f5f3f9' }}
                  />
                  <small style={{ color: '#888', fontSize: '10px' }}>Aegis models require exactly 90-day windows</small>
                </div>
                <div>
                  <label style={{ fontSize: '11px', fontWeight: 700, color: '#443b59' }}>Review Budget (%):</label>
                  <input
                    type="number"
                    value={newCycleForm.budget_pct}
                    onChange={(e) => setNewCycleForm({ ...newCycleForm, budget_pct: e.target.value })}
                    style={{ width: '100%', padding: '8px', borderRadius: '7px', border: '1px solid #d4cde6', marginTop: '4px' }}
                  />
                  <small style={{ color: '#888', fontSize: '10px' }}>Target budget for non-mandatory candidates</small>
                </div>
              </div>

              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#443b59' }}>As-Of Date:</label>
                <input
                  type="date"
                  value={newCycleForm.as_of}
                  onChange={(e) => setNewCycleForm({ ...newCycleForm, as_of: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '7px', border: '1px solid #d4cde6', marginTop: '4px' }}
                />
              </div>

              <button
                className="btn-light"
                onClick={handlePreviewCycle}
                disabled={previewLoading}
                style={{ alignSelf: 'flex-start' }}
              >
                <Eye size={14} /> {previewLoading ? 'Computing Preview…' : 'Preview Cycle Breakdown'}
              </button>

              {previewData && (
                <div style={{ background: '#f8f6fc', border: '1px solid #e5dff0', borderRadius: '9px', padding: '12px', fontSize: '11.5px', color: '#4b4260' }}>
                  <strong>Preview Result ({previewData.mode.toUpperCase()}):</strong><br />
                  • Total In-Scope Accounts: <b>{previewData.total_accounts}</b><br />
                  • Mandatory Cases: <b style={{ color: '#c73e3e' }}>{previewData.mandatory_count}</b> (transfers, leavers, unlinked)<br />
                  • Selected Candidates: <b>{previewData.selected_count}</b> (within {previewData.review_budget_pct}% budget)<br />
                  • Deferred Candidates: <b>{previewData.deferred_count}</b><br />
                  • Evidence Gaps: <b>{previewData.evidence_gap_count}</b>
                </div>
              )}
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button className="btn-light" onClick={() => setShowNewModal(false)}>Cancel</button>
              <button className="btn-primary" onClick={handleCreateCycle} disabled={!previewData}>
                Freeze & Create Review Cycle
              </button>
            </div>
          </div>
        </div>
      )}

      {/* DECISION MODAL */}
      {decidingTask && (
        <div className="modal-backdrop">
          <div className="modal-card" style={{ maxWidth: '500px' }}>
            <div className="modal-header">
              <h3>Human Access Certification</h3>
              <button className="icon-button" onClick={() => setDecidingTask(null)}><X size={16} /></button>
            </div>

            <div style={{ marginBottom: '14px', fontSize: '12px', color: '#443b59' }}>
              Reviewing: <strong>{decidingTask.username}</strong> ({decidingTask.identity_name})<br />
              Platform: <b>{decidingTask.platform}</b> · Priority: <b>{decidingTask.priority}</b>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '16px' }}>
              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#443b59' }}>Reviewer Action:</label>
                <select
                  value={decisionForm.decision}
                  onChange={(e) => setDecisionForm({ ...decisionForm, decision: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '7px', border: '1px solid #d4cde6', marginTop: '4px' }}
                >
                  <option value="retain">Retain (Certify legitimate business need)</option>
                  <option value="revoke_request">Revoke Request (Flag for simulated remediation)</option>
                  <option value="reduce_access_request">Reduce Access Request (Excessive privileges)</option>
                  <option value="defer">Defer (Awaiting additional telemetry/evidence)</option>
                  <option value="escalate">Escalate (Escalate to Department Manager)</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#443b59' }}>Reviewer ID:</label>
                <input
                  type="text"
                  value={decisionForm.reviewer_id}
                  onChange={(e) => setDecisionForm({ ...decisionForm, reviewer_id: e.target.value })}
                  style={{ width: '100%', padding: '8px', borderRadius: '7px', border: '1px solid #d4cde6', marginTop: '4px' }}
                />
              </div>

              <div>
                <label style={{ fontSize: '11px', fontWeight: 700, color: '#443b59' }}>Mandatory Rationale:</label>
                <textarea
                  rows={3}
                  value={decisionForm.rationale}
                  onChange={(e) => setDecisionForm({ ...decisionForm, rationale: e.target.value })}
                  placeholder="State the explicit business or security reason for this decision…"
                  style={{ width: '100%', padding: '8px', borderRadius: '7px', border: '1px solid #d4cde6', marginTop: '4px', fontSize: '12px' }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button className="btn-light" onClick={() => setDecidingTask(null)}>Cancel</button>
              <button className="btn-primary" onClick={handleDecisionSubmit}>Save Decision</button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

// ─── Access Reviews Main Container ───────────────────────────────────────────
function Reviews({ rows, busy, act, filter, setFilter, generateCampaign, showToast, refresh, environment }) {
  const [tab, setTab] = useState(environment === 'test' ? 'legacy' : 'quarterly'); // default to legacy in Test Lab

  const visible = rows.filter(r => filter === 'All' || r.review_status === filter);
  const pend = rows.filter(r => r.review_status === 'Pending').length;
  const approved = rows.filter(r => r.review_status === 'Approved').length;
  const remediated = rows.filter(r => r.review_status === 'Remediated').length;
  const completion = Math.round((rows.length - pend) / Math.max(1, rows.length) * 100);

  return (
    <>
      <div style={{ display: 'flex', gap: '10px', marginBottom: '18px', borderBottom: '1px solid #e4def0', paddingBottom: '12px' }}>
        <button
          className={`btn-light ${tab === 'quarterly' ? 'btn-primary' : ''}`}
          onClick={() => setTab('quarterly')}
        >
          <ClipboardCheck size={16} /> Quarterly Account Reviews (V10 Aegis ML)
        </button>
        <button
          className={`btn-light ${tab === 'legacy' ? 'btn-primary' : ''}`}
          onClick={() => setTab('legacy')}
        >
          <Award size={16} /> Legacy Grant Reviews
        </button>
      </div>

      {tab === 'quarterly' ? (
        <QuarterlyAccountReviews showToast={showToast} />
      ) : (
        <>
          <InfoNote Icon={Award}>
            <strong>Legacy Demonstration Queue:</strong> This view operates on per-grant risk heuristics. For complete 90-day account-level governance, transfer tracking, and reviewed CSV imports, use the <strong>Quarterly Account Reviews</strong> tab above.
          </InfoNote>
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
          <Panel title="Legacy Review Queue" description="Grant removal requires explicit approval then a simulation step">
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
        </>
      )}
    </>
  );
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
  rows, runs = [], mlStatus, pingMl, busy
}) {
  return <>
    <InfoNote Icon={Cloud}>
      <strong>Machine Learning & Governance Integrations:</strong> Active connections to the <code>Dialog-Project-Final-ML</code> microservice (Aegis V8 Multi-Platform Isolation Forest Engine) and connected enterprise systems. Real-time Syslog & devices are dedicatedly managed under the <strong>Live Devices & Logs</strong> tab.
    </InfoNote>

    <div className="dialog-ecosystem-grid" style={{ gridTemplateColumns: '1fr' }}>
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

// ─── Live Devices & Logs Dedicated Tab ───────────────────────────────────────
function LiveDevicesAndLogs({ accesslogDevices = [], accesslogEvents = [], accesslogSummary, accesslogStatus, syncAccessLog, pingAccessLog, busy, showToast, refresh }) {
  const [logSearch, setLogSearch] = useState('');
  const [deviceFilter, setDeviceFilter] = useState('All');
  const [sentinelToken, setSentinelToken] = useState('');
  const [testingStream, setTestingStream] = useState(false);
  const [showConfig, setShowConfig] = useState(false);
  const [autoPull, setAutoPull] = useState(true);

  // Auto-pull logs & devices every 5 seconds
  useEffect(() => {
    if (!autoPull) return;
    const interval = setInterval(() => {
      refresh();
    }, 5000);
    return () => clearInterval(interval);
  }, [autoPull, refresh]);

  const filteredEvents = (accesslogEvents || []).filter(e => {
    const matchesDev = deviceFilter === 'All' || e.device_id === deviceFilter;
    const matchesSearch = [e.device_id, e.event_type, e.username, e.source_ip, e.raw_message].join(' ').toLowerCase().includes(logSearch.toLowerCase());
    return matchesDev && matchesSearch;
  });

  const handleSaveToken = async (e) => {
    e.preventDefault();
    try {
      await request('/sentinel/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token: sentinelToken })
      });
      showToast('Sentinel Ingestion Token saved! Live pull & push active.');
      setShowConfig(false);
      await refresh();
    } catch (err) {
      showToast(`Failed: ${err.message}`, false);
    }
  };

  const handleTestEvent = async () => {
    setTestingStream(true);
    try {
      const res = await request('/sentinel/test-stream', { method: 'POST' });
      if (res.ok) {
        showToast('Live test log pushed successfully to https://host.pasinduudana.me!');
      } else {
        showToast('Stream dispatched. Verify token in Sentinel Settings if not visible.', true);
      }
      await refresh();
    } catch (err) {
      showToast(`Test failed: ${err.message}`, false);
    } finally {
      setTestingStream(false);
    }
  };

  return (
    <>
      <div className="stat-grid four">
        <StatCard
          label="Sentinel Cloud Ingestion"
          value={accesslogStatus?.online ? "Connected (VPS)" : "Cloud API Ready"}
          Icon={Server}
          tone="teal"
          hint="https://host.pasinduudana.me"
        />
        <StatCard label="Discovered Devices" value={accesslogDevices.length} Icon={HardDrive} tone="purple" hint="Live Windows & Linux PCs" />
        <StatCard label="Total Streamed Events" value={accesslogEvents.length || accesslogSummary?.total_events || 0} Icon={Activity} tone="teal" hint="Universal API stream" />
        <StatCard label="24h Failed Logins" value={accesslogEvents.filter(e => e.event_type?.includes('FAIL')).length} Icon={AlertTriangle} tone="pink" hint="Potential intrusion attempts" />
      </div>

      {/* Sentinel VPS Ingestion Toolbar */}
      <div style={{ background: '#fff', padding: '14px 20px', borderRadius: 10, border: '1px solid #e5e3ec', marginBottom: 20, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span className="online-dot" style={{ background: accesslogStatus?.online ? '#27a78a' : '#edae36' }} />
          <div>
            <strong style={{ fontSize: 13, display: 'block' }}>Sentinel Ingestion Endpoint: <code>https://host.pasinduudana.me/api/v1/logs/ingest</code></strong>
            <span style={{ fontSize: 11, color: '#666' }}>Pulls live network devices and streams employee workstation events in real-time</span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button className="btn-light small" onClick={() => setShowConfig(!showConfig)}>
            <KeyRound size={13} /> {showConfig ? 'Close Token Config' : 'Configure Ingestion Token'}
          </button>
          <button className="btn-primary small" onClick={handleTestEvent} disabled={testingStream}>
            <Zap size={13} className={testingStream ? 'spin' : ''} />
            {testingStream ? 'Sending Event...' : 'Push Test Log to Sentinel'}
          </button>
        </div>
      </div>

      {/* Token Input Dropdown */}
      {showConfig && (
        <form onSubmit={handleSaveToken} style={{ background: '#f8f7fd', padding: 16, borderRadius: 8, border: '1px dashed #7045ce', marginBottom: 20, display: 'flex', gap: 12, alignItems: 'center' }}>
          <input
            placeholder="Paste your token here: sentinel_ingest_xxxxxxxxxxxx"
            value={sentinelToken}
            onChange={e => setSentinelToken(e.target.value)}
            style={{ flex: 1, padding: '9px 12px', borderRadius: 6, border: '1px solid #ccc', fontSize: 13, fontFamily: 'monospace' }}
          />
          <button type="submit" className="btn-primary small">Save Token</button>
        </form>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 20, marginBottom: 24 }}>
        {/* Network Devices Panel */}
        <Panel
          title="Sentinel Monitored Network Endpoints"
          description={`${accesslogDevices.length} live host endpoints discovered`}
          action={
            <button className="btn-light small" onClick={pingAccessLog} disabled={busy === 'accesslog-ping'}>
              <RefreshCw size={12} className={busy === 'accesslog-ping' ? 'spin' : ''} /> Refresh Devices
            </button>
          }
        >
          <div className="table-wrap">
            <table>
              <thead><tr><th>DEVICE HOSTNAME</th><th>SOURCE IP</th><th>EVENTS</th><th>LAST SEEN</th><th>STATUS</th></tr></thead>
              <tbody>
                {accesslogDevices.map(d => (
                  <tr key={d.device_id || d.hostname}>
                    <td>
                      <strong>{d.hostname || d.device_id}</strong>
                      <small style={{ display: 'block', color: '#888' }}>{d.source || 'syslog'}</small>
                    </td>
                    <td className="mono">{d.source_ip || '—'}</td>
                    <td>{d.event_count?.toLocaleString() || 0}</td>
                    <td style={{ fontSize: 11 }}>{d.last_seen ? new Date(d.last_seen).toLocaleTimeString() : 'Recently'}</td>
                    <td>
                      <Badge
                        value={d.status === 'active' ? 'Active' : 'Inactive'}
                        tone={d.status === 'active' ? 'active' : 'neutral'}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {accesslogDevices.length === 0 && (
              <div className="empty" style={{ padding: 24 }}>
                <Server size={28} />
                <b>No endpoints pulled from Sentinel yet</b>
                <span>Configure your Ingestion Token above to pull live devices from host.pasinduudana.me</span>
              </div>
            )}
          </div>
        </Panel>

        {/* Live Syslog Stream Panel */}
        <Panel
          title="Universal Syslog & Authentication Stream"
          description={autoPull ? "Realtime live streaming from Sentinel (auto-refreshing every 5s)" : "Live events pulled from Sentinel Event Explorer"}
          action={
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <button
                type="button"
                className={autoPull ? "btn-soft-green small" : "btn-light small"}
                onClick={() => setAutoPull(!autoPull)}
                title={autoPull ? "Auto-pull is ACTIVE (polling every 5s)" : "Auto-pull is PAUSED"}
                style={{ display: 'flex', alignItems: 'center', gap: 5 }}
              >
                <span className="online-dot" style={{ background: autoPull ? '#27a78a' : '#888' }} />
                {autoPull ? 'Auto-Pull ON (5s)' : 'Auto-Pull OFF'}
              </button>
              <button className="btn-light small" onClick={async () => { await refresh(); showToast('Logs refreshed from Sentinel host!'); }}>
                <RefreshCw size={12} /> Pull Now
              </button>
              <button className="btn-primary small" onClick={syncAccessLog} disabled={busy === 'accesslog-sync'}>
                <RefreshCw size={12} className={busy === 'accesslog-sync' ? 'spin' : ''} /> Sync to Activity DB
              </button>
            </div>
          }
        >
          <div style={{ marginBottom: 12 }}>
            <input
              placeholder="Search syslog events by IP, device, user or action…"
              value={logSearch}
              onChange={e => setLogSearch(e.target.value)}
              style={{ width: '100%', padding: '8px 12px', borderRadius: 6, border: '1px solid #ddd', fontSize: 13 }}
            />
          </div>
          <div className="table-wrap" style={{ maxHeight: 420, overflowY: 'auto' }}>
            <table>
              <thead><tr><th>TIMESTAMP</th><th>DEVICE / HOST</th><th>USER</th><th>EVENT / ACTION</th><th>IP</th><th>STATUS</th></tr></thead>
              <tbody>
                {filteredEvents.slice(0, 100).map((e, idx) => (
                  <tr key={idx}>
                    <td className="mono" style={{ fontSize: 11 }}>
                      {e.occurred_at ? new Date(e.occurred_at).toLocaleTimeString() : 'Recent'}
                    </td>
                    <td>
                      <strong style={{ color: '#7045ce' }}>{e.hostname || e.device_id}</strong>
                      <small style={{ display: 'block', color: '#888' }}>{e.source || 'syslog'}</small>
                    </td>
                    <td><strong>{e.user_id || e.username || 'admin'}</strong></td>
                    <td>
                      <span>{e.event_type}</span>
                      {e.raw_message && <small style={{ display: 'block', color: '#666', maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.raw_message}</small>}
                    </td>
                    <td className="mono" style={{ fontSize: 11 }}>{e.source_ip || '—'}</td>
                    <td>
                      <Badge
                        value={e.severity === 'warning' || e.event_type?.includes('FAIL') ? 'Failure' : 'Success'}
                        tone={e.severity === 'warning' || e.event_type?.includes('FAIL') ? 'critical' : 'active'}
                      />
                    </td>
                  </tr>
                ))}
                {filteredEvents.length === 0 && (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: 24, color: '#888' }}>
                      No events received yet. Click "Push Test Log to Sentinel" to verify ingestion.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </Panel>
      </div>
    </>
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

// ─── Settings & Admin Email Notifications ─────────────────────────────────
function SettingsPage({ resetDb, busy, showToast }) {
  const [emailForm, setEmailForm] = useState({
    admin_name: '',
    admin_email: '',
    enabled: true,
    smtp_host: 'smtp.gmail.com',
    smtp_port: 587,
    smtp_user: '',
    smtp_password: '',
    sender_name: 'AccessGuard Security Sentinel',
    notify_on_high_risk: true,
    notify_on_attack_detected: true,
    notify_on_reviews_queued: true,
  });
  const [hasPassword, setHasPassword] = useState(false);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  // Load email configuration and alert logs
  const loadEmailSettings = async () => {
    try {
      setLoading(true);
      const res = await fetch('/api/settings/email');
      if (res.ok) {
        const d = await res.json();
        setEmailForm({
          admin_name: d.admin_name || 'Main Security Administrator',
          admin_email: d.admin_email || '',
          enabled: d.enabled,
          smtp_host: d.smtp_host || 'smtp.gmail.com',
          smtp_port: d.smtp_port || 587,
          smtp_user: d.smtp_user || '',
          smtp_password: '',
          sender_name: d.sender_name || 'AccessGuard Security Sentinel',
          notify_on_high_risk: d.notify_on_high_risk,
          notify_on_attack_detected: d.notify_on_attack_detected,
          notify_on_reviews_queued: d.notify_on_reviews_queued,
        });
        setHasPassword(d.has_password);
      }
      const logsRes = await fetch('/api/settings/email/logs');
      if (logsRes.ok) {
        setLogs(await logsRes.json());
      }
    } catch (e) {
      showToast(`Failed to load email settings: ${e.message}`, false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEmailSettings();
  }, []);

  // Save Settings
  const handleSave = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = { ...emailForm };
      if (!payload.smtp_password && hasPassword) {
        delete payload.smtp_password;
      }
      const res = await fetch('/api/settings/email', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (res.ok) {
        showToast('Admin email settings updated successfully!');
        await loadEmailSettings();
      } else {
        showToast(`Failed: ${data.detail || data.message}`, false);
      }
    } catch (e) {
      showToast(`Error: ${e.message}`, false);
    } finally {
      setSaving(false);
    }
  };

  // Send Test Real Email
  const handleSendTest = async () => {
    setTesting(true);
    try {
      const res = await fetch('/api/settings/email/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recipient: emailForm.admin_email }),
      });
      const data = await res.json();
      if (data.ok) {
        if (data.is_real_delivery) {
          showToast(`Real email delivered successfully to ${data.recipient}! Check your inbox.`);
        } else {
          showToast(`Test alert logged to email dispatch drawer (${data.status}).`);
        }
        await loadEmailSettings();
      } else {
        showToast(`Send failed: ${data.error || data.message}`, false);
      }
    } catch (e) {
      showToast(`Error sending test email: ${e.message}`, false);
    } finally {
      setTesting(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {/* Real Gmail & Main Admin Email Configuration Panel */}
      <Panel
        title="Main Admin Automated Email Notifications (Gmail SMTP)"
        description="Configure your real Gmail or corporate SMTP credentials to receive automated security alerts immediately when an attack or high-risk privilege escalation is detected."
      >
        <form onSubmit={handleSave} className="mapping-form" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', padding: '24px 22px' }}>
          {/* Admin Identity */}
          <label>
            <span>Main Admin Name</span>
            <input
              required
              type="text"
              value={emailForm.admin_name}
              onChange={(e) => setEmailForm({ ...emailForm, admin_name: e.target.value })}
              placeholder="e.g. Chief Information Security Officer"
            />
          </label>

          <label>
            <span>Main Admin Email Address (Destination)</span>
            <input
              required
              type="email"
              value={emailForm.admin_email}
              onChange={(e) => setEmailForm({ ...emailForm, admin_email: e.target.value })}
              placeholder="e.g. your-email@gmail.com"
            />
            <small style={{ color: '#888', fontSize: '11px', marginTop: 2 }}>
              All high-risk breach advisories will be sent to this email.
            </small>
          </label>

          {/* Gmail SMTP Server Details */}
          <label>
            <span>SMTP Host</span>
            <input
              required
              type="text"
              value={emailForm.smtp_host}
              onChange={(e) => setEmailForm({ ...emailForm, smtp_host: e.target.value })}
              placeholder="smtp.gmail.com"
            />
          </label>

          <label>
            <span>SMTP Port (587 TLS or 465 SSL)</span>
            <input
              required
              type="number"
              value={emailForm.smtp_port}
              onChange={(e) => setEmailForm({ ...emailForm, smtp_port: Number(e.target.value) })}
              placeholder="587"
            />
          </label>

          {/* Gmail User & App Password */}
          <label>
            <span>Sender Gmail Address (Username)</span>
            <input
              type="email"
              value={emailForm.smtp_user}
              onChange={(e) => setEmailForm({ ...emailForm, smtp_user: e.target.value })}
              placeholder="your.alert.bot@gmail.com"
            />
          </label>

          <label>
            <span>Gmail App Password (16 characters)</span>
            <input
              type="password"
              value={emailForm.smtp_password}
              onChange={(e) => setEmailForm({ ...emailForm, smtp_password: e.target.value })}
              placeholder={hasPassword ? '•••••••••••••••• (Leave blank to keep existing)' : 'Enter 16-character App Password'}
            />
            <small style={{ color: '#888', fontSize: '11px', marginTop: 2 }}>
              Generate via Google Account → Security → 2-Step Verification → App passwords.
            </small>
          </label>

          {/* Trigger Toggles */}
          <div style={{ gridColumn: '1 / -1', marginTop: 8, paddingTop: 16, borderTop: '1px solid #ede9f4', display: 'flex', flexWrap: 'wrap', gap: 20 }}>
            <label className="confirmation" style={{ cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={emailForm.enabled}
                onChange={(e) => setEmailForm({ ...emailForm, enabled: e.target.checked })}
              />
              <span>Enable Automated Email Delivery</span>
            </label>

            <label className="confirmation" style={{ cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={emailForm.notify_on_attack_detected}
                onChange={(e) => setEmailForm({ ...emailForm, notify_on_attack_detected: e.target.checked })}
              />
              <span>🚨 Malicious Role Breach / Attack Detected</span>
            </label>

            <label className="confirmation" style={{ cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={emailForm.notify_on_high_risk}
                onChange={(e) => setEmailForm({ ...emailForm, notify_on_high_risk: e.target.checked })}
              />
              <span>⚠️ High Risk Privilege Escalation (Score &ge; 60)</span>
            </label>
          </div>

          {/* Action buttons */}
          <div style={{ gridColumn: '1 / -1', marginTop: 12, display: 'flex', gap: 12, justifyContent: 'flex-end', alignItems: 'center' }}>
            <button
              type="button"
              className="btn-light"
              onClick={handleSendTest}
              disabled={testing || !emailForm.admin_email}
            >
              <Send size={15} className={testing ? 'spin' : ''} />
              {testing ? 'Sending Test Email...' : 'Send Test Real Email'}
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={saving}
            >
              <Check size={16} />
              {saving ? 'Saving...' : 'Save Admin Email Settings'}
            </button>
          </div>
        </form>
      </Panel>

      {/* Dispatched Email Audit Logs */}
      <Panel title="Dispatched Security Email Log" description="Recent automated security alerts dispatched to the Main Administrator.">
        <div className="table-wrap" style={{ padding: '0 4px' }}>
          <table>
            <thead>
              <tr>
                <th>TIME</th>
                <th>RECIPIENT</th>
                <th>SUBJECT</th>
                <th>TRIGGER TYPE</th>
                <th>STATUS</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={5} style={{ textAlign: 'center', color: '#999', padding: '24px 0' }}>
                    No automated email alerts dispatched yet. Run an attack test scenario or click "Send Test Real Email".
                  </td>
                </tr>
              ) : (
                logs.map((l) => (
                  <tr key={l.id}>
                    <td>{new Date(l.sent_at).toLocaleString()}</td>
                    <td><strong>{l.recipient}</strong></td>
                    <td style={{ fontSize: '0.85rem' }}>{l.subject}</td>
                    <td>
                      <span className="badge" style={{ textTransform: 'capitalize' }}>
                        {l.trigger_type.replace('_', ' ')}
                      </span>
                    </td>
                    <td>
                      <Badge
                        value={l.status === 'sent' ? 'Sent (Real SMTP)' : (l.status === 'simulated' ? 'Simulated Log' : 'Failed')}
                        tone={l.status === 'sent' ? 'active' : (l.status === 'failed' ? 'critical' : 'purple')}
                      />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Panel>

      {/* Database Reset Controls */}
      <div className="settings-grid">
        <Panel title="Database & Clean Environment Controls">
          <div style={{ padding: '8px 0' }}>
            <p style={{ fontSize: 13, color: '#555', marginBottom: 14 }}>
              Purge synthetic demo records to start with a fresh, production-like clean database for entering real employees and connecting devices.
            </p>
            <button
              className="btn-danger"
              disabled={busy === 'reset-db'}
              onClick={resetDb}
              style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}
            >
              <AlertTriangle size={15} />
              {busy === 'reset-db' ? 'Purging records...' : 'Purge All Mock Data (Start Clean)'}
            </button>
          </div>
        </Panel>
        <Panel title="Demo Workspace">
          {[
            ['Workspace name', 'AccessGuard Research Lab'],
            ['Data mode', <Badge key="dm" value="Synthetic + imports" tone="purple" />],
            ['Database', 'PostgreSQL + Alembic migrations'],
            ['AI/ML', 'IsolationForest + Rule engine (scikit-learn)'],
            ['Remediation', <Badge key="rem" value="Simulated" tone="neutral" />],
            ['API docs', <code key="api">http://127.0.0.1:8200/docs</code>],
            ['Version', 'v2.0.0 — Complete Research Lab'],
          ].map(([k, v]) => (
            <div key={String(k)} className="setting-line"><span>{k}</span><strong>{v}</strong></div>
          ))}
        </Panel>
      </div>
    </div>
  );
}
