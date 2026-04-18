import { useState, useEffect } from 'react';
import { Plus, Trash2, Save, X, Copy, ChevronDown, ChevronUp } from 'lucide-react';

const API = 'http://localhost:8000';

const DIRECTIONS = ['maximize', 'minimize', 'target'];

const PRESETS = {
  'Mechanical': {
    parameters: [
      { name: 'base_polymer_pct', min_val: 60, max_val: 95, unit: 'wt%' },
      { name: 'filler_content', min_val: 0, max_val: 30, unit: 'wt%' },
      { name: 'cure_temp', min_val: 100, max_val: 220, unit: '°C' },
      { name: 'cure_time', min_val: 10, max_val: 180, unit: 'min' },
    ],
    properties: [
      { name: 'tensile_strength_mpa', unit: 'MPa', target: 60, direction: 'maximize', weight: 0.5 },
      { name: 'elongation_at_break_pct', unit: '%', target: 100, direction: 'maximize', weight: 0.3 },
      { name: 'flexural_modulus_gpa', unit: 'GPa', target: 3.5, direction: 'maximize', weight: 0.2 },
    ],
  },
  'Thermal': {
    parameters: [
      { name: 'resin_content', min_val: 50, max_val: 90, unit: 'wt%' },
      { name: 'crosslinker_ratio', min_val: 0.8, max_val: 1.2, unit: 'stoich' },
      { name: 'cure_temp', min_val: 120, max_val: 200, unit: '°C' },
    ],
    properties: [
      { name: 'glass_transition_temp', unit: '°C', target: 150, direction: 'maximize', weight: 0.6 },
      { name: 'thermal_stability_temp', unit: '°C', target: 300, direction: 'maximize', weight: 0.4 },
    ],
  },
  'Nanocomposite': {
    parameters: [
      { name: 'matrix_content', min_val: 70, max_val: 98, unit: 'wt%' },
      { name: 'nano_filler_loading', min_val: 0.5, max_val: 10, unit: 'wt%', log_scale: true },
      { name: 'dispersion_time', min_val: 30, max_val: 240, unit: 'min' },
      { name: 'processing_temp', min_val: 150, max_val: 280, unit: '°C' },
    ],
    properties: [
      { name: 'tensile_strength_mpa', unit: 'MPa', target: 80, direction: 'maximize', weight: 0.4 },
      { name: 'electrical_conductivity', unit: 'S/m', target: 1e-3, direction: 'maximize', weight: 0.3, log_scale: true },
      { name: 'dispersion_quality', unit: '%', target: 90, direction: 'maximize', weight: 0.3 },
    ],
  },
};

const emptyParam = () => ({ name: '', min_val: 0, max_val: 100, unit: '', log_scale: false });
const emptyProp  = () => ({ name: '', unit: '', target: 0, direction: 'maximize', weight: 0.5 });

export default function SchemaBuilder({ onClose, onSaved, editSchema = null }) {
  const [name, setName]           = useState(editSchema?.name || '');
  const [system, setSystem]       = useState(editSchema?.material_system || '');
  const [createdBy, setCreatedBy] = useState(editSchema?.created_by || '');
  const [notes, setNotes]         = useState(editSchema?.notes || '');
  const [params, setParams]       = useState(editSchema?.parameters || [emptyParam()]);
  const [props, setProps]         = useState(editSchema?.properties || [emptyProp()]);
  const [constraints, setConstr]  = useState((editSchema?.constraints || []).join('\n'));
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState('');
  const [showPresets, setShowPresets] = useState(!editSchema);

  function applyPreset(key) {
    const p = PRESETS[key];
    setParams(p.parameters.map(x => ({ ...emptyParam(), ...x })));
    setProps(p.properties.map(x => ({ ...emptyProp(), ...x })));
    setSystem(key);
    setShowPresets(false);
  }

  function updateParam(i, field, value) {
    setParams(ps => ps.map((p, idx) => idx === i ? { ...p, [field]: value } : p));
  }
  function updateProp(i, field, value) {
    setProps(ps => ps.map((p, idx) => idx === i ? { ...p, [field]: value } : p));
  }
  function removeParam(i) { setParams(ps => ps.filter((_, idx) => idx !== i)); }
  function removeProp(i)  { setProps(ps => ps.filter((_, idx) => idx !== i)); }

  async function save() {
    if (!name.trim() || !system.trim()) { setError('Name and Material System are required'); return; }
    if (params.some(p => !p.name.trim())) { setError('All parameters need a name'); return; }
    if (props.some(p => !p.name.trim())) { setError('All properties need a name'); return; }
    setSaving(true); setError('');
    try {
      const body = {
        name, material_system: system, created_by: createdBy, notes,
        parameters: params.map(p => ({ ...p, min_val: +p.min_val, max_val: +p.max_val })),
        properties: props.map(p => ({ ...p, target: +p.target, weight: +p.weight })),
        constraints: constraints.split('\n').map(s => s.trim()).filter(Boolean),
      };
      const url = editSchema ? `${API}/api/schemas/${editSchema.schema_id}` : `${API}/api/schemas`;
      const method = editSchema ? 'PUT' : 'POST';
      const res = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      onSaved?.(data.schema || data);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', zIndex: 1000,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
    }}>
      <div style={{
        background: 'var(--bg-panel, #1a1a2e)', border: '1px solid var(--glass-border)',
        borderRadius: 12, width: 720, maxHeight: '90vh', overflow: 'auto', padding: 24,
      }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 20 }}>
          <h2 style={{ margin: 0, fontSize: 16 }}>{editSchema ? 'Edit Schema' : 'New Experiment Schema'}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}>
            <X size={18} />
          </button>
        </div>

        {/* Presets */}
        {showPresets && !editSchema && (
          <div style={{ marginBottom: 16 }}>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>START FROM PRESET</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              {Object.keys(PRESETS).map(k => (
                <button key={k} onClick={() => applyPreset(k)} style={{
                  padding: '6px 12px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
                  background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', color: 'var(--text)',
                }}>{k}</button>
              ))}
              <button onClick={() => setShowPresets(false)} style={{
                padding: '6px 12px', borderRadius: 6, fontSize: 12, cursor: 'pointer',
                background: 'transparent', border: '1px dashed var(--glass-border)', color: 'var(--text-muted)',
              }}>Custom →</button>
            </div>
          </div>
        )}

        {/* Basic info */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
          <Field label="Schema Name *" value={name} onChange={setName} placeholder="e.g. Epoxy-Amine Optimization" />
          <Field label="Material System *" value={system} onChange={setSystem} placeholder="e.g. Epoxy-Amine" />
          <Field label="Created By" value={createdBy} onChange={setCreatedBy} placeholder="Scientist name" />
          <Field label="Notes" value={notes} onChange={setNotes} placeholder="Optional notes" />
        </div>

        {/* Parameters */}
        <Section title="Input Parameters (Formulation Space)">
          {params.map((p, i) => (
            <ParamRow key={i} p={p} onChange={(f, v) => updateParam(i, f, v)} onRemove={() => removeParam(i)} />
          ))}
          <AddBtn onClick={() => setParams(ps => [...ps, emptyParam()])} label="Add Parameter" />
        </Section>

        {/* Properties */}
        <Section title="Output Properties (Optimization Targets)">
          {props.map((p, i) => (
            <PropRow key={i} p={p} onChange={(f, v) => updateProp(i, f, v)} onRemove={() => removeProp(i)} />
          ))}
          <AddBtn onClick={() => setProps(ps => [...ps, emptyProp()])} label="Add Property" />
        </Section>

        {/* Constraints */}
        <Section title="Constraints (optional)">
          <textarea
            value={constraints}
            onChange={e => setConstr(e.target.value)}
            placeholder="One per line, e.g.: filler_content + base_polymer_pct <= 100"
            style={{
              width: '100%', minHeight: 60, background: 'var(--glass-bg)',
              border: '1px solid var(--glass-border)', borderRadius: 6, color: 'var(--text)',
              padding: '8px 10px', fontSize: 12, resize: 'vertical', boxSizing: 'border-box',
            }}
          />
        </Section>

        {error && <div style={{ color: '#ef4444', fontSize: 12, marginBottom: 12 }}>{error}</div>}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{
            padding: '8px 16px', borderRadius: 6, cursor: 'pointer', fontSize: 13,
            background: 'transparent', border: '1px solid var(--glass-border)', color: 'var(--text-muted)',
          }}>Cancel</button>
          <button onClick={save} disabled={saving} style={{
            padding: '8px 16px', borderRadius: 6, cursor: 'pointer', fontSize: 13,
            background: 'var(--accent, #3b82f6)', border: 'none', color: '#fff',
            display: 'flex', alignItems: 'center', gap: 6,
          }}>
            <Save size={14} />{saving ? 'Saving…' : editSchema ? 'Update Schema' : 'Create Schema'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, value, onChange, placeholder }) {
  return (
    <div>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 4, textTransform: 'uppercase' }}>{label}</div>
      <input value={value} onChange={e => onChange(e.target.value)} placeholder={placeholder}
        style={{
          width: '100%', padding: '7px 10px', background: 'var(--glass-bg)',
          border: '1px solid var(--glass-border)', borderRadius: 6, color: 'var(--text)',
          fontSize: 12, boxSizing: 'border-box',
        }} />
    </div>
  );
}

function Section({ title, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 8, fontWeight: 600 }}>{title}</div>
      {children}
    </div>
  );
}

function AddBtn({ onClick, label }) {
  return (
    <button onClick={onClick} style={{
      display: 'flex', alignItems: 'center', gap: 4, padding: '5px 10px',
      background: 'transparent', border: '1px dashed var(--glass-border)',
      borderRadius: 6, cursor: 'pointer', color: 'var(--text-muted)', fontSize: 11, marginTop: 4,
    }}>
      <Plus size={12} />{label}
    </button>
  );
}

function ParamRow({ p, onChange, onRemove }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1fr auto', gap: 6, marginBottom: 6, alignItems: 'center' }}>
      <input value={p.name} onChange={e => onChange('name', e.target.value)} placeholder="param_name"
        style={inputStyle()} />
      <input value={p.min_val} onChange={e => onChange('min_val', e.target.value)} placeholder="Min" type="number"
        style={inputStyle()} />
      <input value={p.max_val} onChange={e => onChange('max_val', e.target.value)} placeholder="Max" type="number"
        style={inputStyle()} />
      <input value={p.unit} onChange={e => onChange('unit', e.target.value)} placeholder="Unit"
        style={inputStyle()} />
      <button onClick={onRemove} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444' }}>
        <Trash2 size={13} />
      </button>
    </div>
  );
}

function PropRow({ p, onChange, onRemove }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr 1.2fr 1fr auto', gap: 6, marginBottom: 6, alignItems: 'center' }}>
      <input value={p.name} onChange={e => onChange('name', e.target.value)} placeholder="property_name"
        style={inputStyle()} />
      <input value={p.unit} onChange={e => onChange('unit', e.target.value)} placeholder="Unit"
        style={inputStyle()} />
      <input value={p.target} onChange={e => onChange('target', e.target.value)} placeholder="Target" type="number"
        style={inputStyle()} />
      <select value={p.direction} onChange={e => onChange('direction', e.target.value)} style={{ ...inputStyle(), cursor: 'pointer' }}>
        {DIRECTIONS.map(d => <option key={d} value={d}>{d}</option>)}
      </select>
      <input value={p.weight} onChange={e => onChange('weight', e.target.value)} placeholder="Weight" type="number" step="0.1" min="0" max="1"
        style={inputStyle()} />
      <button onClick={onRemove} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444' }}>
        <Trash2 size={13} />
      </button>
    </div>
  );
}

function inputStyle() {
  return {
    padding: '6px 8px', background: 'var(--glass-bg)',
    border: '1px solid var(--glass-border)', borderRadius: 5,
    color: 'var(--text)', fontSize: 11, width: '100%', boxSizing: 'border-box',
  };
}
