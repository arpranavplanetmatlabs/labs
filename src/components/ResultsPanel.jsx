import { useState, useMemo, useEffect } from 'react';
import { BarChart3, TrendingUp, Loader, FlaskConical, Sparkles, Lightbulb } from 'lucide-react';
import {
  RadarChart, PolarGrid, PolarAngleAxis, Radar, ResponsiveContainer,
  LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend,
} from 'recharts';

const API_BASE = 'http://localhost:8000';

const COLORS = { Strength: '#4db882', Flexibility: '#6eb4e6', Cost: '#b8943a' };

export default function ResultsPanel({ selectedExp }) {
  const [tab, setTab] = useState('radar');
  const [experiments, setExperiments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    fetchExperiments();
  }, []);

  const fetchExperiments = async (showLoader = false) => {
    if (showLoader) setRefreshing(true);
    try {
      const res = await fetch(`${API_BASE}/api/experiments?limit=50`);
      if (res.ok) {
        const data = await res.json();
        const expPromises = data.experiments.map(async (exp) => {
          const detailRes = await fetch(`${API_BASE}/api/experiments/${exp.id}`);
          if (detailRes.ok) {
            return await detailRes.json();
          }
          return null;
        });
        const detailedExps = (await Promise.all(expPromises)).filter(Boolean);
        setExperiments(detailedExps);
      }
    } catch (err) {
      console.error('Failed to fetch experiments:', err);
    } finally {
      setLoading(false);
      if (showLoader) setRefreshing(false);
    }
  };

  const activeExp = useMemo(() => {
    if (!selectedExp || experiments.length === 0) return experiments[0] || null;
    return experiments.find(e => e.id === selectedExp.id) || experiments[0] || null;
  }, [selectedExp, experiments]);

  const radarData = useMemo(() => {
    if (experiments.length === 0) return [];
    return experiments.map(exp => {
      const expected = exp.expected_output || {};
      const actual = exp.actual_output || {};
      return {
        subject: exp.name.substring(0, 15) + (exp.name.length > 15 ? '...' : ''),
        Strength: expected.tensile_strength ? Math.min(100, (actual.tensile_strength || 0) / expected.tensile_strength * 100) : 0,
        Flexibility: expected.elongation ? Math.min(100, (actual.elongation || 0) / expected.elongation * 100) : 0,
        Cost: exp.conditions?.cost ? Math.max(0, 100 - (actual.cost || 0) / exp.conditions.cost * 100) : 50,
      };
    });
  }, [experiments]);

  if (loading) {
    return (
      <div className="glass-panel" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Loader size={24} style={{ animation: 'spin 1s linear infinite', color: 'var(--accent)' }} />
      </div>
    );
  }

  if (experiments.length === 0) {
    return (
      <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div className="panel-header">
          <BarChart3 size={14} style={{ color: 'var(--accent)' }} />
          <span className="panel-title">Results Visualization</span>
        </div>
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-muted)' }}>
          <div style={{ textAlign: 'center' }}>
            <FlaskConical size={32} style={{ marginBottom: 8, opacity: 0.5 }} />
            <div style={{ fontSize: 13 }}>No experiments yet</div>
            <div style={{ fontSize: 11, marginTop: 4 }}>Create an experiment to see results</div>
          </div>
        </div>
      </div>
    );
  }

  const completedExps = experiments.filter(e => e.status === 'completed');
  const bestExp = completedExps.length > 0 ? completedExps.reduce((best, exp) => 
    (exp.confidence_score || 0) > (best.confidence_score || 0) ? exp : best
  , completedExps[0]) : activeExp;

  const expected = activeExp?.expected_output || {};
  const actual = activeExp?.actual_output || {};
  const results = activeExp?.results || [];

  return (
    <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="panel-header">
        <BarChart3 size={14} style={{ color: 'var(--accent)' }} />
        <span className="panel-title">Results Visualization</span>
        {refreshing && <Loader size={12} style={{ marginLeft: 8, animation: 'spin 1s linear infinite', color: 'var(--accent)' }} />}
        <div className="ml-auto">
          <div className="pill-tabs">
            <button id="tab-radar" className={`pill-tab${tab === 'radar' ? ' active' : ''}`} onClick={() => setTab('radar')}>Radar</button>
            <button id="tab-trend" className={`pill-tab${tab === 'trend' ? ' active' : ''}`} onClick={() => setTab('trend')}>Trend</button>
          </div>
        </div>
      </div>

      <div className="panel-body" style={{ height: 'calc(100% - 49px)', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {/* Metric summary row */}
        <div className="flex gap-sm">
          <MetricCard 
            label="Total Exp" 
            value={experiments.length} 
            unit="experiments" 
            color="var(--text-primary)" 
          />
          <MetricCard 
            label="Completed" 
            value={completedExps.length} 
            unit="tests" 
            color="var(--score-high)" 
          />
          <MetricCard 
            label="Pending" 
            value={experiments.length - completedExps.length} 
            unit="tests" 
            color="var(--score-mid)" 
          />
          <MetricCard 
            label="Iterations" 
            value="1" 
            unit="/ ∞" 
            color="var(--text-muted)" 
          />
        </div>

        {/* Experiment list */}
        <div style={{ 
          background: 'var(--bg-overlay)', 
          borderRadius: 'var(--r-md)', 
          padding: 8,
          maxHeight: 80,
          overflow: 'auto'
        }}>
          <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>
            Experiments
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {experiments.map(exp => (
              <div 
                key={exp.id}
                style={{
                  padding: '4px 8px',
                  background: activeExp?.id === exp.id ? 'var(--accent)' : 'var(--glass-bg)',
                  borderRadius: 'var(--r-sm)',
                  fontSize: 10,
                  color: activeExp?.id === exp.id ? '#fff' : 'var(--text-secondary)',
                  cursor: 'pointer',
                }}
                onClick={() => {}}
              >
                {exp.name.substring(0, 20)}{exp.name.length > 20 ? '...' : ''}
                <span style={{ marginLeft: 4, opacity: 0.7 }}>({exp.status})</span>
              </div>
            ))}
          </div>
        </div>

        {/* Results table if has results */}
        {results.length > 0 ? (
          <div style={{ flex: 1, overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11 }}>
              <thead>
                <tr style={{ color: 'var(--text-muted)', borderBottom: '1px solid var(--glass-border)' }}>
                  <th style={{ textAlign: 'left', padding: 6 }}>Metric</th>
                  <th style={{ textAlign: 'center', padding: 6 }}>Expected</th>
                  <th style={{ textAlign: 'center', padding: 6 }}>Actual</th>
                  <th style={{ textAlign: 'center', padding: 6 }}>Deviation</th>
                  <th style={{ textAlign: 'center', padding: 6 }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid var(--glass-border)' }}>
                    <td style={{ padding: 6, color: 'var(--text-primary)' }}>{r.metric}</td>
                    <td style={{ padding: 6, textAlign: 'center', color: 'var(--text-muted)' }}>{r.expected}</td>
                    <td style={{ padding: 6, textAlign: 'center', color: 'var(--text-primary)' }}>{r.actual}</td>
                    <td style={{ 
                      padding: 6, 
                      textAlign: 'center', 
                      fontFamily: 'var(--font-mono)',
                      color: r.deviation !== null && Math.abs(r.deviation) <= 10 ? 'var(--score-high)' : 'var(--score-low)'
                    }}>
                      {r.deviation !== null ? `${r.deviation.toFixed(1)}%` : '-'}
                    </td>
                    <td style={{ padding: 6, textAlign: 'center' }}>
                      {r.passed ? '✓' : r.deviation !== null ? '✗' : '-'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ 
            flex: 1, 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center', 
            color: 'var(--text-muted)',
            fontSize: 12 
          }}>
            {activeExp ? 'Add test results to see comparison' : 'Select an experiment'}
          </div>
        )}

        {/* AI Predictions Display */}
        {activeExp && activeExp.llm_output && (
          <div style={{ marginTop: 12, padding: 10, background: 'var(--glass-bg)', borderRadius: 'var(--r-md)', border: '1px solid var(--accent)' }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--accent)', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 4 }}>
              <Sparkles size={10} /> AI Predictions
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6 }}>
              {(() => {
                const props = activeExp.llm_output;
                const keyProps = ['tensile_strength_mpa', 'elongation_percent', 'tensile_modulus_mpa', 'flexural_modulus_mpa'];
                return keyProps.map(k => {
                  const val = props.predictions?.[k] || props[k];
                  if (!val) return null;
                  return (
                    <div key={k} style={{ padding: '4px 6px', background: 'var(--bg-overlay)', borderRadius: 'var(--r-sm)', fontSize: 10 }}>
                      <div style={{ color: 'var(--text-muted)', textTransform: 'capitalize' }}>{k.replace(/_/g, ' ')}</div>
                      <div style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
                        {val.value || val}
                      </div>
                    </div>
                  );
                });
              })()}
            </div>
          </div>
        )}

        {/* Score Display */}
        {activeExp && activeExp.confidence_score > 0 && (
          <div style={{ marginTop: 12, padding: 10, background: 'var(--glass-bg)', borderRadius: 'var(--r-md)', border: '1px solid var(--score-high)' }}>
            <div style={{ fontSize: 10, fontWeight: 600, color: 'var(--score-high)', marginBottom: 6 }}>
              Composite Score: {Math.round(activeExp.confidence_score * 100)}%
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>
              Status: {activeExp.status}
            </div>
          </div>
        )}

        {/* Legend */}
        <div className="trend-legend">
          <div className="trend-legend-item">
            <div className="trend-legend-dot" style={{ background: COLORS.Strength }} />
            Strength
          </div>
          <div className="trend-legend-item">
            <div className="trend-legend-dot" style={{ background: COLORS.Flexibility }} />
            Flexibility
          </div>
          <div className="trend-legend-item">
            <div className="trend-legend-dot" style={{ background: COLORS.Cost }} />
            Cost
          </div>
        </div>
      </div>
    </div>
  );
}

function MetricCard({ label, value, unit, color }) {
  return (
    <div style={{
      flex: 1, background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)',
      borderRadius: 'var(--r-md)', padding: '8px 12px',
    }}>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2, textTransform: 'uppercase', letterSpacing: '0.6px' }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 18, fontWeight: 700, color, lineHeight: 1.2 }}>{value}</div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{unit}</div>
    </div>
  );
}
