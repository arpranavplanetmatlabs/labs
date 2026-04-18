import { useState, useEffect, useRef, useCallback } from 'react';
import './index.css';
import Sidebar from './components/Sidebar';
import GoalPanel from './components/GoalPanel';
import KnowledgePanel from './components/KnowledgePanel';
import ExperimentDashboard from './components/ExperimentDashboard';
import ResultsPanel from './components/ResultsPanel';
import DecisionPanel from './components/DecisionPanel';
import PapersView from './components/PapersView';
import ExperimentsPanel from './components/ExperimentsPanel';
import ChatPanel from './components/ChatPanel';
import SettingsPanel from './components/SettingsPanel';

const API_BASE = 'http://localhost:8000';

export default function App() {
  const [activeNav, setActiveNav] = useState('research');
  const [selectedExp, setSelectedExp] = useState(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(
    () => localStorage.getItem('sidebar-collapsed') === 'true'
  );

  const handleToggleCollapse = useCallback(() => {
    setSidebarCollapsed(prev => {
      const next = !prev;
      localStorage.setItem('sidebar-collapsed', String(next));
      return next;
    });
  }, []);
  const [counts, setCounts] = useState({ documents: 0, tds: 0, papers: 0, experiments: 0, qdrant_parsed: 0 });
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [loopState, setLoopState] = useState(null);   // null = not yet fetched
  const [loopLoading, setLoopLoading] = useState(false);
  const loopLoadingRef = useRef(false);

  // ── Polling ────────────────────────────────────────────────────────────────

  useEffect(() => {
    fetchStats();
    fetchLoopStatus();
    const statsInterval = setInterval(fetchStats, 30000);
    const loopInterval = setInterval(fetchLoopStatus, 10000);
    return () => {
      clearInterval(statsInterval);
      clearInterval(loopInterval);
    };
  }, []);

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/stats`);
      if (res.ok) setCounts(await res.json());
    } catch (_) {}
  };

  const fetchLoopStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/loop/status`);
      if (res.ok) setLoopState(await res.json());
    } catch (_) {}
  };

  // ── View metadata ──────────────────────────────────────────────────────────

  const VIEW_META = {
    research: { title: 'Research Workspace', subtitle: 'Goal · Knowledge · Experiments · Results · Decisions' },
    papers:   { title: 'Papers & TDS Library', subtitle: `${counts.documents} documents indexed` },
    experiments: { title: 'Experiment History', subtitle: `${counts.experiments} experiments` },
    results:  { title: 'Results & Metrics', subtitle: 'Comparative analysis across iterations' },
    decisions: { title: 'Decision Log', subtitle: 'Review and approve experiment decisions' },
    chat:     { title: 'Materials Chat', subtitle: 'AI-powered Q&A with RAG' },
  };
  const meta = VIEW_META[activeNav] || VIEW_META.research;

  // ── Loop handlers ──────────────────────────────────────────────────────────

  const handleToggleLoop = useCallback(async ({ active, goal, weights, schema_id }) => {
    if (!active) {
      await handleStopLoop();
      return;
    }
    setLoopLoading(true);
    loopLoadingRef.current = true;
    try {
      const res = await fetch(`${API_BASE}/api/loop/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal, weights, schema_id: schema_id || null }),
      });
      if (res.ok) setLoopState(await res.json());
    } catch (e) {
      console.error('Loop start error:', e);
    } finally {
      setLoopLoading(false);
      loopLoadingRef.current = false;
    }
  }, []);

  const handleRunIteration = useCallback(async ({ goal, weights, schema_id }) => {
    setLoopLoading(true);
    loopLoadingRef.current = true;
    const endpoint = (!loopState || loopState.status === 'idle' || loopState.status === 'stopped')
      ? `${API_BASE}/api/loop/start`
      : `${API_BASE}/api/loop/iterate`;
    try {
      const res = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal, weights, schema_id: schema_id || null }),
      });
      if (res.ok) setLoopState(await res.json());
    } catch (e) {
      console.error('Iteration error:', e);
    } finally {
      setLoopLoading(false);
      loopLoadingRef.current = false;
    }
  }, [loopState]);

  const handleApprove = useCallback(async () => {
    setLoopLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/loop/approve`, { method: 'POST' });
      if (res.ok) setLoopState(await res.json());
    } catch (e) {
      console.error('Approve error:', e);
    } finally {
      setLoopLoading(false);
    }
  }, []);

  const handleStopLoop = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/loop/stop`, { method: 'POST' });
      if (res.ok) setLoopState(await res.json());
    } catch (e) {
      console.error('Stop error:', e);
    }
  }, []);

  const handleEditHypothesis = useCallback(async (hypothesis) => {
    try {
      const res = await fetch(`${API_BASE}/api/loop/hypothesis`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hypothesis }),
      });
      if (res.ok) fetchLoopStatus();
    } catch (e) {
      console.error('Edit hypothesis error:', e);
    }
  }, []);

  const handleExport = () => {
    const data = { timestamp: new Date().toISOString(), loopState, counts };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `decision-log-${Date.now()}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="app-shell">
      <Sidebar
        active={activeNav}
        onNav={setActiveNav}
        counts={counts}
        collapsed={sidebarCollapsed}
        onToggleCollapse={handleToggleCollapse}
        onOpenSettings={() => setSettingsOpen(true)}
      />
      {settingsOpen && <SettingsPanel onClose={() => setSettingsOpen(false)} />}

      <div className="main-content">
        <div className="topbar">
          <div>
            <div className="topbar-title">{meta.title}</div>
            <div className="topbar-subtitle">{meta.subtitle}</div>
          </div>
          <div className="topbar-actions">
            <IterBadge loopState={loopState} loading={loopLoading} />
            <button className="btn btn-ghost btn-sm" title="Export decision log" onClick={handleExport}>
              Export
            </button>
          </div>
        </div>

        <div className="workspace">
          <div key={activeNav} className="view-transition">
          {activeNav === 'research' && (
            <ResearchView
              loopState={loopState}
              loopLoading={loopLoading}
              onSelectExp={setSelectedExp}
              selectedExp={selectedExp}
              onToggleLoop={handleToggleLoop}
              onRunIteration={handleRunIteration}
              onApprove={handleApprove}
              onEditHypothesis={handleEditHypothesis}
              onStopLoop={handleStopLoop}
            />
          )}
          {activeNav === 'papers'      && <PapersView />}
          {activeNav === 'experiments' && <ExperimentsView />}
          {activeNav === 'results'     && <ResultsOnlyView />}
          {activeNav === 'decisions'   && (
            <DecisionsView
              loopState={loopState}
              loopLoading={loopLoading}
              onApprove={handleApprove}
              onEditHypothesis={handleEditHypothesis}
              onStopLoop={handleStopLoop}
            />
          )}
          {activeNav === 'chat'        && <ChatView />}
          </div>
        </div>
      </div>
    </div>
  );
}

// ── View layouts ──────────────────────────────────────────────────────────────

function ResearchView({ loopState, loopLoading, onSelectExp, selectedExp, onToggleLoop, onRunIteration, onApprove, onEditHypothesis, onStopLoop }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--pad-md)', height: '100%', overflow: 'hidden' }}>
      <GoalPanel
        loopState={loopState}
        loopLoading={loopLoading}
        onToggleLoop={onToggleLoop}
        onRunIteration={onRunIteration}
      />
      <div style={{ display: 'flex', gap: 'var(--pad-md)', flex: '1 1 0', minHeight: 0, overflow: 'hidden' }}>
        <div style={{ flex: '0 0 320px', overflow: 'hidden' }}>
          <KnowledgePanel />
        </div>
        <div style={{ flex: '1 1 0', overflow: 'hidden' }}>
          <ExperimentDashboard loopState={loopState} onSelect={onSelectExp} />
        </div>
      </div>
      <div style={{ display: 'flex', gap: 'var(--pad-md)', flex: '1 1 0', minHeight: 0, overflow: 'hidden' }}>
        <div style={{ flex: '1 1 0', overflow: 'hidden' }}>
          <ResultsPanel selectedExp={selectedExp} loopState={loopState} />
        </div>
        <div style={{ flex: '1 1 0', overflow: 'hidden' }}>
          <DecisionPanel
            loopState={loopState}
            loopLoading={loopLoading}
            onApprove={onApprove}
            onEditHypothesis={onEditHypothesis}
            onStopLoop={onStopLoop}
          />
        </div>
      </div>
    </div>
  );
}

function ExperimentsView() {
  return (
    <div style={{ height: '100%', overflow: 'hidden' }}>
      <ExperimentsPanel />
    </div>
  );
}

function ResultsOnlyView() {
  return <div style={{ height: '100%', overflow: 'hidden' }}><ResultsPanel /></div>;
}

function DecisionsView({ loopState, loopLoading, onApprove, onEditHypothesis, onStopLoop }) {
  return (
    <div style={{ display: 'flex', gap: 'var(--pad-md)', height: '100%', overflow: 'hidden' }}>
      <div style={{ flex: '1 1 0', overflow: 'hidden' }}>
        <DecisionPanel
          loopState={loopState}
          loopLoading={loopLoading}
          onApprove={onApprove}
          onEditHypothesis={onEditHypothesis}
          onStopLoop={onStopLoop}
        />
      </div>
      <div style={{ flex: '0 0 340px', overflow: 'hidden' }}>
        <KnowledgePanel />
      </div>
    </div>
  );
}

function ChatView() {
  return <div style={{ height: '100%', overflow: 'hidden' }}><ChatPanel /></div>;
}

// ── IterBadge ─────────────────────────────────────────────────────────────────

function IterBadge({ loopState, loading }) {
  const iter   = loopState?.iteration ?? 0;
  const status = loopState?.status ?? 'idle';

  const statusColor = {
    running:            'var(--score-high)',
    awaiting_approval:  'var(--accent)',
    stopped:            'var(--text-muted)',
    idle:               'var(--text-muted)',
  }[status] ?? 'var(--text-muted)';

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 6,
      background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)',
      borderRadius: 'var(--r-md)', padding: '4px 12px', fontSize: 12,
    }}>
      {loading && <span style={{ color: 'var(--accent)', animation: 'pulse 1s ease-in-out infinite' }}>⟳</span>}
      <span style={{ color: 'var(--text-muted)' }}>Loop</span>
      <span style={{ fontFamily: 'var(--font-mono)', color: statusColor, fontWeight: 700 }}>
        {loading ? 'Running…' : iter > 0 ? `Iter ${iter}` : 'Idle'}
      </span>
      {status === 'awaiting_approval' && !loading && (
        <span style={{ fontSize: 10, color: 'var(--accent)', fontWeight: 600 }}>▲ Awaiting</span>
      )}
    </div>
  );
}
