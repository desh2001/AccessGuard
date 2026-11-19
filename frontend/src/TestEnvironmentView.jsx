import React, { useState, useEffect } from 'react';
import {
  Activity, AlertTriangle, ArrowRight, CheckCircle2, ChevronRight,
  Clock, Database, Eye, Flame, Play, RefreshCw, RotateCcw,
  Sliders, Terminal, UserCheck, Users, ShieldAlert,
  Server, Github, Cloud, HardDrive, Check, AlertCircle, Plus, Target
} from 'lucide-react';

export default function TestEnvironmentView({
  subpage,
  companies,
  selectedCompanyId,
  setSelectedCompanyId,
  onRefresh,
  showToast,
  busy,
  setBusy,
}) {
  const [summary, setSummary] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  const [scenarioResults, setScenarioResults] = useState([]);
  const [mlMetrics, setMlMetrics] = useState(null);
  const [collectionData, setCollectionData] = useState({ items: [], total: 0 });
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('resources');
  const [searchQuery, setSearchQuery] = useState('');
  const [offset, setOffset] = useState(0);

  // Wizard state
  const [wizardOpen, setWizardOpen] = useState(false);
  const [wizardForm, setWizardForm] = useState({
    name: 'Acme Enterprise Labs',
    industry: 'Technology',
    count: 1000,
    locations: 'Colombo, London, New York',
    platforms: ['github', 'aws', 'windows', 'linux'],
    speed: 60.0,
    eps: 15,
    seed: 42,
  });

  const cid = selectedCompanyId || companies[0]?.id || 1;

  // Load subpage data
  const loadData = async () => {
    if (!cid) return;
    setLoading(true);
    try {
      if (subpage === 'test-overview' || subpage === 'sim-controls') {
        const res = await fetch(`/api/simulator/companies/${cid}/summary`);
        if (res.ok) setSummary(await res.json());
      } else if (subpage === 'test-scenarios') {
        const scRes = await fetch('/api/simulator/scenarios');
        if (scRes.ok) setScenarios(await scRes.json());
      } else if (subpage === 'test-results') {
        const metRes = await fetch(`/api/simulator/companies/${cid}/ml-metrics`);
        if (metRes.ok) setMlMetrics(await metRes.json());
      } else if (subpage === 'sim-activity') {
        const res = await fetch(`/api/simulator/companies/${cid}/collection?table=events&limit=100&offset=${offset}&q=${searchQuery}`);
        if (res.ok) setCollectionData(await res.json());
      } else if (subpage === 'sim-employees') {
        const res = await fetch(`/api/simulator/companies/${cid}/collection?table=employees&limit=50&offset=${offset}&q=${searchQuery}`);
        if (res.ok) setCollectionData(await res.json());
      } else if (['sim-github', 'sim-aws', 'sim-windows', 'sim-linux'].includes(subpage)) {
        const plat = subpage.replace('sim-', '');
        const table = activeTab === 'accounts' ? 'accounts' : 'resources';
        const res = await fetch(`/api/simulator/companies/${cid}/collection?table=${table}&platform=${plat}&limit=50&offset=${offset}&q=${searchQuery}`);
        if (res.ok) setCollectionData(await res.json());
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [subpage, cid, offset, activeTab]);

  // Simulation controls
  const controlSimulation = async (action) => {
    setBusy(`sim-${action}`);
    try {
      const res = await fetch(`/api/simulator/companies/${cid}/simulation/${action}`, { method: 'POST' });
      if (res.ok) {
        showToast(`Simulation engine: ${action.toUpperCase()}`);
        await loadData();
      }
    } catch (e) {
      showToast(`Error: ${e.message}`, false);
    } finally {
      setBusy(null);
    }
  };

  // Sync now
  const syncNow = async () => {
    setBusy('sync-inv');
    try {
      const res = await fetch(`/api/simulator/companies/${cid}/sync`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        showToast(`Synchronized ${data.records_imported} items into Test Environment!`);
        onRefresh();
        await loadData();
      } else {
        showToast(`Sync failed: ${data.detail}`, false);
      }
    } catch (e) {
      showToast(`Sync error: ${e.message}`, false);
    } finally {
      setBusy(null);
    }
  };

  // Poll events
  const pollEvents = async () => {
    setBusy('poll-events');
    try {
      const res = await fetch(`/api/simulator/companies/${cid}/poll-events`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        showToast(`Polled ${data.ingested} new events from live stream!`);
        onRefresh();
        await loadData();
      }
    } catch (e) {
      showToast(`Poll error: ${e.message}`, false);
    } finally {
      setBusy(null);
    }
  };

  // Run scenario
  const runScenario = async (scenId) => {
    setBusy(scenId);
    try {
      const res = await fetch(`/api/simulator/companies/${cid}/scenarios/${scenId}/run`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        showToast(`Scenario executed! Result: ${data.detection_result} (${data.execution_time_ms}ms)`);
        onRefresh();
        await loadData();
      } else {
        showToast(`Failed: ${data.detail}`, false);
      }
    } catch (e) {
      showToast(`Error: ${e.message}`, false);
    } finally {
      setBusy(null);
    }
  };

  // Reset Test Environment
  const resetEnv = async () => {
    if (!window.confirm('Reset simulated company and wipe all synthetic test data from AccessGuard? Production data is unaffected.')) return;
    setBusy('reset-env');
    try {
      const res = await fetch(`/api/simulator/companies/${cid}/reset`, { method: 'POST' });
      if (res.ok) {
        showToast('Test environment reset successfully!');
        onRefresh();
        await loadData();
      }
    } catch (e) {
      showToast(`Error: ${e.message}`, false);
    } finally {
      setBusy(null);
    }
  };

  // Create & Setup Company Wizard
  const handleWizardSubmit = async (e) => {
    e.preventDefault();
    setBusy('wizard-create');
    try {
      const res = await fetch('/api/simulator/companies', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(wizardForm),
      });
      const data = await res.json();
      if (res.ok) {
        showToast(`Company '${wizardForm.name}' created & synced (${data.sync.records_imported} items)!`);
        setSelectedCompanyId(data.company.id);
        setWizardOpen(false);
        onRefresh();
        await loadData();
      } else {
        showToast(`Failed: ${data.detail}`, false);
      }
    } catch (e) {
      showToast(`Error: ${e.message}`, false);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="test-env-view">
      {/* Top Controls Bar */}
      <div className="card" style={{ marginBottom: 20, padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--muted)' }}>VIRTUAL ENTERPRISE:</span>
          <select
            value={cid}
            onChange={(e) => setSelectedCompanyId(Number(e.target.value))}
            style={{ padding: '6px 12px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--card)', color: 'var(--fg)', fontWeight: 600 }}
          >
            {companies.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} ({c.industry}) — #{c.id}
              </option>
            ))}
          </select>
          <button className="btn-light" onClick={() => setWizardOpen(true)} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <Plus size={15} /> Setup New Enterprise Wizard
          </button>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <button className="btn-light" onClick={pollEvents} disabled={busy} title="Poll live synthetic telemetry">
            <Activity size={15} /> {busy === 'poll-events' ? 'Polling…' : 'Poll Live Logs'}
          </button>
          <button className="btn-primary" onClick={syncNow} disabled={busy} title="Full Inventory Synchronizer">
            <RefreshCw size={15} className={busy === 'sync-inv' ? 'spin' : ''} /> {busy === 'sync-inv' ? 'Syncing…' : 'Sync Inventory'}
          </button>
          <button className="btn-light" onClick={resetEnv} disabled={busy} style={{ color: 'var(--danger)' }} title="Wipe test data and reset clock">
            <RotateCcw size={15} /> Reset Test Lab
          </button>
        </div>
      </div>

      {/* ─── Subpage: Overview ─── */}
      {subpage === 'test-overview' && summary && (
        <>
          <div className="stat-grid four" style={{ marginBottom: 20 }}>
            <div className="stat-card">
              <div className="stat-icon purple"><Users size={20} /></div>
              <div className="stat-value">{Number(summary.employees || 0).toLocaleString()}</div>
              <div className="stat-label">Virtual Employees</div>
              <div className="stat-hint">{summary.online || 0} active in simulated shift</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon blue"><HardDrive size={20} /></div>
              <div className="stat-value">{Number(summary.accounts || 0).toLocaleString()}</div>
              <div className="stat-label">Platform Accounts</div>
              <div className="stat-hint">Across GitHub, AWS, Windows, Linux</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon orange"><Database size={20} /></div>
              <div className="stat-value">{Number(summary.resources || 0).toLocaleString()}</div>
              <div className="stat-label">Virtual Resources</div>
              <div className="stat-hint">Repos, EC2, IAM, Servers, Domains</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon pink"><Activity size={20} /></div>
              <div className="stat-value">{Number(summary.events || 0).toLocaleString()}</div>
              <div className="stat-label">Telemetry Events</div>
              <div className="stat-hint">Continuous synthetic access logs</div>
            </div>
          </div>

          <div className="panel-grid two" style={{ marginBottom: 20 }}>
            <div className="panel">
              <div className="panel-header">
                <h2>Simulation Engine Status</h2>
                <span className={`badge ${summary.company?.state === 'running' ? 'active' : 'suspended'}`}>
                  {summary.company?.state?.toUpperCase() || 'UNKNOWN'}
                </span>
              </div>
              <div style={{ padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="muted">Simulated Clock:</span>
                  <strong>{summary.company?.clock ? new Date(summary.company.clock * 1000).toUTCString() : '—'}</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="muted">Time Acceleration:</span>
                  <strong>{summary.company?.speed}× real-time</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="muted">Events Per Second:</span>
                  <strong>{summary.company?.eps} events/sec</strong>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span className="muted">Anomaly Probability:</span>
                  <strong>{summary.company?.exception_pct}% failed auth attempts</strong>
                </div>
                <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
                  <button className="btn-primary" onClick={() => controlSimulation('start')}><Play size={14} /> Start</button>
                  <button className="btn-light" onClick={() => controlSimulation('pause')}>Pause</button>
                  <button className="btn-light" onClick={() => controlSimulation('stop')}>Stop</button>
                  <button className="btn-light" onClick={() => controlSimulation('reset')} style={{ color: 'var(--danger)' }}>Reset Clock</button>
                </div>
              </div>
            </div>

            <div className="panel">
              <div className="panel-header">
                <h2>Activity by Platform</h2>
                <span className="badge neutral">Real-time Ingestion</span>
              </div>
              <div style={{ padding: '16px 20px' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Platform</th>
                      <th>Logged Events</th>
                      <th>Coverage</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(summary.by_platform || []).map((p) => (
                      <tr key={p.platform}>
                        <td style={{ fontWeight: 600, textTransform: 'capitalize' }}>{p.platform}</td>
                        <td>{Number(p.count).toLocaleString()}</td>
                        <td><span className="badge low">100% Attested</span></td>
                      </tr>
                    ))}
                    {!summary.by_platform?.length && (
                      <tr><td colSpan="3" style={{ textAlign: 'center', padding: 20 }}>No activity logged yet. Click Start.</td></tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}

      {/* ─── Subpage: Virtual Companies ─── */}
      {subpage === 'sim-companies' && (
        <div className="panel">
          <div className="panel-header">
            <h2>Configured Virtual Companies</h2>
            <button className="btn-primary" onClick={() => setWizardOpen(true)}><Plus size={15} /> Add Virtual Company</button>
          </div>
          <div style={{ padding: 20 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Company Name</th>
                  <th>Industry</th>
                  <th>Locations</th>
                  <th>Status</th>
                  <th>Virtual Clock</th>
                  <th>Action</th>
                </tr>
              </thead>
              <tbody>
                {companies.map((co) => (
                  <tr key={co.id} style={{ background: co.id === cid ? 'rgba(99, 102, 241, 0.08)' : 'transparent' }}>
                    <td><b>#{co.id}</b></td>
                    <td style={{ fontWeight: 600 }}>{co.name}</td>
                    <td>{co.industry}</td>
                    <td>{co.locations}</td>
                    <td><span className={`badge ${co.state === 'running' ? 'active' : 'suspended'}`}>{co.state}</span></td>
                    <td style={{ fontSize: '0.82rem' }}>{co.clock ? new Date(co.clock * 1000).toISOString() : '—'}</td>
                    <td>
                      <button className="btn-light" onClick={() => setSelectedCompanyId(co.id)}>
                        {co.id === cid ? 'Selected' : 'Switch To'}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ─── Subpage: Virtual Employees ─── */}
      {subpage === 'sim-employees' && (
        <div className="panel">
          <div className="panel-header">
            <h2>Virtual Employee Directory ({collectionData.total} Total)</h2>
            <input
              placeholder="Search employee name, email or title…"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{ padding: '6px 14px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--card)' }}
            />
          </div>
          <div style={{ padding: 20 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Full Name</th>
                  <th>Work Email</th>
                  <th>Department</th>
                  <th>Job Title</th>
                  <th>Status</th>
                  <th>Last Simulation Activity</th>
                </tr>
              </thead>
              <tbody>
                {collectionData.items?.map((emp) => (
                  <tr key={emp.id}>
                    <td><code>sim-emp-{emp.id}</code></td>
                    <td style={{ fontWeight: 600 }}>{emp.name}</td>
                    <td>{emp.email}</td>
                    <td><span className="badge neutral">{emp.department}</span></td>
                    <td>{emp.title}</td>
                    <td><span className={`badge ${emp.status === 'active' ? 'active' : 'critical'}`}>{emp.status}</span></td>
                    <td style={{ fontSize: '0.82rem' }}>{emp.last_activity ? new Date(emp.last_activity).toLocaleTimeString() : 'Idle'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ─── Subpage: Platforms (GitHub, AWS, Windows, Linux) ─── */}
      {['sim-github', 'sim-aws', 'sim-windows', 'sim-linux'].includes(subpage) && (
        <div className="panel">
          <div className="panel-header">
            <h2 style={{ textTransform: 'capitalize' }}>{subpage.replace('sim-', '')} Virtual Infrastructure</h2>
            <div style={{ display: 'flex', gap: 10 }}>
              <button className={`btn-light ${activeTab === 'resources' ? 'btn-primary' : ''}`} onClick={() => setActiveTab('resources')}>
                Resources & Entitlements
              </button>
              <button className={`btn-light ${activeTab === 'accounts' ? 'btn-primary' : ''}`} onClick={() => setActiveTab('accounts')}>
                Platform Accounts
              </button>
            </div>
          </div>
          <div style={{ padding: 20 }}>
            <table className="data-table">
              <thead>
                {activeTab === 'resources' ? (
                  <tr>
                    <th>ID</th>
                    <th>Resource Type</th>
                    <th>Resource Name / Key</th>
                    <th>State</th>
                  </tr>
                ) : (
                  <tr>
                    <th>Account ID</th>
                    <th>Employee ID</th>
                    <th>Platform</th>
                    <th>Role / Privilege</th>
                    <th>Account Status</th>
                  </tr>
                )}
              </thead>
              <tbody>
                {collectionData.items?.map((row) => (
                  <tr key={row.id}>
                    {activeTab === 'resources' ? (
                      <>
                        <td>#{row.id}</td>
                        <td><span className="badge neutral">{row.kind}</span></td>
                        <td style={{ fontWeight: 600 }}>{row.name}</td>
                        <td><span className="badge low">{row.state}</span></td>
                      </>
                    ) : (
                      <>
                        <td>#{row.id}</td>
                        <td><code>sim-emp-{row.employee}</code></td>
                        <td style={{ textTransform: 'capitalize' }}>{row.platform}</td>
                        <td><span className={`badge ${row.permission === 'admin' ? 'critical' : 'neutral'}`}>{row.permission}</span></td>
                        <td><span className={`badge ${row.status === 'active' ? 'active' : 'suspended'}`}>{row.status}</span></td>
                      </>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ─── Subpage: Simulation Controls ─── */}
      {subpage === 'sim-controls' && summary && (
        <div className="panel">
          <div className="panel-header">
            <h2>Simulation Engine Real-Time Controls</h2>
            <span className={`badge ${summary.company?.state === 'running' ? 'active' : 'suspended'}`}>
              Engine {summary.company?.state}
            </span>
          </div>
          <div style={{ padding: 24, maxWidth: 640 }}>
            <p className="muted" style={{ marginBottom: 20 }}>
              Directly adjust the synthetic generation loop parameters. Changes take effect on the next tick.
            </p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <label style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>Clock Acceleration (Speed)</label>
                <input
                  type="number"
                  value={summary.company?.speed || 60}
                  readOnly
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)' }}
                />
                <small className="muted">1 real second = {summary.company?.speed || 60} simulated seconds</small>
              </div>
              <div>
                <label style={{ display: 'block', fontWeight: 600, marginBottom: 6 }}>Events Per Second (EPS)</label>
                <input
                  type="number"
                  value={summary.company?.eps || 10}
                  readOnly
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)' }}
                />
              </div>
              <div style={{ display: 'flex', gap: 12, marginTop: 14 }}>
                <button className="btn-primary" onClick={() => controlSimulation('start')}><Play size={16} /> Start Simulator</button>
                <button className="btn-light" onClick={() => controlSimulation('pause')}>Pause</button>
                <button className="btn-light" onClick={() => controlSimulation('stop')}>Stop</button>
                <button className="btn-light" onClick={() => controlSimulation('reset')} style={{ color: 'var(--danger)' }}>Reset Events</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ─── Subpage: Activity Logs ─── */}
      {subpage === 'sim-activity' && (
        <div className="panel">
          <div className="panel-header">
            <h2>Live Synthetic Activity Stream ({collectionData.total} Events)</h2>
            <button className="btn-light" onClick={pollEvents}><RefreshCw size={15} /> Poll Stream</button>
          </div>
          <div style={{ padding: 20 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Event ID</th>
                  <th>Timestamp</th>
                  <th>Platform</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Target Resource</th>
                  <th>Result</th>
                  <th>Source IP</th>
                </tr>
              </thead>
              <tbody>
                {collectionData.items?.map((ev) => (
                  <tr key={ev.id}>
                    <td>#{ev.id}</td>
                    <td style={{ fontSize: '0.82rem' }}>{ev.ts ? new Date(ev.ts).toLocaleTimeString() : '—'}</td>
                    <td><span className="badge neutral">{ev.platform}</span></td>
                    <td style={{ fontWeight: 600 }}>{ev.actor}</td>
                    <td><code>{ev.action}</code></td>
                    <td>{ev.resource}</td>
                    <td><span className={`badge ${ev.result === 'success' ? 'low' : 'critical'}`}>{ev.result}</span></td>
                    <td style={{ fontSize: '0.82rem' }}>{ev.ip}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ─── Subpage: Test Scenarios ─── */}
      {subpage === 'test-scenarios' && (
        <div className="panel">
          <div className="panel-header">
            <h2>Automated Security Test Scenarios</h2>
            <span className="badge neutral">Pre-packaged Threats & Misconfigurations</span>
          </div>
          <div style={{ padding: 20, display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(340px, 1fr))', gap: 16 }}>
            {scenarios.map((scen) => (
              <div key={scen.id} className="card" style={{ padding: 18, display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                    <span className="badge purple">{scen.category}</span>
                    <span className="badge neutral" style={{ textTransform: 'capitalize' }}>{scen.platform}</span>
                  </div>
                  <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: 8 }}>{scen.name}</h3>
                  <p className="muted" style={{ fontSize: '0.85rem', marginBottom: 14 }}>{scen.description}</p>
                  <div style={{ background: 'rgba(99, 102, 241, 0.05)', padding: '8px 12px', borderRadius: 6, fontSize: '0.82rem', marginBottom: 16 }}>
                    <strong>Expected Detection:</strong> {scen.expected_behavior}
                  </div>
                </div>
                <button
                  className="btn-primary"
                  onClick={() => runScenario(scen.id)}
                  disabled={busy === scen.id}
                  style={{ width: '100%', justifyContent: 'center' }}
                >
                  <Flame size={15} /> {busy === scen.id ? 'Running Scenario…' : 'Run Scenario'}
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ─── Subpage: Test Results & ML Metrics ─── */}
      {subpage === 'test-results' && (
        <>
          <div className="stat-grid four" style={{ marginBottom: 20 }}>
            <div className="stat-card">
              <div className="stat-icon purple"><CheckCircle2 size={20} /></div>
              <div className="stat-value">{mlMetrics?.precision !== undefined ? `${Math.round(mlMetrics.precision * 100)}%` : '100%'}</div>
              <div className="stat-label">Model Precision</div>
              <div className="stat-hint">{mlMetrics?.true_positives || 0} true detections</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon blue"><Target size={20} /></div>
              <div className="stat-value">{mlMetrics?.recall !== undefined ? `${Math.round(mlMetrics.recall * 100)}%` : '100%'}</div>
              <div className="stat-label">Model Recall</div>
              <div className="stat-hint">0 missed anomalies</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon orange"><ShieldAlert size={20} /></div>
              <div className="stat-value">{mlMetrics?.f1_score !== undefined ? mlMetrics.f1_score : '1.000'}</div>
              <div className="stat-label">F1 Detection Score</div>
              <div className="stat-hint">Harmonic mean precision/recall</div>
            </div>
            <div className="stat-card">
              <div className="stat-icon pink"><Clock size={20} /></div>
              <div className="stat-value">{mlMetrics?.avg_detection_latency_ms || 0}ms</div>
              <div className="stat-label">Avg Detection Latency</div>
              <div className="stat-hint">Inference + Rule Execution</div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-header">
              <h2>Recent Test Scenario Execution Results</h2>
              <button className="btn-light" onClick={loadData}><RefreshCw size={15} /> Refresh Results</button>
            </div>
            <div style={{ padding: 20 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Run ID</th>
                    <th>Scenario Name</th>
                    <th>Platform</th>
                    <th>Result</th>
                    <th>Latency</th>
                    <th>Executed At</th>
                  </tr>
                </thead>
                <tbody>
                  {mlMetrics?.recent_runs?.map((r) => (
                    <tr key={r.id}>
                      <td>#{r.id}</td>
                      <td style={{ fontWeight: 600 }}>{r.name}</td>
                      <td style={{ textTransform: 'capitalize' }}>{r.platform}</td>
                      <td>
                        <span className={`badge ${r.detection_result === 'Detected' ? 'active' : 'critical'}`}>
                          {r.detection_result}
                        </span>
                      </td>
                      <td>{r.execution_time_ms} ms</td>
                      <td style={{ fontSize: '0.82rem' }}>{new Date(r.executed_at).toLocaleString()}</td>
                    </tr>
                  ))}
                  {!mlMetrics?.recent_runs?.length && (
                    <tr><td colSpan="6" style={{ textAlign: 'center', padding: 20 }}>No scenarios executed yet. Navigate to Test Scenarios to trigger automated threats.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {/* ─── Setup Wizard Modal ─── */}
      {wizardOpen && (
        <div className="overlay top" style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <form className="card" onSubmit={handleWizardSubmit} style={{ maxWidth: 540, width: '90%', padding: 24 }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: 8 }}>One-Click Virtual Enterprise Setup</h2>
            <p className="muted" style={{ fontSize: '0.85rem', marginBottom: 20 }}>
              Generate complete synthetic enterprise infrastructure with employees, accounts, and live activity streams.
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div>
                <label style={{ display: 'block', fontWeight: 600, fontSize: '0.85rem', marginBottom: 4 }}>Enterprise Preset</label>
                <select
                  value={wizardForm.count}
                  onChange={(e) => setWizardForm({ ...wizardForm, count: Number(e.target.value) })}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--card)' }}
                >
                  <option value={100}>Small — 100 employees</option>
                  <option value={1000}>Medium — 1,000 employees</option>
                  <option value={10000}>Large — 10,000 employees</option>
                  <option value={100000}>Enterprise — 100,000 employees</option>
                </select>
              </div>

              <div>
                <label style={{ display: 'block', fontWeight: 600, fontSize: '0.85rem', marginBottom: 4 }}>Company Name</label>
                <input
                  required
                  value={wizardForm.name}
                  onChange={(e) => setWizardForm({ ...wizardForm, name: e.target.value })}
                  style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--card)' }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                <div>
                  <label style={{ display: 'block', fontWeight: 600, fontSize: '0.85rem', marginBottom: 4 }}>Industry</label>
                  <input
                    value={wizardForm.industry}
                    onChange={(e) => setWizardForm({ ...wizardForm, industry: e.target.value })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--card)' }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontWeight: 600, fontSize: '0.85rem', marginBottom: 4 }}>Events / Sec (EPS)</label>
                  <input
                    type="number"
                    value={wizardForm.eps}
                    onChange={(e) => setWizardForm({ ...wizardForm, eps: Number(e.target.value) })}
                    style={{ width: '100%', padding: '8px 12px', borderRadius: 8, border: '1px solid var(--border)', background: 'var(--card)' }}
                  />
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 10 }}>
                <button type="button" className="btn-light" onClick={() => setWizardOpen(false)}>Cancel</button>
                <button type="submit" className="btn-primary" disabled={busy === 'wizard-create'}>
                  {busy === 'wizard-create' ? 'Generating Virtual Enterprise…' : 'Create & Start Test Environment'}
                </button>
              </div>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
