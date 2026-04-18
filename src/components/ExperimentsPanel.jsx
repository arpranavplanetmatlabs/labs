import { useState, useEffect, useCallback, useRef } from 'react';
import {
  FlaskConical, Plus, Search, CheckCircle, Clock, AlertCircle,
  Loader, X, Save, TestTube, Trash2, Lightbulb,
  BarChart2, Brain, Info, RefreshCw, Target, ChevronRight,
  Beaker, SlidersHorizontal, Activity, Database,
} from 'lucide-react';
import UncertaintyBar from './UncertaintyBar';

const API_BASE = 'http://localhost:8000';

const SCORE_COLOR = s =>
  s >= 0.8 ? 'var(--score-high)' : s >= 0.6 ? 'var(--score-mid)' : 'var(--score-low)';

const STATUS_CONFIG = {
  pending:   { label: 'Queued',    color: 'var(--text-muted)',  icon: Clock },
  queued:    { label: 'Queued',    color: 'var(--text-muted)',  icon: Clock },
  running:   { label: 'Running',   color: 'var(--accent)',      icon: Loader },
  completed: { label: 'Completed', color: 'var(--score-high)',  icon: CheckCircle },
  failed:    { label: 'Failed',    color: 'var(--score-low)',   icon: AlertCircle },
};

const DOMAIN_PRESETS = {
  custom: {
    label: 'Custom',
    icon: '✦',
    description: 'Define your own properties and targets from scratch',
    props: [],
  },
  mechanical: {
    label: 'Mechanical',
    icon: '⚙',
    description: 'Tensile strength, elongation, flexural modulus',
    props: [
      { name: 'tensile_strength', unit: 'MPa', target: '', weight: '0.40' },
      { name: 'elongation',       unit: '%',   target: '', weight: '0.30' },
      { name: 'flexural_modulus', unit: 'MPa', target: '', weight: '0.30' },
    ],
  },
  emi: {
    label: 'EMI Shielding',
    icon: '📡',
    description: 'EMI shielding effectiveness, conductivity',
    props: [
      { name: 'emi_shielding',           unit: 'dB',  target: '', weight: '0.50' },
      { name: 'electrical_conductivity', unit: 'S/m', target: '', weight: '0.30' },
      { name: 'tensile_strength',        unit: 'MPa', target: '', weight: '0.20' },
    ],
  },
  thermal: {
    label: 'Thermal',
    icon: '🌡',
    description: 'Heat deflection, thermal conductivity, Tg',
    props: [
      { name: 'heat_deflection_temp',  unit: '°C',   target: '', weight: '0.40' },
      { name: 'thermal_conductivity',  unit: 'W/mK', target: '', weight: '0.35' },
      { name: 'glass_transition_temp', unit: '°C',   target: '', weight: '0.25' },
    ],
  },
  nanocomposite: {
    label: 'Nanocomposite',
    icon: '⬡',
    description: 'Strength, EMI, density, filler loading',
    props: [
      { name: 'tensile_strength', unit: 'MPa',   target: '', weight: '0.30' },
      { name: 'emi_shielding',    unit: 'dB',    target: '', weight: '0.40' },
      { name: 'density',          unit: 'g/cm³', target: '', weight: '0.15' },
      { name: 'filler_loading',   unit: 'wt%',   target: '', weight: '0.15' },
    ],
  },
};

// ── Primitives ─────────────────────────────────────────────────────────────────

function StatusPill({ status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.pending;
  const Icon = cfg.icon;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 4,
      fontSize: 10, color: cfg.color,
      background: `${cfg.color}18`, border: `1px solid ${cfg.color}44`,
      borderRadius: 10, padding: '2px 8px',
      fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px', flexShrink: 0,
    }}>
      <Icon size={9} style={status === 'running' ? { animation: 'spin 1s linear infinite' } : {}} />
      {cfg.label}
    </span>
  );
}

function ScoreBar({ score, height = 4 }) {
  const pct   = Math.round((score || 0) * 100);
  const color = SCORE_COLOR(score || 0);
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
      <div style={{ flex: 1, height, background: 'var(--bg-overlay)', borderRadius: height, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: color, borderRadius: height, transition: 'width 0.4s ease' }} />
      </div>
      <span style={{ fontSize: 11, fontFamily: 'var(--font-mono)', color, fontWeight: 700, minWidth: 32, textAlign: 'right' }}>
        {pct}%
      </span>
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 10, fontWeight: 700, color: 'var(--text-muted)',
      textTransform: 'uppercase', letterSpacing: '0.9px', marginBottom: 10,
    }}>
      {children}
    </div>
  );
}

function Block({ title, children }) {
  return (
    <div>
      <SectionLabel>{title}</SectionLabel>
      {children}
    </div>
  );
}

// ── Main panel ─────────────────────────────────────────────────────────────────

export default function ExperimentsPanel() {
  const [experiments, setExperiments]     = useState([]);
  const [loading, setLoading]             = useState(true);
  const [refreshing, setRefreshing]       = useState(false);
  const [searchQuery, setSearchQuery]     = useState('');
  const [selectedId, setSelectedId]       = useState(null);
  const [selectedExp, setSelectedExp]     = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showCreate, setShowCreate]       = useState(false);
  const [activeTab, setActiveTab]         = useState('overview');
  const [surrogate, setSurrogate]         = useState(null);
  const [suggestions, setSuggestions]     = useState([]);
  const [aiLoading, setAiLoading]         = useState(null);

  useEffect(() => { fetchExperiments(); }, []);

  const fetchExperiments = useCallback(async (silent = false) => {
    if (!silent) setLoading(true); else setRefreshing(true);
    try {
      const res = await fetch(`${API_BASE}/api/experiments?limit=200`);
      if (res.ok) {
        const data = await res.json();
        setExperiments(data.experiments || []);
      }
    } catch (_) {}
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  const fetchDetail = useCallback(async (id) => {
    setDetailLoading(true);
    setSurrogate(null);
    setSuggestions([]);
    try {
      const res = await fetch(`${API_BASE}/api/experiments/${id}`);
      if (res.ok) setSelectedExp(await res.json());
    } catch (_) {}
    finally { setDetailLoading(false); }
  }, []);

  const handleSelect = (exp) => {
    setSelectedId(exp.id);
    setActiveTab('overview');
    fetchDetail(exp.id);
  };

  const handleCreate = async (formData) => {
    const res = await fetch(`${API_BASE}/api/experiments`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(formData),
    });
    if (res.ok) {
      const created = await res.json();
      setShowCreate(false);
      await fetchExperiments(true);
      handleSelect({ ...created, id: created.experiment_id ?? created.id });
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('Delete this experiment?')) return;
    const res = await fetch(`${API_BASE}/api/experiments/${id}`, { method: 'DELETE' });
    if (!res.ok) return;
    setExperiments(prev => prev.filter(e => e.id !== id));
    setSelectedId(null);
    setSelectedExp(null);
    fetchExperiments(true);
  };

  const handleAddResult = async (expId, row) => {
    const res = await fetch(`${API_BASE}/api/experiments/${expId}/results`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ experiment_id: expId, results: [row] }),
    });
    if (res.ok) { fetchDetail(expId); fetchExperiments(true); }
  };

  const handleComplete = async (id) => {
    const res = await fetch(`${API_BASE}/api/experiments/${id}/complete`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}),
    });
    if (res.ok) { fetchDetail(id); fetchExperiments(true); }
  };

  const handleSurrogate = async (id) => {
    setAiLoading('surrogate');
    try {
      const res = await fetch(`${API_BASE}/api/experiments/${id}/surrogate`);
      if (res.ok) setSurrogate(await res.json());
    } catch (_) {}
    finally { setAiLoading(null); }
  };

  const handleSuggest = async (id) => {
    setAiLoading('suggest');
    try {
      const res = await fetch(`${API_BASE}/api/experiments/${id}/suggest`, { method: 'POST' });
      if (res.ok) { const d = await res.json(); setSuggestions(d.suggestions || []); }
    } catch (_) {}
    finally { setAiLoading(null); }
  };

  // ── Derived ──────────────────────────────────────────────────────────────────

  const filtered = experiments.filter(e =>
    e.name?.toLowerCase().includes(searchQuery.toLowerCase()) ||
    e.material_name?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const running   = filtered.filter(e => e.status === 'running');
  const queued    = filtered.filter(e => ['pending', 'queued'].includes(e.status));
  const completed = filtered.filter(e => ['completed', 'failed'].includes(e.status));
  const doneCount = experiments.filter(e => e.status === 'completed').length;
  const bestScore = experiments
    .filter(e => e.status === 'completed' && e.confidence)
    .reduce((max, e) => Math.max(max, e.confidence || 0), 0);

  // ── Render ────────────────────────────────────────────────────────────────────

  return (
    <>
      {showCreate && (
        <CreateModal onSubmit={handleCreate} onClose={() => setShowCreate(false)} />
      )}

      <div style={{ display: 'flex', height: '100%', gap: 'var(--pad-md)', overflow: 'hidden' }}>

        {/* ── LEFT RAIL ── */}
        <div className="glass-panel" style={{
          width: 300, flexShrink: 0,
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>
          {/* Header */}
          <div style={{ padding: '14px 16px 12px', borderBottom: '1px solid var(--glass-border)', flexShrink: 0 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <FlaskConical size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
              <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-primary)', flex: 1 }}>
                Experiments
              </span>
              <button className="btn btn-ghost btn-sm" onClick={() => fetchExperiments(true)}
                disabled={refreshing} title="Refresh" style={{ padding: '4px 6px' }}>
                <RefreshCw size={12} style={refreshing ? { animation: 'spin 1s linear infinite' } : {}} />
              </button>
              <button className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)} style={{ gap: 5 }}>
                <Plus size={12} /> New
              </button>
            </div>

            {/* Stats row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6, marginBottom: 12 }}>
              {[
                { label: 'Total',   value: experiments.length,  color: 'var(--text-primary)' },
                { label: 'Active',  value: running.length,      color: 'var(--accent)' },
                { label: 'Done',    value: doneCount,           color: 'var(--score-high)' },
                {
                  label: 'Best',
                  value: bestScore > 0 ? `${Math.round(bestScore * 100)}%` : '—',
                  color: bestScore > 0 ? SCORE_COLOR(bestScore) : 'var(--text-muted)',
                },
              ].map(s => (
                <div key={s.label} style={{
                  textAlign: 'center', padding: '7px 2px',
                  background: 'var(--bg-overlay)', borderRadius: 'var(--r-sm)',
                  border: '1px solid var(--glass-border)',
                }}>
                  <div style={{
                    fontSize: 15, fontWeight: 800,
                    fontFamily: 'var(--font-mono)', color: s.color, lineHeight: 1,
                  }}>
                    {s.value}
                  </div>
                  <div style={{
                    fontSize: 9, color: 'var(--text-muted)',
                    textTransform: 'uppercase', letterSpacing: '0.4px', marginTop: 3,
                  }}>
                    {s.label}
                  </div>
                </div>
              ))}
            </div>

            {/* Search */}
            <div style={{ position: 'relative' }}>
              <Search size={11} style={{
                position: 'absolute', left: 9, top: '50%',
                transform: 'translateY(-50%)', color: 'var(--text-muted)',
              }} />
              <input
                type="text" placeholder="Search…" value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                style={{
                  width: '100%', boxSizing: 'border-box',
                  paddingLeft: 28, paddingRight: 10, paddingTop: 7, paddingBottom: 7,
                  background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)',
                  borderRadius: 'var(--r-sm)', color: 'var(--text-primary)', fontSize: 12, outline: 'none',
                }}
              />
            </div>
          </div>

          {/* List */}
          <div style={{ flex: 1, overflow: 'auto', padding: '6px 0' }}>
            {loading ? (
              <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
                <Loader size={20} style={{ animation: 'spin 1s linear infinite', color: 'var(--accent)' }} />
              </div>
            ) : filtered.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 16px', color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.7 }}>
                {searchQuery ? 'No matches found' : 'No experiments yet.\nClick New to create one.'}
              </div>
            ) : (
              <>
                <ListGroup label="Running"   count={running.length}   color="var(--accent)"
                  experiments={running}   selectedId={selectedId} onSelect={handleSelect} />
                <ListGroup label="Queued"    count={queued.length}    color="var(--text-muted)"
                  experiments={queued}    selectedId={selectedId} onSelect={handleSelect} />
                <ListGroup label="Completed" count={completed.length} color="var(--score-high)"
                  experiments={completed} selectedId={selectedId} onSelect={handleSelect} />
              </>
            )}
          </div>
        </div>

        {/* ── RIGHT PANEL ── */}
        <div style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
          {detailLoading ? (
            <div className="glass-panel" style={{
              height: '100%', display: 'flex',
              alignItems: 'center', justifyContent: 'center',
            }}>
              <Loader size={24} style={{ animation: 'spin 1s linear infinite', color: 'var(--accent)' }} />
            </div>
          ) : selectedId && selectedExp ? (
            <DetailPanel
              exp={selectedExp}
              activeTab={activeTab} setActiveTab={setActiveTab}
              onDelete={() => handleDelete(selectedExp.id)}
              onAddResult={(row) => handleAddResult(selectedExp.id, row)}
              onComplete={() => handleComplete(selectedExp.id)}
              onSurrogate={() => handleSurrogate(selectedExp.id)}
              onSuggest={() => handleSuggest(selectedExp.id)}
              surrogate={surrogate} suggestions={suggestions} aiLoading={aiLoading}
            />
          ) : (
            <EmptyState onNew={() => setShowCreate(true)} />
          )}
        </div>
      </div>
    </>
  );
}

// ── List group ─────────────────────────────────────────────────────────────────

function ListGroup({ label, count, color, experiments, selectedId, onSelect }) {
  if (count === 0) return null;
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={{ padding: '6px 16px 3px', display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 9, fontWeight: 700, color, textTransform: 'uppercase', letterSpacing: '0.9px' }}>
          {label}
        </span>
        <span style={{
          fontSize: 9, fontFamily: 'var(--font-mono)', color: 'var(--text-muted)',
          background: 'var(--bg-overlay)', padding: '1px 5px', borderRadius: 6,
        }}>
          {count}
        </span>
      </div>
      {experiments.map(exp => (
        <ListRow key={exp.id} exp={exp} selected={exp.id === selectedId} onSelect={() => onSelect(exp)} />
      ))}
    </div>
  );
}

function ListRow({ exp, selected, onSelect }) {
  const cfg       = STATUS_CONFIG[exp.status] || STATUS_CONFIG.pending;
  const Icon      = cfg.icon;
  const isRunning = exp.status === 'running';
  return (
    <button
      onClick={onSelect}
      style={{
        width: '100%', textAlign: 'left', padding: '9px 16px',
        background: selected ? 'var(--glass-active)' : 'transparent',
        border: 'none', borderLeft: `3px solid ${selected ? cfg.color : 'transparent'}`,
        cursor: 'pointer', transition: 'background 0.12s, border-color 0.12s',
      }}
      onMouseEnter={e => { if (!selected) e.currentTarget.style.background = 'var(--bg-overlay)'; }}
      onMouseLeave={e => { if (!selected) e.currentTarget.style.background = 'transparent'; }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <Icon size={11} style={{
          color: cfg.color, flexShrink: 0,
          ...(isRunning ? { animation: 'spin 1s linear infinite' } : {}),
        }} />
        <span style={{
          fontSize: 12, fontWeight: 600, flex: 1,
          color: selected ? 'var(--text-primary)' : 'var(--text-secondary)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {exp.name}
        </span>
        {exp.confidence > 0 && (
          <span style={{
            fontSize: 10, fontFamily: 'var(--font-mono)',
            color: SCORE_COLOR(exp.confidence), fontWeight: 700, flexShrink: 0,
          }}>
            {Math.round(exp.confidence * 100)}%
          </span>
        )}
        <ChevronRight size={10} style={{ color: 'var(--text-muted)', flexShrink: 0, opacity: selected ? 1 : 0 }} />
      </div>
      {exp.material_name && (
        <div style={{
          fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)',
          marginTop: 2, paddingLeft: 19,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {exp.material_name}
        </div>
      )}
    </button>
  );
}

// ── Empty state ────────────────────────────────────────────────────────────────

function EmptyState({ onNew }) {
  return (
    <div className="glass-panel" style={{
      height: '100%', display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', gap: 20,
    }}>
      <div style={{
        width: 64, height: 64, borderRadius: '50%',
        background: 'var(--glass-active)', border: '1px solid var(--glass-border)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <FlaskConical size={28} style={{ color: 'var(--accent)', opacity: 0.7 }} />
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 8 }}>
          No experiment selected
        </div>
        <div style={{ fontSize: 13, color: 'var(--text-muted)', maxWidth: 300, lineHeight: 1.7 }}>
          Select an experiment from the list, or create a new one to start tracking results.
        </div>
      </div>
      <button className="btn btn-primary" onClick={onNew} style={{ gap: 6 }}>
        <Plus size={14} /> New Experiment
      </button>
    </div>
  );
}

// ── Detail panel ───────────────────────────────────────────────────────────────

const TABS = [
  { id: 'overview', label: 'Overview', icon: Info },
  { id: 'results',  label: 'Results',  icon: BarChart2 },
  { id: 'ai',       label: 'AI',       icon: Brain },
];

function DetailPanel({
  exp, activeTab, setActiveTab,
  onDelete, onAddResult, onComplete,
  onSurrogate, onSuggest, surrogate, suggestions, aiLoading,
}) {
  const cfg = STATUS_CONFIG[exp.status] || STATUS_CONFIG.pending;

  return (
    <div className="glass-panel" style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

      {/* Header */}
      <div style={{ padding: '16px 22px 14px', borderBottom: '1px solid var(--glass-border)', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <div style={{
            width: 38, height: 38, borderRadius: 'var(--r-sm)', flexShrink: 0,
            background: `${cfg.color}18`, border: `1px solid ${cfg.color}44`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <TestTube size={17} style={{ color: cfg.color }} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontWeight: 700, fontSize: 16, color: 'var(--text-primary)', lineHeight: 1.3, marginBottom: 8, wordBreak: 'break-word' }}>
              {exp.name}
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <StatusPill status={exp.status} />
              {exp.material_name && (
                <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {exp.material_name}
                </span>
              )}
              {exp.iteration > 0 && (
                <span style={{
                  fontSize: 10, color: 'var(--accent)',
                  background: 'rgba(109,106,248,0.12)', border: '1px solid rgba(109,106,248,0.3)',
                  borderRadius: 10, padding: '1px 7px',
                }}>
                  Iter {exp.iteration}
                </span>
              )}
            </div>
          </div>
          <button onClick={onDelete} className="btn btn-ghost btn-sm" title="Delete" style={{
            padding: '5px 7px', color: 'var(--score-low)',
            borderColor: 'rgba(224,85,85,0.2)', flexShrink: 0,
          }}>
            <Trash2 size={13} />
          </button>
        </div>
        {exp.confidence > 0 && (
          <div style={{ marginTop: 12 }}>
            <ScoreBar score={exp.confidence} height={5} />
          </div>
        )}
      </div>

      {/* Tabs */}
      <div style={{
        display: 'flex', borderBottom: '1px solid var(--glass-border)',
        flexShrink: 0, padding: '0 22px',
      }}>
        {TABS.map(tab => {
          const Icon   = tab.icon;
          const active = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '10px 14px', fontSize: 12,
                fontWeight: active ? 600 : 400,
                color: active ? 'var(--accent)' : 'var(--text-muted)',
                borderBottom: active ? '2px solid var(--accent)' : '2px solid transparent',
                background: 'transparent', border: 'none',
                cursor: 'pointer', transition: 'color 0.15s',
                marginBottom: -1,
              }}
            >
              <Icon size={12} /> {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div style={{ flex: 1, overflow: 'auto', padding: '20px 22px' }}>
        {activeTab === 'overview' && <OverviewTab exp={exp} />}
        {activeTab === 'results'  && <ResultsTab exp={exp} onAddResult={onAddResult} onComplete={onComplete} />}
        {activeTab === 'ai'       && (
          <AITab
            exp={exp}
            onSurrogate={onSurrogate} onSuggest={onSuggest}
            surrogate={surrogate} suggestions={suggestions} aiLoading={aiLoading}
          />
        )}
      </div>
    </div>
  );
}

// ── Overview tab ───────────────────────────────────────────────────────────────

function OverviewTab({ exp }) {
  const conditions = exp.conditions || {};
  const expected   = exp.expected_output || {};
  const candidates = exp.candidates || [];
  const reasoning  = exp.reasoning || exp.notes;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {exp.description && (
        <Block title="Description">
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', lineHeight: 1.75, margin: 0 }}>
            {exp.description}
          </p>
        </Block>
      )}

      {Object.values(conditions).some(Boolean) && (
        <Block title="Process Conditions">
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {Object.entries(conditions).filter(([, v]) => v).map(([k, v]) => (
              <div key={k} style={{
                padding: '7px 14px', background: 'var(--bg-overlay)',
                borderRadius: 'var(--r-sm)', border: '1px solid var(--glass-border)', fontSize: 12,
              }}>
                <span style={{ color: 'var(--text-muted)', textTransform: 'capitalize', marginRight: 6 }}>{k}:</span>
                <span style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>{v}</span>
              </div>
            ))}
          </div>
        </Block>
      )}

      {Object.keys(expected).length > 0 && (
        <Block title="Target Properties">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {Object.entries(expected).map(([key, val]) => {
              const v = typeof val === 'object' ? val : { value: val };
              return (
                <div key={key} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '9px 14px', background: 'var(--bg-overlay)',
                  borderRadius: 'var(--r-sm)', border: '1px solid var(--glass-border)',
                }}>
                  <Target size={11} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                  <span style={{ fontSize: 12, color: 'var(--text-primary)', flex: 1 }}>
                    {key.replace(/_/g, ' ')}
                  </span>
                  <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontWeight: 700 }}>
                    {v.value ?? '—'}{v.unit ? ` ${v.unit}` : ''}
                  </span>
                </div>
              );
            })}
          </div>
        </Block>
      )}

      {candidates.length > 0 && (
        <Block title={`Loop Candidates (${candidates.length})`}>
          {candidates.map((c, i) => (
            <div key={i} style={{
              padding: '12px 14px', background: 'var(--bg-overlay)',
              borderRadius: 'var(--r-md)', marginBottom: 8, border: '1px solid var(--glass-border)',
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                  {c.material_name || `Candidate ${i + 1}`}
                </span>
                {c.composite_score != null && (
                  <span style={{ fontSize: 12, fontFamily: 'var(--font-mono)', color: SCORE_COLOR(c.composite_score), fontWeight: 700 }}>
                    {Math.round(c.composite_score * 100)}%
                  </span>
                )}
              </div>
              {c.composite_score != null && <ScoreBar score={c.composite_score} />}
              {c.hypothesis && (
                <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: '8px 0 0', lineHeight: 1.55 }}>{c.hypothesis}</p>
              )}
            </div>
          ))}
        </Block>
      )}

      {reasoning && (
        <Block title="Reasoning / Notes">
          <p style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.75, margin: 0, fontStyle: 'italic' }}>
            {reasoning}
          </p>
        </Block>
      )}

      <Block title="Metadata">
        <div style={{ display: 'flex', flexDirection: 'column', gap: 5, fontSize: 11, color: 'var(--text-muted)' }}>
          {exp.created_at && (
            <div>
              <span style={{ marginRight: 8 }}>Created:</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{new Date(exp.created_at).toLocaleString()}</span>
            </div>
          )}
          <div>
            <span style={{ marginRight: 8 }}>ID:</span>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10 }}>{exp.id}</span>
          </div>
        </div>
      </Block>
    </div>
  );
}

// ── Results tab ────────────────────────────────────────────────────────────────

function ResultsTab({ exp, onAddResult, onComplete }) {
  const [showAdd, setShowAdd] = useState(false);
  const [row, setRow]         = useState({ metric_name: '', expected_value: '', actual_value: '', test_method: '', notes: '' });
  const [saving, setSaving]   = useState(false);

  const rawResults  = exp.results || [];
  const actual      = exp.actual_output || {};
  const isCompleted = exp.status === 'completed';

  const handleSave = async () => {
    if (!row.metric_name.trim()) return;
    setSaving(true);
    await onAddResult(row);
    setRow({ metric_name: '', expected_value: '', actual_value: '', test_method: '', notes: '' });
    setShowAdd(false);
    setSaving(false);
  };

  const inp = {
    flex: 1, minWidth: 0, padding: '7px 10px',
    background: 'var(--glass-bg)', border: '1px solid var(--glass-border)',
    borderRadius: 'var(--r-sm)', color: 'var(--text-primary)', fontSize: 12, outline: 'none',
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      {Object.keys(actual).length > 0 && (
        <Block title="Measured Output">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {Object.entries(actual).map(([k, v]) => {
              const val = typeof v === 'object' ? v.value : v;
              return (
                <div key={k} style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                  padding: '9px 14px', background: 'var(--bg-overlay)',
                  borderRadius: 'var(--r-sm)', border: '1px solid var(--glass-border)',
                }}>
                  <span style={{ fontSize: 12, color: 'var(--text-primary)' }}>{k.replace(/_/g, ' ')}</span>
                  <span style={{ fontSize: 14, fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--score-high)' }}>{val}</span>
                </div>
              );
            })}
          </div>
        </Block>
      )}

      {rawResults.length > 0 && (
        <Block title={`Test Results (${rawResults.length})`}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {rawResults.map((r, i) => {
              const exp_v    = r.expected_value ?? r.target ?? '';
              const act_v    = r.actual_value ?? r.actual ?? '';
              const deviation = (exp_v && act_v)
                ? (((parseFloat(act_v) - parseFloat(exp_v)) / parseFloat(exp_v)) * 100).toFixed(1)
                : null;
              const pass = deviation !== null ? Math.abs(parseFloat(deviation)) <= 10 : null;
              return (
                <div key={i} style={{
                  display: 'flex', gap: 12, alignItems: 'center',
                  padding: '11px 14px', background: 'var(--bg-overlay)',
                  borderRadius: 'var(--r-md)', border: '1px solid var(--glass-border)',
                  borderLeft: `3px solid ${pass === true ? 'var(--score-high)' : pass === false ? 'var(--score-low)' : 'var(--glass-border)'}`,
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
                      {r.metric_name || r.metric || 'Result'}
                    </div>
                    {r.test_method && <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{r.test_method}</div>}
                    {r.notes      && <div style={{ fontSize: 10, color: 'var(--text-muted)', fontStyle: 'italic', marginTop: 1 }}>{r.notes}</div>}
                  </div>
                  <div style={{ textAlign: 'right', flexShrink: 0 }}>
                    {exp_v && <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>Target: {exp_v}</div>}
                    {act_v && <div style={{ fontSize: 15, fontFamily: 'var(--font-mono)', fontWeight: 800, color: 'var(--text-primary)' }}>{act_v}</div>}
                    {deviation !== null && (
                      <div style={{ fontSize: 10, color: pass ? 'var(--score-high)' : 'var(--score-low)', fontWeight: 700, marginTop: 1 }}>
                        {parseFloat(deviation) > 0 ? '+' : ''}{deviation}% {pass ? '✓' : '✗'}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </Block>
      )}

      {rawResults.length === 0 && Object.keys(actual).length === 0 && !showAdd && (
        <div style={{
          textAlign: 'center', padding: '32px 0', color: 'var(--text-muted)', fontSize: 12,
          border: '1px dashed var(--glass-border)', borderRadius: 'var(--r-md)',
        }}>
          No results recorded yet. Add a result to track measured outcomes.
        </div>
      )}

      {showAdd && (
        <div style={{
          padding: 16, background: 'var(--bg-overlay)',
          borderRadius: 'var(--r-md)', border: '1px solid var(--glass-border)',
          display: 'flex', flexDirection: 'column', gap: 10,
        }}>
          <SectionLabel>Add Result</SectionLabel>
          <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 8 }}>
            <input type="text" placeholder="Metric name *" value={row.metric_name}
              onChange={e => setRow(r => ({ ...r, metric_name: e.target.value }))} style={inp} />
            <input type="text" placeholder="Target" value={row.expected_value}
              onChange={e => setRow(r => ({ ...r, expected_value: e.target.value }))} style={inp} />
            <input type="text" placeholder="Actual" value={row.actual_value}
              onChange={e => setRow(r => ({ ...r, actual_value: e.target.value }))} style={inp} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <input type="text" placeholder="Test method (e.g. ISO 527)" value={row.test_method}
              onChange={e => setRow(r => ({ ...r, test_method: e.target.value }))} style={inp} />
            <input type="text" placeholder="Notes" value={row.notes}
              onChange={e => setRow(r => ({ ...r, notes: e.target.value }))} style={inp} />
          </div>
          <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
            <button className="btn btn-ghost btn-sm" onClick={() => setShowAdd(false)}>Cancel</button>
            <button className="btn btn-primary btn-sm" onClick={handleSave}
              disabled={saving || !row.metric_name.trim()} style={{ gap: 5 }}>
              {saving ? <Loader size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Save size={12} />}
              Save Result
            </button>
          </div>
        </div>
      )}

      {!showAdd && (
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
          <button className="btn btn-ghost btn-sm" onClick={() => setShowAdd(true)} style={{ gap: 5 }}>
            <Plus size={12} /> Add Result
          </button>
          {!isCompleted && (rawResults.length > 0 || Object.keys(actual).length > 0) && (
            <button className="btn btn-primary btn-sm" onClick={onComplete} style={{ gap: 5 }}>
              <CheckCircle size={12} /> Mark Complete
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── AI tab ─────────────────────────────────────────────────────────────────────

function AITab({ exp, onSurrogate, onSuggest, surrogate, suggestions, aiLoading }) {
  const hasSurrogate = surrogate?.predictions && Object.keys(surrogate.predictions).length > 0;
  const nPts = surrogate?.n_training_points ?? 0;
  const modelType = surrogate?.model_type ?? 'GP';
  const schemaId = exp?.schema_id;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>

      {/* Surrogate Prediction */}
      <Block title="Surrogate Prediction">
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14, lineHeight: 1.65 }}>
          {schemaId
            ? 'Gaussian Process surrogate trained on literature + approved iterations predicts property values with uncertainty.'
            : 'No experiment schema linked. Run this experiment via the Research Loop with a schema selected to enable GP predictions.'}
        </p>

        {schemaId && (
          <button
            className="btn btn-ghost"
            onClick={onSurrogate}
            disabled={aiLoading === 'surrogate'}
            style={{ gap: 7 }}
          >
            {aiLoading === 'surrogate'
              ? <><Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> Loading…</>
              : <><Activity size={13} /> Get Surrogate Prediction</>}
          </button>
        )}

        {surrogate && (
          <div style={{ marginTop: 16 }}>
            {/* Model metadata */}
            <div style={{
              display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14,
              padding: '10px 14px', background: 'var(--bg-overlay)',
              borderRadius: 'var(--r-sm)', border: '1px solid var(--glass-border)',
            }}>
              <Database size={13} style={{ color: 'var(--accent)', flexShrink: 0 }} />
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
                {modelType} surrogate
              </span>
              <span style={{
                marginLeft: 'auto', fontSize: 11, fontFamily: 'var(--font-mono)',
                color: nPts >= 3 ? 'var(--score-high)' : 'var(--score-mid)',
              }}>
                {nPts} training {nPts === 1 ? 'point' : 'points'}
              </span>
              {nPts < 3 && (
                <span style={{
                  fontSize: 10, color: 'var(--score-mid)',
                  background: 'rgba(180,140,40,0.12)', border: '1px solid rgba(180,140,40,0.3)',
                  borderRadius: 8, padding: '1px 6px',
                }}>
                  Prior estimate
                </span>
              )}
            </div>

            {hasSurrogate ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {Object.entries(surrogate.predictions).map(([name, pred]) => (
                  <div key={name} style={{
                    padding: '12px 14px', background: 'var(--bg-overlay)',
                    borderRadius: 'var(--r-md)', border: '1px solid var(--glass-border)',
                  }}>
                    <div style={{
                      fontSize: 11, color: 'var(--text-muted)',
                      textTransform: 'uppercase', letterSpacing: '0.6px', marginBottom: 8,
                    }}>
                      {name.replace(/_/g, ' ')}
                    </div>
                    <UncertaintyBar
                      mean={pred?.mean ?? pred}
                      std={pred?.std ?? 0}
                      unit={pred?.unit ?? ''}
                      trained={pred?.trained !== false}
                    />
                  </div>
                ))}
              </div>
            ) : (
              <div style={{ fontSize: 12, color: 'var(--text-muted)', fontStyle: 'italic' }}>
                {surrogate.error || 'No predictions available — schema may not be linked.'}
              </div>
            )}
          </div>
        )}
      </Block>

      {/* Next configuration suggestion */}
      <Block title="Suggest Next Configuration">
        <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 14, lineHeight: 1.65 }}>
          Based on this experiment's formulation and literature, suggest the next most promising configuration.
        </p>
        <button className="btn btn-ghost" onClick={onSuggest} disabled={aiLoading === 'suggest'} style={{ gap: 7 }}>
          {aiLoading === 'suggest'
            ? <><Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> Generating…</>
            : <><Lightbulb size={13} /> Suggest Next</>}
        </button>

        {suggestions.length > 0 && (
          <div style={{ marginTop: 16, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {suggestions.map((s, i) => (
              <div key={i} style={{
                padding: '12px 14px', background: 'var(--bg-overlay)',
                borderRadius: 'var(--r-md)', border: '1px solid var(--glass-border)',
              }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 6 }}>
                  {s.material_name || s.name || `Suggestion ${i + 1}`}
                </div>
                <p style={{ fontSize: 11, color: 'var(--text-muted)', margin: 0, lineHeight: 1.55 }}>
                  {s.rationale || s.reasoning || JSON.stringify(s)}
                </p>
              </div>
            ))}
          </div>
        )}
      </Block>
    </div>
  );
}

// ── Create modal ───────────────────────────────────────────────────────────────

function CreateModal({ onSubmit, onClose }) {
  const [name, setName]               = useState('');
  const [material, setMaterial]       = useState('');
  const [description, setDescription] = useState('');
  const [conditions, setConditions]   = useState({ temperature: '', pressure: '', time: '', atmosphere: '' });
  const [selectedPreset, setPreset]   = useState('custom');
  const [props, setProps]             = useState([]);
  const [extraFields, setExtraFields] = useState([]);
  const [submitting, setSubmitting]   = useState(false);
  const backdropRef                   = useRef(null);

  const applyPreset = (key) => {
    setPreset(key);
    setProps(DOMAIN_PRESETS[key].props.map(p => ({ ...p })));
  };

  const addProp    = () => setProps(prev => [...prev, { name: '', unit: '', target: '', weight: '' }]);
  const removeProp = (i) => setProps(prev => prev.filter((_, idx) => idx !== i));
  const updateProp = (i, field, value) =>
    setProps(prev => prev.map((p, idx) => idx === i ? { ...p, [field]: value } : p));

  const addExtra    = () => setExtraFields(prev => [...prev, { key: '', value: '' }]);
  const removeExtra = (i) => setExtraFields(prev => prev.filter((_, idx) => idx !== i));
  const updateExtra = (i, field, value) =>
    setExtraFields(prev => prev.map((f, idx) => idx === i ? { ...f, [field]: value } : f));

  const handleBackdropClick = (e) => {
    if (e.target === backdropRef.current) onClose();
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    setSubmitting(true);

    const expected_output  = {};
    const property_weights = {};
    props.forEach(p => {
      if (p.name.trim()) {
        const key = p.name.trim().replace(/\s+/g, '_').toLowerCase();
        if (p.target) expected_output[key] = { value: parseFloat(p.target) || p.target, unit: p.unit };
        if (p.weight) property_weights[key] = parseFloat(p.weight) || 0;
      }
    });

    const extraConditions = {};
    extraFields.forEach(f => { if (f.key.trim()) extraConditions[f.key.trim()] = f.value; });

    await onSubmit({
      name: name.trim(),
      material_name: material || null,
      description: description || null,
      conditions: {
        temperature: conditions.temperature || null,
        pressure:    conditions.pressure    || null,
        time:        conditions.time        || null,
        atmosphere:  conditions.atmosphere  || null,
        ...extraConditions,
      },
      expected_output,
      property_weights,
    });
    setSubmitting(false);
  };

  const inp = {
    width: '100%', boxSizing: 'border-box', padding: '9px 11px',
    background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)',
    borderRadius: 'var(--r-sm)', color: 'var(--text-primary)', fontSize: 13, outline: 'none',
  };
  const lbl = {
    display: 'block', fontSize: 10, color: 'var(--text-muted)',
    marginBottom: 5, textTransform: 'uppercase', letterSpacing: '0.6px', fontWeight: 600,
  };

  return (
    <div
      ref={backdropRef}
      onClick={handleBackdropClick}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(7,9,15,0.78)', backdropFilter: 'blur(8px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, padding: 24,
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          width: '100%', maxWidth: 680,
          background: 'var(--bg-surface)', border: '1px solid var(--glass-border)',
          borderRadius: 'var(--r-lg)', display: 'flex', flexDirection: 'column',
          maxHeight: '90vh', overflow: 'hidden',
          boxShadow: '0 24px 64px rgba(0,0,0,0.6), 0 0 0 1px rgba(109,106,248,0.14)',
        }}
      >
        {/* Modal header */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: 12,
          padding: '18px 24px', borderBottom: '1px solid var(--glass-border)', flexShrink: 0,
        }}>
          <div style={{
            width: 34, height: 34, borderRadius: 'var(--r-sm)',
            background: 'linear-gradient(135deg, var(--accent), var(--accent-dim))',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            boxShadow: '0 0 16px var(--accent-glow)', flexShrink: 0,
          }}>
            <Beaker size={16} style={{ color: '#fff' }} />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--text-primary)' }}>New Experiment</div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>Define your configuration, conditions, and targets</div>
          </div>
          <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}
            style={{ marginLeft: 'auto', padding: '5px 7px' }}>
            <X size={14} />
          </button>
        </div>

        {/* Scrollable fields */}
        <div style={{ flex: 1, overflow: 'auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 20 }}>

          {/* Name + material */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
            <div>
              <label style={lbl}>Experiment Name *</label>
              <input type="text" required placeholder="e.g., MXene-Epoxy 3wt% at 180°C"
                value={name} onChange={e => setName(e.target.value)} style={inp} />
            </div>
            <div>
              <label style={lbl}>Material System</label>
              <input type="text" placeholder="e.g., Ti₃C₂Tₓ / DGEBA Epoxy"
                value={material} onChange={e => setMaterial(e.target.value)} style={inp} />
            </div>
          </div>

          {/* Description */}
          <div>
            <label style={lbl}>Description</label>
            <textarea
              placeholder="Describe the objective, rationale, or hypothesis…"
              value={description} onChange={e => setDescription(e.target.value)}
              rows={2}
              style={{ ...inp, resize: 'vertical', fontFamily: 'inherit', lineHeight: 1.6 }}
            />
          </div>

          {/* Standard conditions */}
          <div>
            <label style={lbl}>Process Conditions</label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10 }}>
              {[
                { key: 'temperature', ph: 'Temp (°C)' },
                { key: 'pressure',    ph: 'Pressure (bar)' },
                { key: 'time',        ph: 'Time (min)' },
                { key: 'atmosphere',  ph: 'Atmosphere' },
              ].map(({ key, ph }) => (
                <input key={key} type="text" placeholder={ph}
                  value={conditions[key]}
                  onChange={e => setConditions(c => ({ ...c, [key]: e.target.value }))}
                  style={inp}
                />
              ))}
            </div>
          </div>

          {/* Extra custom condition fields */}
          {extraFields.length > 0 && (
            <div>
              <label style={lbl}>Custom Conditions</label>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
                {extraFields.map((f, i) => (
                  <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <input type="text" placeholder="Field name" value={f.key}
                      onChange={e => updateExtra(i, 'key', e.target.value)}
                      style={{ ...inp, flex: '0 0 160px', width: 'auto' }} />
                    <input type="text" placeholder="Value" value={f.value}
                      onChange={e => updateExtra(i, 'value', e.target.value)}
                      style={{ ...inp, flex: 1, width: 'auto' }} />
                    <button type="button" className="btn btn-ghost btn-sm"
                      onClick={() => removeExtra(i)} style={{ padding: '5px 7px', flexShrink: 0 }}>
                      <X size={12} />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
          <button type="button" onClick={addExtra} className="btn btn-ghost btn-sm"
            style={{ width: 'fit-content', gap: 5, marginTop: -8 }}>
            <Plus size={11} /> Add custom condition
          </button>

          {/* Target properties */}
          <div style={{ borderTop: '1px solid var(--glass-border)', paddingTop: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
              <SlidersHorizontal size={13} style={{ color: 'var(--accent)' }} />
              <span style={{ ...lbl, margin: 0 }}>Target Properties</span>
            </div>

            {/* Preset pills */}
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
              {Object.entries(DOMAIN_PRESETS).map(([key, p]) => {
                const active = selectedPreset === key;
                return (
                  <button
                    key={key} type="button" onClick={() => applyPreset(key)}
                    style={{
                      padding: '6px 12px', fontSize: 11, fontWeight: 600,
                      border: `1px solid ${active ? 'var(--accent)' : 'var(--glass-border)'}`,
                      borderRadius: 'var(--r-sm)',
                      background: active ? 'var(--glass-active)' : 'var(--bg-overlay)',
                      color: active ? 'var(--accent)' : 'var(--text-muted)',
                      cursor: 'pointer', transition: 'all 0.12s',
                    }}
                  >
                    {p.icon} {p.label}
                  </button>
                );
              })}
            </div>

            {selectedPreset !== 'custom' && (
              <p style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 12, lineHeight: 1.55 }}>
                {DOMAIN_PRESETS[selectedPreset].description}. Adjust targets and weights or add more rows.
              </p>
            )}

            {/* Property rows */}
            {props.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '2fr 0.65fr 0.85fr 0.65fr 28px', gap: 6, marginBottom: 5 }}>
                  {['Property', 'Unit', 'Target', 'Weight', ''].map((h, i) => (
                    <span key={i} style={{ fontSize: 9, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{h}</span>
                  ))}
                </div>
                {props.map((p, i) => (
                  <div key={i} style={{ display: 'grid', gridTemplateColumns: '2fr 0.65fr 0.85fr 0.65fr 28px', gap: 6, marginBottom: 6 }}>
                    <input type="text" placeholder="property_name" value={p.name}
                      onChange={e => updateProp(i, 'name', e.target.value)} style={{ ...inp, padding: '7px 9px' }} />
                    <input type="text" placeholder="MPa" value={p.unit}
                      onChange={e => updateProp(i, 'unit', e.target.value)} style={{ ...inp, padding: '7px 9px' }} />
                    <input type="text" placeholder="target" value={p.target}
                      onChange={e => updateProp(i, 'target', e.target.value)} style={{ ...inp, padding: '7px 9px' }} />
                    <input type="text" placeholder="0.50" value={p.weight}
                      onChange={e => updateProp(i, 'weight', e.target.value)} style={{ ...inp, padding: '7px 9px' }} />
                    <button type="button" onClick={() => removeProp(i)} className="btn btn-ghost btn-sm"
                      style={{ padding: '5px 6px' }}>
                      <X size={11} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <button type="button" onClick={addProp} className="btn btn-ghost btn-sm" style={{ gap: 5 }}>
              <Plus size={12} /> Add property row
            </button>
          </div>
        </div>

        {/* Footer */}
        <div style={{
          display: 'flex', gap: 10, justifyContent: 'flex-end',
          padding: '16px 24px', borderTop: '1px solid var(--glass-border)',
          background: 'var(--bg-surface)', flexShrink: 0,
        }}>
          <button type="button" onClick={onClose} className="btn btn-ghost">Cancel</button>
          <button type="submit" disabled={submitting || !name.trim()} className="btn btn-primary" style={{ gap: 7 }}>
            {submitting ? <Loader size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <FlaskConical size={13} />}
            Create Experiment
          </button>
        </div>
      </form>
    </div>
  );
}
