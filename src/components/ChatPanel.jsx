import { useState, useEffect, useRef } from 'react';
import { MessageSquare, Send, Trash2, FileText, Loader, Settings, Plus, X, ShieldCheck, Clock, ChevronRight, Globe } from 'lucide-react';
import CyberLoader from './CyberLoader';

const API_BASE = 'http://localhost:8000';

const ROLES = [
  { id: 'material-expert',       label: 'Material Expert',      description: 'Technical analysis and comparisons' },
  { id: 'technical-reviewer',    label: 'Technical Reviewer',   description: 'Quality assurance and compliance' },
  { id: 'literature-researcher', label: 'Literature Researcher',description: 'Academic synthesis and research' },
  { id: 'document-parser',       label: 'Doc Parser',           description: 'Audit extraction quality — flags wrong units, missing values, implausible data' },
  { id: 'compliance-auditor',    label: 'Compliance Auditor',   description: 'Standards audit with ⚠️ deviation flags' },
];


export default function ChatPanel() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState('default');
  const [role, setRole] = useState('material-expert');
  const [complianceStandard, setComplianceStandard] = useState('');
  const [showComplianceManager, setShowComplianceManager] = useState(false);
  const [complianceStandards, setComplianceStandards] = useState([]);
  const [sessions, setSessions] = useState([]);
  const [deletingSession, setDeletingSession] = useState(null);
  const [forceWebSearch, setForceWebSearch] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    fetchSessions();
    fetchHistory();
    fetchComplianceStandards();
  }, [sessionId]);

  const fetchComplianceStandards = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/compliance`);
      if (res.ok) {
        const data = await res.json();
        setComplianceStandards(data.standards || []);
      }
    } catch (_) {}
  };

  const fetchSessions = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/chat/sessions`);
      if (res.ok) {
        const data = await res.json();
        setSessions(data.sessions || []);
      }
    } catch (err) {
      console.error('Failed to fetch sessions:', err);
    }
  };

  const fetchHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/chat/sessions/${sessionId}/history?limit=20`);
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages || []);
      }
    } catch (err) {
      console.error('Failed to fetch history:', err);
    }
  };

  const handleSend = async () => {
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setLoading(true);

    setMessages(prev => [...prev, { role: 'user', content: userMessage, timestamp: new Date().toISOString() }]);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 120_000); // 2 min hard cap

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        signal: controller.signal,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage,
          role: role,
          session_id: sessionId,
          include_context: true,
          compliance_standard: role === 'compliance-auditor' ? complianceStandard : '',
          force_web_search: forceWebSearch,
        })
      });
      clearTimeout(timeoutId);

      if (res.ok) {
        const data = await res.json();
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: data.response, sources: data.sources, web_used: data.web_used, timestamp: new Date().toISOString() }
        ]);
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: 'Error: Failed to get response', timestamp: new Date().toISOString() }]);
      }
    } catch (err) {
      clearTimeout(timeoutId);
      const msg = err.name === 'AbortError'
        ? 'Request timed out — the model is taking too long. Try a shorter question or restart the backend.'
        : 'Error: ' + err.message;
      setMessages(prev => [...prev, { role: 'assistant', content: msg, timestamp: new Date().toISOString() }]);
    }

    setLoading(false);
  };

  const handleNewSession = () => {
    const newId = 'session-' + Date.now();
    setSessionId(newId);
    setMessages([]);
    fetchSessions();
  };

  const switchSession = (sid) => {
    if (sid === sessionId) return;
    setSessionId(sid);
    setMessages([]); // cleared, useEffect re-fetches via fetchHistory
  };

  const deleteSession = async (sid, e) => {
    e.stopPropagation();
    if (!confirm('Delete this session? Cannot be undone.')) return;
    setDeletingSession(sid);
    try {
      await fetch(`${API_BASE}/api/chat/sessions/${encodeURIComponent(sid)}`, { method: 'DELETE' });
      if (sid === sessionId) {
        // Switch to default or the next available session
        const remaining = sessions.filter(s => s.session_id !== sid);
        const next = remaining[0]?.session_id || 'default';
        setSessionId(next);
        setMessages([]);
      }
      await fetchSessions();
    } catch (err) {
      console.error('Failed to delete session:', err);
    } finally {
      setDeletingSession(null);
    }
  };

  const handleClearSession = async () => {
    if (!confirm('Clear this chat session? This cannot be undone.')) return;
    try {
      await fetch(`${API_BASE}/api/chat/sessions/${encodeURIComponent(sessionId)}`, { method: 'DELETE' });
      setMessages([]);
      fetchSessions();
    } catch (err) {
      console.error('Failed to clear session:', err);
    }
  };

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <>
      <div style={{ display: 'flex', height: '100%', gap: 0, overflow: 'hidden' }}>

        {/* ── Session list column ─────────────────────────────────────── */}
        <div style={{
          width: 200, flexShrink: 0,
          display: 'flex', flexDirection: 'column',
          background: 'var(--bg-card)',
          border: '1px solid var(--glass-border)',
          borderRadius: 'var(--r-lg) 0 0 var(--r-lg)',
          overflow: 'hidden',
        }}>
          {/* Session list header */}
          <div style={{
            padding: '10px 12px',
            borderBottom: '1px solid var(--glass-border)',
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <span style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
              Sessions
            </span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={handleNewSession}
              title="New session"
              style={{ padding: '3px 6px' }}
            >
              <Plus size={12} />
            </button>
          </div>

          {/* Session entries */}
          <div style={{ flex: 1, overflow: 'auto', padding: '6px 0' }}>
            {sessions.length === 0 && (
              <div style={{ padding: '12px', fontSize: 11, color: 'var(--text-muted)', textAlign: 'center' }}>
                No saved sessions
              </div>
            )}
            {sessions.map(s => (
              <SessionEntry
                key={s.session_id}
                session={s}
                active={s.session_id === sessionId}
                deleting={deletingSession === s.session_id}
                onClick={() => switchSession(s.session_id)}
                onDelete={(e) => deleteSession(s.session_id, e)}
              />
            ))}
          </div>
        </div>

        {/* ── Chat column ─────────────────────────────────────────────── */}
      <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', flex: 1, borderRadius: '0 var(--r-lg) var(--r-lg) 0', borderLeft: 'none' }}>
        <div className="panel-header">
          <MessageSquare size={14} style={{ color: 'var(--accent)' }} />
          <span className="panel-title">
            {sessionId === 'default' ? 'Materials Chat' : sessionId.replace('session-', 'Session ')}
          </span>
          <button className="btn btn-ghost btn-sm" onClick={handleClearSession} title="Delete this session">
            <Trash2 size={12} />
          </button>
        </div>

        <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--glass-border)' }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6 }}>Role:</div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {ROLES.map(r => (
              <button
                key={r.id}
                className={`btn btn-sm ${role === r.id ? 'btn-primary' : 'btn-secondary'}`}
                onClick={() => setRole(r.id)}
                style={{ fontSize: 10, padding: '4px 8px' }}
                title={r.description}
              >
                {r.label}
              </button>
            ))}
          </div>
          {role === 'compliance-auditor' && (
            <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
              <ShieldCheck size={11} style={{ color: 'var(--accent)', flexShrink: 0 }} />
              <span style={{ fontSize: 10, color: 'var(--text-muted)', flexShrink: 0 }}>Standard:</span>
              <select
                value={complianceStandard}
                onChange={e => setComplianceStandard(e.target.value)}
                style={{
                  flex: 1,
                  background: 'var(--glass-bg)',
                  border: '1px solid var(--glass-border)',
                  borderRadius: 'var(--r-sm)',
                  color: 'var(--text-primary)',
                  fontSize: 11,
                  padding: '4px 8px',
                  cursor: 'pointer',
                }}
              >
                <option value="" style={{ background: 'var(--bg-base)' }}>Auto-detect</option>
                {complianceStandards.filter(s => s.key).map(s => (
                  <option key={s.key} value={s.key} style={{ background: 'var(--bg-base)' }}>
                    {s.display}{s.is_builtin ? '' : ' ✦'}
                  </option>
                ))}
              </select>
              <button
                className="btn btn-ghost btn-sm"
                onClick={() => setShowComplianceManager(true)}
                title="Manage compliance standards"
                style={{ padding: '4px 6px', flexShrink: 0 }}
              >
                <Settings size={12} />
              </button>
            </div>
          )}
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
          {messages.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
              <MessageSquare size={32} style={{ marginBottom: 12, opacity: 0.5 }} />
              <div style={{ fontSize: 13 }}>Ask about materials</div>
              <div style={{ fontSize: 11, marginTop: 4, color: 'var(--text-muted)' }}>
                {role === 'compliance-auditor'
                  ? 'Audits documents against ISO, ASTM, IEC, or nanocomposite reporting standards'
                  : 'Answers grounded in your indexed document library'}
              </div>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div key={i} style={{ marginBottom: 12 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                  <span style={{
                    fontSize: 10,
                    color: msg.role === 'user' ? 'var(--accent)' : 'var(--text-muted)',
                    textTransform: 'uppercase',
                    fontWeight: 600
                  }}>
                    {msg.role === 'user' ? 'You' : 'AI'}
                  </span>
                  {msg.web_used && (
                    <span title="Web search was used for this response" style={{
                      fontSize: 10,
                      background: 'rgba(59,130,246,0.2)',
                      border: '1px solid rgba(59,130,246,0.4)',
                      borderRadius: 4,
                      padding: '1px 5px',
                      color: '#60a5fa',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 3,
                    }}>
                      <Globe size={9} /> Web
                    </span>
                  )}
                </div>
                <div style={{
                  padding: '10px 14px',
                  borderRadius: 'var(--r-md)',
                  background: msg.role === 'user' ? 'var(--glass-active)' : 'var(--glass-bg)',
                  border: '1px solid var(--glass-border)',
                  fontSize: 13,
                  lineHeight: 1.5,
                  whiteSpace: 'pre-wrap'
                }}>
                  {msg.content}
                </div>
                {msg.sources && msg.sources.length > 0 && (
                  <SourcePills sources={msg.sources} />
                )}
              </div>
            ))
          )}
          {loading && <ThinkingIndicator />}
          <div ref={messagesEndRef} />
        </div>

        <div style={{ padding: 12, borderTop: '1px solid var(--glass-border)' }}>
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              type="text"
              placeholder="Ask about materials..."
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSend()}
              disabled={loading}
              style={{
                flex: 1,
                background: 'var(--glass-bg)',
                border: '1px solid var(--glass-border)',
                borderRadius: 'var(--r-md)',
                padding: '8px 12px',
                color: 'var(--text-primary)',
                fontSize: 13,
              }}
            />
            <button
              title={forceWebSearch ? 'Web search ON — will always search online' : 'Web search OFF — AI decides'}
              onClick={() => setForceWebSearch(v => !v)}
              style={{
                background: forceWebSearch ? 'var(--accent, #3b82f6)' : 'transparent',
                border: `1px solid ${forceWebSearch ? 'var(--accent, #3b82f6)' : 'rgba(255,255,255,0.2)'}`,
                borderRadius: '6px',
                padding: '6px 8px',
                cursor: 'pointer',
                color: forceWebSearch ? '#fff' : 'rgba(255,255,255,0.5)',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                fontSize: '11px',
              }}
            >
              <Globe size={13} />
              {forceWebSearch && <span>Web</span>}
            </button>
            <button
              className="btn btn-primary"
              onClick={handleSend}
              disabled={loading || !input.trim()}
            >
              <Send size={14} />
            </button>
          </div>
        </div>
      </div>{/* end glass-panel / chat column */}
      </div>{/* end session+chat row */}

      {showComplianceManager && (
        <ComplianceManagerModal
          standards={complianceStandards}
          onClose={() => { setShowComplianceManager(false); fetchComplianceStandards(); }}
        />
      )}
    </>
  );
}


// ── Session Entry ─────────────────────────────────────────────────────────────

function relativeTime(iso) {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1)  return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function SessionEntry({ session, active, deleting, onClick, onDelete }) {
  const label = session.first_message
    ? session.first_message.slice(0, 40) + (session.first_message.length > 40 ? '…' : '')
    : session.session_id === 'default' ? 'Default' : session.session_id.replace('session-', '#');

  return (
    <div
      onClick={onClick}
      style={{
        position: 'relative',
        padding: '8px 10px',
        margin: '0 6px 2px',
        borderRadius: 'var(--r-sm)',
        cursor: 'pointer',
        background: active ? 'var(--glass-active)' : 'transparent',
        border: `1px solid ${active ? 'var(--accent-dim)' : 'transparent'}`,
        transition: 'background 0.15s, border-color 0.15s',
        display: 'flex', flexDirection: 'column', gap: 3,
      }}
      onMouseEnter={e => { if (!active) e.currentTarget.style.background = 'var(--glass-hover)'; }}
      onMouseLeave={e => { if (!active) e.currentTarget.style.background = 'transparent'; }}
    >
      {/* Active indicator */}
      {active && (
        <div style={{
          position: 'absolute', left: 0, top: '50%', transform: 'translateY(-50%)',
          width: 2, height: 20, background: 'var(--accent)', borderRadius: 2,
        }} />
      )}

      <div style={{ fontSize: 11, color: active ? 'var(--text-primary)' : 'var(--text-secondary)', fontWeight: active ? 600 : 400, lineHeight: 1.3, paddingRight: 18 }}>
        {label}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          {session.message_count} msg
        </span>
        {session.last_active && (
          <>
            <span style={{ fontSize: 10, color: 'var(--glass-border)' }}>·</span>
            <span style={{ fontSize: 10, color: 'var(--text-muted)' }}>
              {relativeTime(session.last_active)}
            </span>
          </>
        )}
      </div>

      {/* Delete button */}
      <button
        onClick={onDelete}
        disabled={deleting}
        title="Delete session"
        style={{
          position: 'absolute', right: 6, top: '50%', transform: 'translateY(-50%)',
          background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--text-muted)', padding: 3, borderRadius: 4,
          opacity: 0.6,
          display: 'flex', alignItems: 'center',
        }}
        onMouseEnter={e => { e.currentTarget.style.color = 'var(--score-low)'; e.currentTarget.style.opacity = '1'; }}
        onMouseLeave={e => { e.currentTarget.style.color = 'var(--text-muted)'; e.currentTarget.style.opacity = '0.6'; }}
      >
        {deleting ? <Loader size={10} style={{ animation: 'spin 1s linear infinite' }} /> : <Trash2 size={10} />}
      </button>
    </div>
  );
}


// ── Thinking Indicator ────────────────────────────────────────────────────────

function ThinkingIndicator() {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const id = setInterval(() => setElapsed(s => s + 1), 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      color: 'var(--text-muted)', marginBottom: 8,
    }}>
      <Loader size={13} style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }} />
      <span style={{ fontSize: 12 }}>
        Thinking
        <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', marginLeft: 6 }}>
          {elapsed}s
        </span>
        {elapsed >= 20 && (
          <span style={{ marginLeft: 6, color: 'var(--text-muted)', fontSize: 11 }}>
            — local model is working, please wait…
          </span>
        )}
      </span>
    </div>
  );
}


// ── Source Pills (6F) ─────────────────────────────────────────────────────────

function SourcePills({ sources }) {
  const [expandedIdx, setExpandedIdx] = useState(null);

  const scoreColor = (s) => {
    if (s >= 0.8) return 'var(--score-high)';
    if (s >= 0.5) return 'var(--score-mid)';
    return 'var(--score-low)';
  };

  return (
    <div style={{ marginTop: 8 }}>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, fontWeight: 600 }}>
        Sources ({sources.length})
      </div>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
        {sources.map((s, i) => {
          const isOpen = expandedIdx === i;
          return (
            <div key={i} style={{ maxWidth: '100%' }}>
              <button
                onClick={() => setExpandedIdx(isOpen ? null : i)}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  padding: '3px 8px',
                  background: isOpen ? 'var(--glass-active)' : 'var(--glass-bg)',
                  border: `1px solid ${isOpen ? 'var(--accent-dim)' : 'var(--glass-border)'}`,
                  borderRadius: 5, cursor: 'pointer',
                  color: 'var(--text-secondary)', fontSize: 11,
                  transition: 'all 0.15s',
                }}
              >
                <FileText size={10} style={{ flexShrink: 0 }} />
                <span style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {s.filename}
                </span>
                {s.score != null && (
                  <span style={{
                    fontFamily: 'var(--font-mono)', fontSize: 10,
                    color: scoreColor(s.score), fontWeight: 600, flexShrink: 0,
                  }}>
                    {(s.score * 100).toFixed(0)}%
                  </span>
                )}
                <span style={{ fontSize: 9, color: 'var(--text-muted)', flexShrink: 0 }}>
                  {isOpen ? '▲' : '▼'}
                </span>
              </button>
              {isOpen && s.preview && (
                <div style={{
                  marginTop: 4,
                  padding: '8px 10px',
                  background: 'var(--bg-overlay)',
                  border: '1px solid var(--glass-border)',
                  borderRadius: 5,
                  fontSize: 11, lineHeight: 1.5,
                  color: 'var(--text-secondary)',
                  fontFamily: 'var(--font-mono)',
                  whiteSpace: 'pre-wrap',
                  maxWidth: 420,
                  maxHeight: 160,
                  overflow: 'auto',
                }}>
                  {s.preview}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ── Compliance Manager Modal ───────────────────────────────────────────────────

function ComplianceManagerModal({ standards, onClose }) {
  const [tab, setTab] = useState('list');
  const [form, setForm] = useState({ key: '', display: '', system_prompt: '', constraint_summary: '' });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState(null);

  const handleSave = async () => {
    if (!form.key.trim() || !form.display.trim() || !form.system_prompt.trim()) {
      setError('Key, display name, and system prompt are required.');
      return;
    }
    setSaving(true);
    setError('');
    try {
      const res = await fetch(`${API_BASE}/api/compliance`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        setForm({ key: '', display: '', system_prompt: '', constraint_summary: '' });
        setTab('list');
        onClose();
      } else {
        const data = await res.json();
        setError(data.detail || 'Save failed');
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (key) => {
    if (!confirm(`Delete "${key}"? This cannot be undone.`)) return;
    setDeleting(key);
    try {
      await fetch(`${API_BASE}/api/compliance/${encodeURIComponent(key)}`, { method: 'DELETE' });
      onClose();
    } catch (_) {}
    setDeleting(null);
  };

  const inputStyle = {
    width: '100%',
    background: 'var(--glass-bg)',
    border: '1px solid var(--glass-border)',
    borderRadius: 'var(--r-sm)',
    color: 'var(--text-primary)',
    fontSize: 12,
    padding: '7px 10px',
    outline: 'none',
    boxSizing: 'border-box',
  };

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 100,
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }} onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="glass-panel" style={{
        width: 560, maxHeight: '80vh', display: 'flex', flexDirection: 'column',
        border: '1px solid var(--glass-border)',
      }}>
        <div className="panel-header" style={{ flexShrink: 0 }}>
          <ShieldCheck size={14} style={{ color: 'var(--accent)' }} />
          <span className="panel-title">Compliance Standards</span>
          <div style={{ marginLeft: 'auto', display: 'flex', gap: 6 }}>
            <button className={`btn btn-sm ${tab === 'list' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setTab('list')} style={{ fontSize: 10 }}>Standards</button>
            <button className={`btn btn-sm ${tab === 'add' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => { setTab('add'); setError(''); }} style={{ fontSize: 10 }}>
              <Plus size={10} /> Add New
            </button>
            <button className="btn btn-ghost btn-sm" onClick={onClose}><X size={12} /></button>
          </div>
        </div>

        <div style={{ flex: 1, overflow: 'auto', padding: '12px 16px' }}>
          {tab === 'list' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {standards.filter(s => s.key).map(s => (
                <div key={s.key} style={{
                  display: 'flex', alignItems: 'flex-start', gap: 10,
                  padding: '10px 12px',
                  background: 'var(--glass-bg)',
                  border: '1px solid var(--glass-border)',
                  borderRadius: 'var(--r-md)',
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>{s.display}</span>
                      {s.is_builtin
                        ? <span style={{ fontSize: 9, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', padding: '1px 5px', border: '1px solid var(--glass-border)', borderRadius: 3 }}>BUILT-IN</span>
                        : <span style={{ fontSize: 9, color: 'var(--accent)', fontFamily: 'var(--font-mono)', padding: '1px 5px', border: '1px solid rgba(77,184,130,0.3)', borderRadius: 3 }}>CUSTOM</span>
                      }
                    </div>
                    <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 2, fontFamily: 'var(--font-mono)' }}>{s.key}</div>
                    {s.constraint_summary && (
                      <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginTop: 4 }}>{s.constraint_summary}</div>
                    )}
                  </div>
                  {!s.is_builtin && (
                    <button className="btn btn-sm" onClick={() => handleDelete(s.key)} disabled={deleting === s.key}
                      style={{ background: 'rgba(146,58,58,0.15)', border: '1px solid rgba(146,58,58,0.3)', color: '#e07070', flexShrink: 0 }}>
                      {deleting === s.key ? <Loader size={11} style={{ animation: 'spin 1s linear infinite' }} /> : <Trash2 size={11} />}
                    </button>
                  )}
                </div>
              ))}
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {error && (
                <div style={{ padding: '8px 12px', background: 'rgba(146,58,58,0.15)', border: '1px solid rgba(146,58,58,0.3)', borderRadius: 'var(--r-sm)', fontSize: 12, color: '#e07070' }}>
                  {error}
                </div>
              )}
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>KEY <span style={{ color: 'var(--score-low)' }}>*</span></div>
                <input style={inputStyle} placeholder="e.g. ISO-14125-Composites"
                  value={form.key} onChange={e => setForm(f => ({ ...f, key: e.target.value }))} />
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 3 }}>Alphanumeric + hyphens. Used as the identifier in the dropdown.</div>
              </div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>DISPLAY NAME <span style={{ color: 'var(--score-low)' }}>*</span></div>
                <input style={inputStyle} placeholder="e.g. ISO Composite Flexural Testing"
                  value={form.display} onChange={e => setForm(f => ({ ...f, display: e.target.value }))} />
              </div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>CONSTRAINT SUMMARY</div>
                <input style={inputStyle} placeholder="e.g. ISO 14125, ISO 14130: Composite mechanical testing"
                  value={form.constraint_summary} onChange={e => setForm(f => ({ ...f, constraint_summary: e.target.value }))} />
              </div>
              <div>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4 }}>SYSTEM PROMPT <span style={{ color: 'var(--score-low)' }}>*</span></div>
                <textarea
                  style={{ ...inputStyle, minHeight: 180, resize: 'vertical', fontFamily: 'var(--font-mono)', lineHeight: 1.5 }}
                  placeholder={`You are a compliance auditor for [standard].\n\nAUDITOR MANDATE:\n- Check that...\n\nDEVIATION FLAGS:\n- Missing X → ⚠️ NON-CONFORMANCE: X Not Specified\n\nRESPONSE FORMAT:\n1. Summary\n2. Clause-by-Clause Check\n3. Flags Found\n4. Recommendations`}
                  value={form.system_prompt}
                  onChange={e => setForm(f => ({ ...f, system_prompt: e.target.value }))}
                />
                <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 3 }}>
                  Tip: Include ⚠️ deviation flags and a numbered response format for best results.
                </div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                <button className="btn btn-secondary btn-sm" onClick={() => setTab('list')}>Cancel</button>
                <button className="btn btn-primary btn-sm" onClick={handleSave} disabled={saving}>
                  {saving ? <Loader size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Plus size={12} />}
                  Save Standard
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}