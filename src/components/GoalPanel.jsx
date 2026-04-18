import { useState, useEffect } from 'react';
import { Sparkles, SlidersHorizontal, Play, RotateCcw, ChevronRight, Settings, Plus } from 'lucide-react';
import { MOCK_GOAL, MOCK_WEIGHTS } from '../mockData';
import SchemaBuilder from './SchemaBuilder';

const API = 'http://localhost:8000';
const COLORS = ['#4db882','#6eb4e6','#b8943a','#a78bfa','#f87171','#34d399','#fb923c'];

export default function GoalPanel({ onRunIteration, onToggleLoop, loopState, loopLoading, onSchemaChange }) {
  const [goal, setGoal]         = useState(MOCK_GOAL);
  const [weights, setWeights]   = useState(MOCK_WEIGHTS);
  const [schemas, setSchemas]   = useState([]);
  const [schemaId, setSchemaId] = useState('');
  const [schema, setSchema]     = useState(null);
  const [showBuilder, setShowBuilder] = useState(false);
  const [editSchema, setEditSchema]   = useState(null);

  const loopActive = loopState?.status === 'running' || loopState?.status === 'awaiting_approval';
  const isRunning  = loopLoading || loopState?.status === 'running';

  useEffect(() => { fetchSchemas(); }, []);

  async function fetchSchemas() {
    try {
      const res = await fetch(`${API}/api/schemas`);
      if (res.ok) { const d = await res.json(); setSchemas(d.schemas || []); }
    } catch (_) {}
  }

  function selectSchema(id) {
    setSchemaId(id);
    const s = schemas.find(x => x.schema_id === id) || null;
    setSchema(s);
    onSchemaChange?.(id, s);
    // Init weights from schema properties
    if (s?.property_names) {
      const names = typeof s.property_names === 'string' ? s.property_names.split(',') : s.property_names;
      const eq = 1 / (names.length || 1);
      setWeights(Object.fromEntries(names.map(n => [n, eq])));
    }
  }

  function handleSchemaSaved(saved) {
    setShowBuilder(false);
    setEditSchema(null);
    fetchSchemas();
    if (saved?.schema_id) selectSchema(saved.schema_id);
  }

  const handleToggleLoop = () => {
    onToggleLoop?.({ active: !loopActive, goal, weights, schema_id: schemaId || undefined });
  };
  const handleRunIteration = () => {
    onRunIteration?.({ goal, weights, schema_id: schemaId || undefined });
  };

  // Dynamic property weights from schema, fallback to 3 hardcoded
  const weightEntries = schema?.property_names
    ? (typeof schema.property_names === 'string' ? schema.property_names.split(',') : schema.property_names)
        .filter(Boolean)
        .map((name, i) => ({ key: name, label: name.replace(/_/g,' '), color: COLORS[i % COLORS.length] }))
    : [
        { key: 'strength',    label: 'Tensile Strength', color: COLORS[0] },
        { key: 'flexibility', label: 'Flexibility',       color: COLORS[1] },
        { key: 'cost',        label: 'Cost Efficiency',   color: COLORS[2] },
      ];

  const total = Object.values(weights).reduce((a, b) => a + (b || 0), 0);

  return (
    <div className="glass-panel" style={{ minHeight: 220 }}>
      <div className="panel-header">
        <Sparkles size={14} className="panel-title-icon" style={{ color: 'var(--accent)' }} />
        <span className="panel-title">Goal Configuration</span>
        <div className="ml-auto flex items-center gap-sm">
          {isRunning && <span className="tag tag-success" style={{ animation: 'pulse 2s ease-in-out infinite' }}>● Loop Running</span>}
          {loopState?.status === 'awaiting_approval' && !isRunning && (
            <span className="tag" style={{ background: 'rgba(61,153,112,0.15)', color: 'var(--accent)', borderColor: 'var(--accent)' }}>▲ Awaiting Approval</span>
          )}
          <button className="btn btn-ghost btn-sm" onClick={() => { setGoal(MOCK_GOAL); setWeights(MOCK_WEIGHTS); setSchemaId(''); setSchema(null); }} title="Reset">
            <RotateCcw size={12} />
          </button>
        </div>
      </div>

      <div className="panel-body" style={{ height: 'auto', overflow: 'visible' }}>
        {/* Schema selector */}
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 6 }}>
            Experiment Schema
            {loopState?.bo_mode && <span style={{ marginLeft: 8, color: '#22c55e' }}>● BO Active</span>}
            {loopState?.n_training_points > 0 && (
              <span style={{ marginLeft: 8, color: 'var(--text-muted)' }}>({loopState.n_training_points} training pts)</span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <select value={schemaId} onChange={e => selectSchema(e.target.value)} style={{
              flex: 1, padding: '7px 10px', background: 'var(--glass-bg)',
              border: `1px solid ${schemaId ? 'var(--accent)' : 'var(--glass-border)'}`,
              borderRadius: 6, color: 'var(--text)', fontSize: 12, cursor: 'pointer',
            }}>
              <option value="">— No schema (legacy mode) —</option>
              {schemas.map(s => (
                <option key={s.schema_id} value={s.schema_id}>
                  {s.name} ({s.material_system})
                </option>
              ))}
            </select>
            {schema && (
              <button onClick={() => { setEditSchema(schema); setShowBuilder(true); }} title="Edit schema"
                style={{ padding: '7px 10px', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 6, cursor: 'pointer', color: 'var(--text-muted)' }}>
                <Settings size={14} />
              </button>
            )}
            <button onClick={() => { setEditSchema(null); setShowBuilder(true); }} title="New schema"
              style={{ padding: '7px 10px', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 6, cursor: 'pointer', color: 'var(--accent)' }}>
              <Plus size={14} />
            </button>
          </div>
          {schema && (
            <div style={{ fontSize: 10, color: 'var(--text-muted)', marginTop: 4 }}>
              {schema.n_parameters} parameters · {schema.n_properties} properties · {schema.material_system}
            </div>
          )}
        </div>

        <div className="flex gap-md" style={{ flexWrap: 'wrap' }}>
          {/* Goal text */}
          <div style={{ flex: '1 1 360px' }}>
            <label style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.7px', display: 'block', marginBottom: 8 }}>Research Goal</label>
            <textarea className="goal-textarea" rows={3} value={goal} onChange={e => setGoal(e.target.value)}
              placeholder="Describe your optimization objective in natural language..." />
          </div>

          {/* Weights */}
          <div style={{ flex: '1 1 260px' }}>
            <div className="flex items-center" style={{ marginBottom: 8 }}>
              <label style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.7px' }}>
                <SlidersHorizontal size={11} style={{ display: 'inline', marginRight: 5 }} />
                {schema ? 'Property Weights' : 'Optimization Weights'}
              </label>
              <span style={{ marginLeft: 'auto', fontSize: 10, fontFamily: 'var(--font-mono)', color: Math.abs(total - 1) > 0.01 ? 'var(--score-low)' : 'var(--text-muted)' }}>
                Σ = {total.toFixed(2)}
              </span>
            </div>
            {weightEntries.map(({ key, label, color }) => (
              <WeightSlider key={key} label={label} color={color}
                value={weights[key] ?? 0.33}
                onChange={v => setWeights(w => ({ ...w, [key]: v }))} />
            ))}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-sm mt-md">
          <button className="btn btn-primary btn-lg" onClick={handleToggleLoop} disabled={isRunning}>
            <Play size={14} />
            {isRunning ? 'Running…' : loopActive ? 'Loop Active' : 'Start Research Loop'}
          </button>
          <button className="btn btn-ghost" onClick={handleRunIteration} disabled={isRunning}>
            <ChevronRight size={14} />Run 1 Iteration
          </button>
          <div className="ml-auto flex items-center gap-sm" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            <span>Auto-run</span>
            <Toggle active={loopActive} onChange={handleToggleLoop} />
          </div>
        </div>
      </div>

      {showBuilder && (
        <SchemaBuilder
          editSchema={editSchema}
          onClose={() => { setShowBuilder(false); setEditSchema(null); }}
          onSaved={handleSchemaSaved}
        />
      )}
    </div>
  );
}

function WeightSlider({ label, color, value, onChange }) {
  return (
    <div className="weight-slider-row">
      <div className="weight-slider-label" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{label}</div>
      <input type="range" min="0" max="1" step="0.05" value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        className="weight-slider" style={{ '--thumb-color': color }} />
      <div className="weight-slider-value" style={{ color }}>{(value||0).toFixed(2)}</div>
    </div>
  );
}

function Toggle({ active, onChange }) {
  return (
    <div onClick={onChange} style={{
      width: 36, height: 20, borderRadius: 20, cursor: 'pointer',
      background: active ? 'var(--accent)' : 'var(--bg-overlay)',
      border: '1px solid var(--glass-border)', position: 'relative', transition: 'background 0.25s',
    }}>
      <div style={{
        width: 14, height: 14, borderRadius: '50%', background: '#fff',
        position: 'absolute', top: 2, left: active ? 18 : 2, transition: 'left 0.2s',
      }} />
    </div>
  );
}
