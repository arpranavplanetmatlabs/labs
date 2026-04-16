import { useState, useEffect, useRef } from 'react';
import { MessageSquare, Send, Loader, Trash2, FolderOpen, FileText } from 'lucide-react';

const API_BASE = 'http://localhost:8000';

const ROLES = [
  { id: 'material-expert', label: 'Material Expert', description: 'Technical analysis and comparisons' },
  { id: 'technical-reviewer', label: 'Technical Reviewer', description: 'Quality assurance and compliance' },
  { id: 'literature-researcher', label: 'Literature Researcher', description: 'Academic synthesis and research' },
];

export default function ChatPanel() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [sessionId, setSessionId] = useState('default');
  const [role, setRole] = useState('material-expert');
  const [sessions, setSessions] = useState([]);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    fetchSessions();
    fetchHistory();
  }, [sessionId]);

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

    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMessage,
          role: role,
          session_id: sessionId,
          include_context: true
        })
      });

      if (res.ok) {
        const data = await res.json();
        setMessages(prev => [
          ...prev,
          { role: 'assistant', content: data.response, sources: data.sources, timestamp: new Date().toISOString() }
        ]);
      } else {
        setMessages(prev => [...prev, { role: 'assistant', content: 'Error: Failed to get response', timestamp: new Date().toISOString() }]);
      }
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'Error: ' + err.message, timestamp: new Date().toISOString() }]);
    }

    setLoading(false);
  };

  const handleNewSession = () => {
    const newId = 'session-' + Date.now();
    setSessionId(newId);
    setMessages([]);
    fetchSessions();
  };

  const handleClearSession = async () => {
    if (!confirm('Clear this chat session? This cannot be undone.')) return;
    try {
      await fetch(`${API_BASE}/api/chat/sessions/${sessionId}`, { method: 'DELETE' });
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
    <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="panel-header">
        <MessageSquare size={14} style={{ color: 'var(--accent)' }} />
        <span className="panel-title">Materials Chat</span>
        <button className="btn btn-ghost btn-sm" onClick={handleNewSession} title="New session">
          <FolderOpen size={12} />
        </button>
        <button className="btn btn-ghost btn-sm" onClick={handleClearSession} title="Clear session">
          <Trash2 size={12} />
        </button>
      </div>

      <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--glass-border)' }}>
        <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6 }}>Role:</div>
        <div style={{ display: 'flex', gap: 6 }}>
          {ROLES.map(r => (
            <button
              key={r.id}
              className={`btn btn-sm ${role === r.id ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setRole(r.id)}
              style={{ fontSize: 10, padding: '4px 8px' }}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div style={{ flex: 1, overflow: 'auto', padding: 12 }}>
        {messages.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
            <MessageSquare size={32} style={{ marginBottom: 12, opacity: 0.5 }} />
            <div style={{ fontSize: 13 }}>Ask about materials</div>
            <div style={{ fontSize: 11, marginTop: 4 }}>Chat uses Qdrant knowledge base for context</div>
          </div>
        ) : (
          messages.map((msg, i) => (
            <div key={i} style={{ marginBottom: 12 }}>
              <div style={{
                fontSize: 10,
                color: msg.role === 'user' ? 'var(--accent)' : 'var(--text-muted)',
                marginBottom: 4,
                textTransform: 'uppercase',
                fontWeight: 600
              }}>
                {msg.role === 'user' ? 'You' : 'AI'}
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
                <div style={{ marginTop: 6, fontSize: 10, color: 'var(--text-muted)' }}>
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {msg.sources.map((s, j) => (
                      <span key={j} style={{
                        padding: '2px 6px',
                        background: 'var(--glass-bg)',
                        borderRadius: 4,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 4
                      }}>
                        <FileText size={10} />
                        {s.filename}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))
        )}
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--text-muted)' }}>
            <Loader size={14} style={{ animation: 'spin 1s linear infinite' }} />
            <span style={{ fontSize: 12 }}>Thinking...</span>
          </div>
        )}
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
            className="btn btn-primary"
            onClick={handleSend}
            disabled={loading || !input.trim()}
          >
            <Send size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}