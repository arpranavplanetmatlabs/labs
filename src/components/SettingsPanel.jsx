import { useState, useEffect, useRef } from 'react';

const API_BASE = 'http://localhost:8000';

export default function SettingsPanel({ onClose }) {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');

  // Form state
  const [tavilyKey, setTavilyKey] = useState('');
  const [tavilyKeyVisible, setTavilyKeyVisible] = useState(false);
  const [webSearchEnabled, setWebSearchEnabled] = useState(false);

  const backdropRef = useRef(null);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/settings`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setSettings(data);
      setWebSearchEnabled(!!data.web_search_enabled);
      // Don't pre-fill the key input — user must retype to change
    } catch (e) {
      setError('Failed to load settings.');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    setError('');
    try {
      const body = { web_search_enabled: webSearchEnabled };
      if (tavilyKey.trim()) body.tavily_api_key = tavilyKey.trim();

      const res = await fetch(`${API_BASE}/api/settings`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.settings) setSettings(data.settings);
      setSaved(true);
      setTavilyKey('');
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError('Failed to save settings.');
    } finally {
      setSaving(false);
    }
  };

  const handleBackdropClick = (e) => {
    if (e.target === backdropRef.current) onClose();
  };

  return (
    <div
      ref={backdropRef}
      onClick={handleBackdropClick}
      style={{
        position: 'fixed', inset: 0, zIndex: 1000,
        background: 'rgba(7,9,15,0.75)',
        backdropFilter: 'blur(8px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}
    >
      <div style={{
        width: 480, maxWidth: '90vw',
        background: 'var(--bg-card)',
        border: '1px solid var(--glass-border)',
        borderRadius: 'var(--r-lg)',
        padding: 'var(--pad-lg)',
        display: 'flex', flexDirection: 'column', gap: 'var(--pad-md)',
        boxShadow: '0 24px 64px rgba(0,0,0,0.6)',
      }}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' }}>
              Settings
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>
              API keys &amp; feature flags
            </div>
          </div>
          <button
            className="btn btn-ghost btn-sm"
            onClick={onClose}
            style={{ padding: '4px 10px', fontSize: 16 }}
          >
            ×
          </button>
        </div>

        {loading && (
          <div style={{ color: 'var(--text-muted)', fontSize: 13, textAlign: 'center', padding: 24 }}>
            Loading…
          </div>
        )}

        {!loading && (
          <>
            {/* Web Search Toggle */}
            <section style={{
              background: 'var(--bg-overlay)',
              border: '1px solid var(--glass-border)',
              borderRadius: 'var(--r-md)',
              padding: 'var(--pad-md)',
              display: 'flex', flexDirection: 'column', gap: 12,
            }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                Web Search
              </div>

              <label style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}>
                <div
                  onClick={() => setWebSearchEnabled(v => !v)}
                  style={{
                    width: 36, height: 20,
                    borderRadius: 10,
                    background: webSearchEnabled ? 'var(--accent)' : 'var(--bg-overlay)',
                    border: `1px solid ${webSearchEnabled ? 'var(--accent)' : 'var(--glass-border)'}`,
                    position: 'relative',
                    cursor: 'pointer',
                    transition: 'background 0.2s',
                    flexShrink: 0,
                  }}
                >
                  <div style={{
                    position: 'absolute',
                    top: 2, left: webSearchEnabled ? 18 : 2,
                    width: 14, height: 14,
                    borderRadius: '50%',
                    background: 'white',
                    transition: 'left 0.2s',
                  }} />
                </div>
                <span style={{ fontSize: 13, color: 'var(--text-primary)' }}>
                  Enable web search via Tavily
                </span>
              </label>

              <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                When enabled, the chat system will supplement local document results with live web search via Tavily API.
              </div>
            </section>

            {/* Tavily API Key */}
            <section style={{
              background: 'var(--bg-overlay)',
              border: '1px solid var(--glass-border)',
              borderRadius: 'var(--r-md)',
              padding: 'var(--pad-md)',
              display: 'flex', flexDirection: 'column', gap: 12,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
                  Tavily API Key
                </div>
                {settings?.tavily_api_key_set && (
                  <span style={{
                    fontSize: 11, color: 'var(--score-high)',
                    background: 'rgba(74,222,128,0.1)',
                    border: '1px solid rgba(74,222,128,0.3)',
                    borderRadius: 4, padding: '2px 8px',
                  }}>
                    Key saved ({settings.tavily_api_key_preview})
                  </span>
                )}
              </div>

              <div style={{ position: 'relative' }}>
                <input
                  type={tavilyKeyVisible ? 'text' : 'password'}
                  value={tavilyKey}
                  onChange={e => setTavilyKey(e.target.value)}
                  placeholder={settings?.tavily_api_key_set ? 'Enter new key to replace…' : 'Paste your Tavily API key…'}
                  style={{
                    width: '100%',
                    background: 'var(--bg-base)',
                    border: '1px solid var(--glass-border)',
                    borderRadius: 'var(--r-sm)',
                    color: 'var(--text-primary)',
                    padding: '8px 40px 8px 12px',
                    fontSize: 13,
                    fontFamily: 'var(--font-mono)',
                    boxSizing: 'border-box',
                    outline: 'none',
                  }}
                />
                <button
                  type="button"
                  onClick={() => setTavilyKeyVisible(v => !v)}
                  style={{
                    position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)',
                    background: 'none', border: 'none', cursor: 'pointer',
                    color: 'var(--text-muted)', fontSize: 14, padding: 4,
                  }}
                  title={tavilyKeyVisible ? 'Hide key' : 'Show key'}
                >
                  {tavilyKeyVisible ? '🙈' : '👁'}
                </button>
              </div>

              <div style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
                Get your key at{' '}
                <span style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                  tavily.com
                </span>
                . Stored locally in{' '}
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>data/settings.json</span>.
                Takes priority over the <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>TAVILY_API_KEY</span> env var.
              </div>
            </section>

            {/* Error / success */}
            {error && (
              <div style={{
                fontSize: 13, color: 'var(--score-low)',
                background: 'rgba(248,113,113,0.1)',
                border: '1px solid rgba(248,113,113,0.3)',
                borderRadius: 'var(--r-sm)', padding: '8px 12px',
              }}>
                {error}
              </div>
            )}
            {saved && (
              <div style={{
                fontSize: 13, color: 'var(--score-high)',
                background: 'rgba(74,222,128,0.1)',
                border: '1px solid rgba(74,222,128,0.3)',
                borderRadius: 'var(--r-sm)', padding: '8px 12px',
              }}>
                Settings saved.
              </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn btn-ghost btn-sm" onClick={onClose}>Cancel</button>
              <button
                className="btn btn-primary btn-sm"
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? 'Saving…' : 'Save Settings'}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
