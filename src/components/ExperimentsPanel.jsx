import { useState, useEffect } from 'react';
import { FlaskConical, Plus, Search, CheckCircle, Clock, AlertCircle, Loader, X, Save, TestTube, Trash2, Sparkles, Lightbulb } from 'lucide-react';

const API_BASE = 'http://localhost:8000';

const SCORE_COLOR = score =>
  score >= 0.8 ? 'var(--score-high)' : score >= 0.65 ? 'var(--score-mid)' : 'var(--score-low)';

const STATUS_ICON = {
  pending: <Clock size={12} style={{ color: 'var(--text-muted)' }} />,
  running: <Loader size={12} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />,
  completed: <CheckCircle size={12} style={{ color: 'var(--score-high)' }} />,
  failed: <AlertCircle size={12} style={{ color: 'var(--score-low)' }} />,
};

export default function ExperimentsPanel({ onSelect, onCreateNew }) {
  const [experiments, setExperiments] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(null);
  const [selectedExp, setSelectedExp] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [predictions, setPredictions] = useState(null);
  const [suggestions, setSuggestions] = useState([]);

  useEffect(() => {
    fetchExperiments();
  }, []);

  const fetchExperiments = async (showLoader = false) => {
    if (showLoader) setRefreshing(true);
    try {
      const res = await fetch(`${API_BASE}/api/experiments?limit=50`);
      if (res.ok) {
        const data = await res.json();
        setExperiments(data.experiments);
      }
    } catch (err) {
      console.error('Failed to fetch experiments:', err);
    } finally {
      setLoading(false);
      if (showLoader) setRefreshing(false);
    }
  };

  const handleSelect = async (exp) => {
    setSelectedExp(exp);
    try {
      const res = await fetch(`${API_BASE}/api/experiments/${exp.id}`);
      if (res.ok) {
        const fullExp = await res.json();
        setShowDetailModal(fullExp);
        if (onSelect) onSelect(fullExp);
      }
    } catch (err) {
      console.error('Failed to fetch experiment details:', err);
    }
  };

  const handleCreateExperiment = async (formData) => {
    try {
      const res = await fetch(`${API_BASE}/api/experiments`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData)
      });
      if (res.ok) {
        setShowCreateModal(false);
        fetchExperiments(true);
      }
    } catch (err) {
      console.error('Failed to create experiment:', err);
    }
  };

  const handleAddResults = async (expId, results) => {
    try {
      const res = await fetch(`${API_BASE}/api/experiments/${expId}/results`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ experiment_id: expId, results })
      });
      if (res.ok) {
        fetchExperiments(true);
        // Also refresh the detail modal to show new results immediately
        const detailRes = await fetch(`${API_BASE}/api/experiments/${expId}`);
        if (detailRes.ok) {
          const updatedExp = await detailRes.json();
          setShowDetailModal(updatedExp);
        }
      }
    } catch (err) {
      console.error('Failed to add results:', err);
    }
  };

  const handleDeleteExperiment = async (expId) => {
    if (!confirm('Delete this experiment? This cannot be undone.')) return;
    try {
      const res = await fetch(`${API_BASE}/api/experiments/${expId}`, { method: 'DELETE' });
      if (res.ok) {
        setShowDetailModal(null);
        setPredictions(null);
        setSuggestions([]);
        fetchExperiments(true);
      }
    } catch (err) {
      console.error('Failed to delete experiment:', err);
    }
  };

  const handlePredict = async (expId) => {
    try {
      const res = await fetch(`${API_BASE}/api/experiments/${expId}/predict`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setPredictions(data);
      }
    } catch (err) {
      console.error('Failed to predict:', err);
    }
  };

  const handleSuggest = async (expId) => {
    try {
      const res = await fetch(`${API_BASE}/api/experiments/${expId}/suggest`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setSuggestions(data.suggestions || []);
      }
    } catch (err) {
      console.error('Failed to suggest:', err);
    }
  };

  const handleComplete = async (expId, results) => {
    // Build actual_output from results
    const actual_output = {};
    results.forEach(r => {
      if (r.metric && r.actual) {
        const key = r.metric.toLowerCase().includes('tensile') ? 'tensile_strength' :
                    r.metric.toLowerCase().includes('elongation') ? 'elongation' :
                    r.metric.toLowerCase().includes('modulus') ? 'tensile_modulus' : 'other';
        actual_output[key] = { value: r.actual, confidence: 0.8 };
      }
    });
    
    try {
      const res = await fetch(`${API_BASE}/api/experiments/${expId}/complete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(actual_output)
      });
      if (res.ok) {
        fetchExperiments(true);
      }
    } catch (err) {
      console.error('Failed to complete:', err);
    }
  };

  const filteredExps = experiments.filter(exp =>
    exp.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (exp.material_name && exp.material_name.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  const pendingCount = experiments.filter(e => e.status === 'pending').length;
  const completedCount = experiments.filter(e => e.status === 'completed').length;

  if (loading) {
    return (
      <div className="glass-panel" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
        <Loader size={24} style={{ animation: 'spin 1s linear infinite', color: 'var(--accent)' }} />
      </div>
    );
  }

  return (
    <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%', position: 'relative' }}>
      <div className="panel-header">
        <FlaskConical size={14} style={{ color: 'var(--accent)' }} />
        <span className="panel-title">Experiments</span>
        <span className="ml-auto" style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          {experiments.length} total
        </span>
      </div>

      <div style={{ padding: '8px 12px', borderBottom: '1px solid var(--glass-border)' }}>
        <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
          <input
            type="text"
            placeholder="Search experiments..."
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            style={{
              flex: 1,
              background: 'var(--glass-bg)',
              border: '1px solid var(--glass-border)',
              borderRadius: 'var(--r-md)',
              padding: '6px 10px',
              color: 'var(--text-primary)',
              fontSize: 12,
            }}
          />
          <button className="btn btn-primary btn-sm" onClick={() => setShowCreateModal(true)} title="Create new experiment">
            <Plus size={12} />
          </button>
        </div>
        <div style={{ display: 'flex', gap: 12, fontSize: 11 }}>
          <span style={{ color: 'var(--text-muted)' }}>
            Pending: <strong style={{ color: 'var(--text-secondary)' }}>{pendingCount}</strong>
          </span>
          <span style={{ color: 'var(--text-muted)' }}>
            Completed: <strong style={{ color: 'var(--score-high)' }}>{completedCount}</strong>
          </span>
        </div>
      </div>

      <div className="panel-body scroll-area" style={{ height: 'calc(100% - 120px)' }}>
        {filteredExps.length === 0 ? (
          <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
            <FlaskConical size={32} style={{ marginBottom: 12, opacity: 0.5 }} />
            <div style={{ fontSize: 13 }}>No experiments found</div>
            <div style={{ fontSize: 11, marginTop: 4 }}>Click + to create a new experiment</div>
          </div>
        ) : (
          filteredExps.map(exp => (
            <ExperimentCard
              key={exp.id}
              exp={exp}
              isExpanded={expanded === exp.id}
              onToggle={() => setExpanded(expanded === exp.id ? null : exp.id)}
              onSelect={() => handleSelect(exp)}
            />
          ))
        )}
      </div>

      {showCreateModal && (
        <CreateExperimentModal
          onClose={() => setShowCreateModal(false)}
          onSubmit={handleCreateExperiment}
        />
      )}

      {showDetailModal && (
        <ExperimentDetailModal
          experiment={showDetailModal}
          onClose={() => { setShowDetailModal(null); setPredictions(null); setSuggestions([]); fetchExperiments(); }}
          onAddResults={handleAddResults}
          onDelete={() => handleDeleteExperiment(showDetailModal.id)}
          onPredict={() => handlePredict(showDetailModal.id)}
          onSuggest={() => handleSuggest(showDetailModal.id)}
          onComplete={() => handleComplete(showDetailModal.id, showDetailModal.results || [])}
          predictions={predictions}
          suggestions={suggestions}
        />
      )}
    </div>
  );
}

function ExperimentCard({ exp, isExpanded, onToggle, onSelect }) {
  const statusIcon = STATUS_ICON[exp.status] || STATUS_ICON.pending;
  const confidence = exp.confidence || 0;

  return (
    <div
      className="exp-card anim-fade-in"
      style={{
        padding: '12px',
        borderRadius: 'var(--r-md)',
        background: isExpanded ? 'var(--glass-active)' : 'var(--glass-bg)',
        border: '1px solid var(--glass-border)',
        cursor: 'pointer',
        transition: 'all 0.15s ease',
      }}
      onClick={onToggle}
    >
      <div className="flex items-center gap-sm">
        {statusIcon}
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>{exp.name}</div>
          {exp.material_name && (
            <div style={{ fontSize: 11, color: 'var(--text-muted)' }}>{exp.material_name}</div>
          )}
        </div>
        <div style={{
          fontSize: 11,
          fontFamily: 'var(--font-mono)',
          color: SCORE_COLOR(confidence),
        }}>
          {exp.status === 'completed' ? `${Math.round(confidence * 100)}%` : exp.status}
        </div>
      </div>

      {isExpanded && exp.material_name && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--glass-border)' }}>
          <button
            className="btn btn-secondary btn-sm"
            style={{ width: '100%' }}
            onClick={(e) => { e.stopPropagation(); onSelect(); }}
          >
            View Details
          </button>
        </div>
      )}
    </div>
  );
}

function CreateExperimentModal({ onClose, onSubmit }) {
  const [formData, setFormData] = useState({
    name: '',
    material_name: '',
    description: '',
    conditions: { temperature: '', pressure: '', time: '' },
    expected_output: { tensile_strength: '', elongation: '' }
  });
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.name.trim()) return;
    
    setSubmitting(true);
    const submitData = {
      name: formData.name,
      material_name: formData.material_name || null,
      description: formData.description || null,
      conditions: {
        temperature: formData.conditions.temperature || null,
        pressure: formData.conditions.pressure || null,
        time: formData.conditions.time || null
      },
      expected_output: {
        tensile_strength: formData.expected_output.tensile_strength || null,
        elongation: formData.expected_output.elongation || null
      }
    };
    await onSubmit(submitData);
    setSubmitting(false);
  };

  return (
    <div style={{
      position: 'absolute', inset: 0, zIndex: 50,
      background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center',
      backdropFilter: 'blur(4px)'
    }}>
      <div className="glass-panel" style={{ 
        width: 480, maxHeight: '90%', overflow: 'auto',
        border: '1px solid var(--accent)', boxShadow: '0 0 30px rgba(58,146,104,0.3)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid var(--glass-border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <FlaskConical size={18} style={{ color: 'var(--accent)' }} />
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>Create New Experiment</span>
          </div>
          <button onClick={onClose} className="btn btn-ghost btn-sm" style={{ padding: 4 }}>
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ padding: 20 }}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>
              Experiment Name *
            </label>
            <input
              type="text"
              required
              placeholder="e.g., Tensile Test - EPDM + Silica"
              value={formData.name}
              onChange={e => setFormData({ ...formData, name: e.target.value })}
              style={{ width: '100%', padding: '10px 12px', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-md)', color: 'var(--text-primary)', fontSize: 13 }}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>
              Material Name
            </label>
            <input
              type="text"
              placeholder="e.g., EPDM Rubber"
              value={formData.material_name}
              onChange={e => setFormData({ ...formData, material_name: e.target.value })}
              style={{ width: '100%', padding: '10px 12px', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-md)', color: 'var(--text-primary)', fontSize: 13 }}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 6, textTransform: 'uppercase' }}>
              Description
            </label>
            <textarea
              placeholder="Describe the experiment objectives and approach..."
              value={formData.description}
              onChange={e => setFormData({ ...formData, description: e.target.value })}
              rows={3}
              style={{ width: '100%', padding: '10px 12px', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-md)', color: 'var(--text-primary)', fontSize: 13, resize: 'vertical' }}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase' }}>
              Process Conditions
            </label>
            <div style={{ display: 'flex', gap: 10 }}>
              <input
                type="text"
                placeholder="Temp (°C)"
                value={formData.conditions.temperature}
                onChange={e => setFormData({ ...formData, conditions: { ...formData.conditions, temperature: e.target.value } })}
                style={{ flex: 1, padding: '8px 10px', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-md)', color: 'var(--text-primary)', fontSize: 12 }}
              />
              <input
                type="text"
                placeholder="Pressure (bar)"
                value={formData.conditions.pressure}
                onChange={e => setFormData({ ...formData, conditions: { ...formData.conditions, pressure: e.target.value } })}
                style={{ flex: 1, padding: '8px 10px', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-md)', color: 'var(--text-primary)', fontSize: 12 }}
              />
              <input
                type="text"
                placeholder="Time (min)"
                value={formData.conditions.time}
                onChange={e => setFormData({ ...formData, conditions: { ...formData.conditions, time: e.target.value } })}
                style={{ flex: 1, padding: '8px 10px', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-md)', color: 'var(--text-primary)', fontSize: 12 }}
              />
            </div>
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: 11, color: 'var(--text-muted)', marginBottom: 8, textTransform: 'uppercase' }}>
              Expected Output (Target Values)
            </label>
            <div style={{ display: 'flex', gap: 10 }}>
              <input
                type="text"
                placeholder="Tensile (MPa)"
                value={formData.expected_output.tensile_strength}
                onChange={e => setFormData({ ...formData, expected_output: { ...formData.expected_output, tensile_strength: e.target.value } })}
                style={{ flex: 1, padding: '8px 10px', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-md)', color: 'var(--text-primary)', fontSize: 12 }}
              />
              <input
                type="text"
                placeholder="Elongation (%)"
                value={formData.expected_output.elongation}
                onChange={e => setFormData({ ...formData, expected_output: { ...formData.expected_output, elongation: e.target.value } })}
                style={{ flex: 1, padding: '8px 10px', background: 'var(--glass-bg)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-md)', color: 'var(--text-primary)', fontSize: 12 }}
              />
            </div>
          </div>

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
            <button type="button" onClick={onClose} className="btn btn-secondary">Cancel</button>
            <button type="submit" disabled={submitting || !formData.name.trim()} className="btn btn-primary">
              {submitting ? <Loader size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Save size={14} />}
              Create Experiment
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function ExperimentDetailModal({ experiment, onClose, onAddResults, onDelete, onPredict, onSuggest, onComplete, predictions, suggestions }) {
  const [showAddResult, setShowAddResult] = useState(false);
  const [newResult, setNewResult] = useState({ metric_name: '', expected_value: '', actual_value: '', test_method: '', notes: '' });
  const [loadingAction, setLoadingAction] = useState(null);
  const [error, setError] = useState(null);

  // More lenient checks for results and status
  const rawResults = experiment.results || experiment.result || [];
  const hasResults = Array.isArray(rawResults) && rawResults.length > 0;
  const isCompleted = experiment.status === 'completed';
  const hasActualOutput = experiment.actual_output && Object.keys(experiment.actual_output).length > 0;
  const canComplete = hasResults || hasActualOutput;

  const handleAddResult = async () => {
    if (!newResult.metric_name.trim()) return;
    await onAddResults(experiment.id, [newResult]);
    setShowAddResult(false);
    setNewResult({ metric_name: '', expected_value: '', actual_value: '', test_method: '', notes: '' });
  };

  const handleDelete = () => {
    if (confirm('Delete this experiment? This cannot be undone.')) {
      onDelete?.();
    }
  };

  const handlePredictClick = async () => {
    setLoadingAction('predict');
    setError(null);
    try {
      await onPredict();
    } catch (e) {
      setError('Prediction failed. Please try again.');
    } finally {
      setLoadingAction(null);
    }
  };

  const handleSuggestClick = async () => {
    setLoadingAction('suggest');
    setError(null);
    try {
      await onSuggest();
    } catch (e) {
      setError('Suggestions failed. Please try again.');
    } finally {
      setLoadingAction(null);
    }
  };

  const handleCompleteClick = async () => {
    setLoadingAction('complete');
    setError(null);
    try {
      await onComplete();
    } catch (e) {
      setError('Failed to complete. Please try again.');
    } finally {
      setLoadingAction(null);
    }
  };

  return (
    <div style={{
      position: 'absolute', inset: 0, zIndex: 50,
      background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center',
      backdropFilter: 'blur(4px)'
    }}>
      <div className="glass-panel" style={{ 
        width: 560, maxHeight: '90%', overflow: 'auto',
        border: '1px solid var(--accent)', boxShadow: '0 0 30px rgba(58,146,104,0.3)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid var(--glass-border)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <TestTube size={18} style={{ color: 'var(--accent)' }} />
            <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{experiment.name}</span>
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            {experiment.status === 'pending' && (
              <button 
                onClick={handlePredictClick} 
                disabled={loadingAction === 'predict'}
                className="btn btn-secondary btn-sm" 
                title="Predict properties using AI"
                style={{ opacity: loadingAction === 'predict' ? 0.6 : 1 }}
              >
                {loadingAction === 'predict' ? <Loader size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Sparkles size={12} />}
                {loadingAction === 'predict' ? ' Predicting...' : ' Predict'}
              </button>
            )}
            {isCompleted && (
              <button 
                onClick={handleSuggestClick} 
                disabled={loadingAction === 'suggest'}
                className="btn btn-secondary btn-sm" 
                title="Get next configuration suggestions"
                style={{ opacity: loadingAction === 'suggest' ? 0.6 : 1 }}
              >
                {loadingAction === 'suggest' ? <Loader size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Lightbulb size={12} />}
                {loadingAction === 'suggest' ? ' Suggesting...' : ' Suggest'}
              </button>
            )}
            {canComplete && !isCompleted && (
              <button 
                onClick={handleCompleteClick} 
                disabled={loadingAction === 'complete'}
                className="btn btn-primary btn-sm" 
                title="Mark experiment as completed"
                style={{ opacity: loadingAction === 'complete' ? 0.6 : 1 }}
              >
                {loadingAction === 'complete' ? <Loader size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <CheckCircle size={12} />}
                {loadingAction === 'complete' ? ' Completing...' : ' Complete'}
              </button>
            )}
            <div style={{ width: 1, height: 20, background: 'var(--glass-border)', margin: '0 4px' }} />
            <button onClick={handleDelete} className="btn btn-ghost btn-sm" style={{ padding: 4, color: 'var(--score-low)' }} title="Delete experiment">
              <Trash2 size={14} />
            </button>
            <button onClick={onClose} className="btn btn-ghost btn-sm" style={{ padding: 4 }}>
              <X size={16} />
            </button>
          </div>
        </div>

        {error && (
          <div style={{ padding: '12px 20px', background: 'rgba(146,58,58,0.15)', borderBottom: '1px solid var(--score-low)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <AlertCircle size={14} style={{ color: 'var(--score-low)' }} />
            <span style={{ color: 'var(--score-low)', fontSize: 12 }}>{error}</span>
            <button onClick={() => setError(null)} className="btn btn-ghost btn-sm" style={{ marginLeft: 'auto', padding: 2 }}>
              <X size={12} />
            </button>
          </div>
        )}

        <div style={{ padding: 20 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
            <div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>Material</div>
              <div style={{ color: 'var(--text-primary)', fontSize: 13 }}>{experiment.material_name || '-'}</div>
            </div>
            <div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>Status</div>
              <span className={`tag ${experiment.status === 'completed' ? 'tag-success' : 'tag-pending'}`}>
                {experiment.status}
              </span>
            </div>
            {experiment.conditions && Object.keys(experiment.conditions).length > 0 && (
              <div style={{ gridColumn: '1 / -1' }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>Conditions</div>
                <div style={{ display: 'flex', gap: 16, color: 'var(--text-secondary)', fontSize: 12 }}>
                  {experiment.conditions.temperature && <span>Temp: {experiment.conditions.temperature}</span>}
                  {experiment.conditions.pressure && <span>Pressure: {experiment.conditions.pressure}</span>}
                  {experiment.conditions.time && <span>Time: {experiment.conditions.time}</span>}
                </div>
              </div>
            )}
            {experiment.expected_output && Object.keys(experiment.expected_output).length > 0 && (
              <div style={{ gridColumn: '1 / -1' }}>
                <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 4 }}>Expected Output</div>
                <div style={{ display: 'flex', gap: 16, color: 'var(--text-secondary)', fontSize: 12 }}>
                  {experiment.expected_output.tensile_strength && <span>Tensile: {experiment.expected_output.tensile_strength} MPa</span>}
                  {experiment.expected_output.elongation && <span>Elongation: {experiment.expected_output.elongation}%</span>}
                </div>
              </div>
            )}
          </div>

          {experiment.description && (
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 6 }}>Description</div>
              <div style={{ color: 'var(--text-secondary)', fontSize: 12, lineHeight: 1.5 }}>{experiment.description}</div>
            </div>
          )}

          <div style={{ marginBottom: 20 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-primary)' }}>Test Results</div>
              <button className="btn btn-primary btn-sm" onClick={() => setShowAddResult(!showAddResult)}>
                <Plus size={12} /> Add Result
              </button>
            </div>

            {showAddResult && (
              <div style={{ background: 'var(--glass-bg)', padding: 12, borderRadius: 'var(--r-md)', marginBottom: 12, border: '1px solid var(--glass-border)' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
                  <input
                    type="text"
                    placeholder="Metric (e.g., Tensile Strength)"
                    value={newResult.metric_name}
                    onChange={e => setNewResult({ ...newResult, metric_name: e.target.value })}
                    style={{ padding: '6px 8px', background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-sm)', color: 'var(--text-primary)', fontSize: 11 }}
                  />
                  <input
                    type="text"
                    placeholder="Test Method (e.g., ASTM D638)"
                    value={newResult.test_method}
                    onChange={e => setNewResult({ ...newResult, test_method: e.target.value })}
                    style={{ padding: '6px 8px', background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-sm)', color: 'var(--text-primary)', fontSize: 11 }}
                  />
                  <input
                    type="text"
                    placeholder="Expected Value"
                    value={newResult.expected_value}
                    onChange={e => setNewResult({ ...newResult, expected_value: e.target.value })}
                    style={{ padding: '6px 8px', background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-sm)', color: 'var(--text-primary)', fontSize: 11 }}
                  />
                  <input
                    type="text"
                    placeholder="Actual Value"
                    value={newResult.actual_value}
                    onChange={e => setNewResult({ ...newResult, actual_value: e.target.value })}
                    style={{ padding: '6px 8px', background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-sm)', color: 'var(--text-primary)', fontSize: 11 }}
                  />
                </div>
                <input
                  type="text"
                  placeholder="Notes..."
                  value={newResult.notes}
                  onChange={e => setNewResult({ ...newResult, notes: e.target.value })}
                  style={{ width: '100%', padding: '6px 8px', background: 'var(--bg-overlay)', border: '1px solid var(--glass-border)', borderRadius: 'var(--r-sm)', color: 'var(--text-primary)', fontSize: 11, marginBottom: 8 }}
                />
                <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                  <button className="btn btn-ghost btn-sm" onClick={() => setShowAddResult(false)}>Cancel</button>
                  <button className="btn btn-primary btn-sm" onClick={handleAddResult}>Save Result</button>
                </div>
              </div>
            )}
 
            {/* Use our more lenient hasResults check for display too */}
            {Array.isArray(rawResults) && rawResults.length > 0 ? (
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid var(--glass-border)', color: 'var(--text-muted)' }}>
                    <th style={{ textAlign: 'left', padding: '8px 4px' }}>Metric</th>
                    <th style={{ textAlign: 'center', padding: '8px 4px' }}>Expected</th>
                    <th style={{ textAlign: 'center', padding: '8px 4px' }}>Actual</th>
                    <th style={{ textAlign: 'center', padding: '8px 4px' }}>Deviation</th>
                    <th style={{ textAlign: 'center', padding: '8px 4px' }}>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {rawResults.map((r, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid var(--glass-border)' }}>
                      <td style={{ padding: '8px 4px', color: 'var(--text-primary)' }}>{r.metric}</td>
                      <td style={{ padding: '8px 4px', textAlign: 'center', color: 'var(--text-secondary)' }}>{r.expected || '-'}</td>
                      <td style={{ padding: '8px 4px', textAlign: 'center', color: 'var(--text-primary)' }}>{r.actual || '-'}</td>
                      <td style={{ padding: '8px 4px', textAlign: 'center', fontFamily: 'var(--font-mono)', color: r.deviation !== null && Math.abs(r.deviation) <= 10 ? 'var(--score-high)' : 'var(--score-low)' }}>
                        {r.deviation !== null ? `${r.deviation.toFixed(1)}%` : '-'}
                      </td>
                      <td style={{ padding: '8px 4px', textAlign: 'center' }}>
                        {r.passed ? <CheckCircle size={14} style={{ color: 'var(--score-high)' }} /> : r.deviation !== null ? <AlertCircle size={14} style={{ color: 'var(--score-low)' }} /> : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div style={{ textAlign: 'center', padding: 20, color: 'var(--text-muted)', fontSize: 12 }}>
                No results recorded yet. Add test results after running the experiment.
              </div>
            )}
          </div>

          {predictions && (
            <div style={{ marginBottom: 20, padding: 12, background: 'var(--glass-bg)', borderRadius: 'var(--r-md)', border: predictions.predictions ? '1px solid var(--accent)' : '1px solid var(--score-low)' }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--accent)', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Sparkles size={12} /> 
                {predictions.predictions ? 'AI Predicted Properties' : 'Prediction Error'}
              </div>
              {predictions.predictions && Object.keys(predictions.predictions).length > 0 ? (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                  {Object.entries(predictions.predictions).map(([key, val]) => (
                    <div key={key} style={{ padding: '6px 8px', background: 'var(--bg-overlay)', borderRadius: 'var(--r-sm)', fontSize: 11 }}>
                      <div style={{ color: 'var(--text-muted)', textTransform: 'capitalize' }}>{key.replace(/_/g, ' ')}</div>
                      <div style={{ color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontWeight: 600 }}>
                        {val?.value || val || '-'}
                      </div>
                      {val?.confidence && (
                        <div style={{ color: 'var(--score-mid)', fontSize: 10 }}>Conf: {Math.round(val.confidence * 100)}%</div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div style={{ fontSize: 11, color: 'var(--text-muted)', padding: 8 }}>
                  Raw prediction data: {JSON.stringify(predictions).substring(0, 200)}...
                </div>
              )}
              {predictions.reasoning && (
                <div style={{ marginTop: 8, fontSize: 10, color: 'var(--text-secondary)', fontStyle: 'italic' }}>
                  {predictions.reasoning.substring(0, 150)}...
                </div>
              )}
            </div>
          )}

          {suggestions && suggestions.length > 0 && (
            <div style={{ marginBottom: 20, padding: 12, background: 'var(--glass-bg)', borderRadius: 'var(--r-md)', border: '1px solid #b8943a' }}>
              <div style={{ fontSize: 11, fontWeight: 600, color: '#b8943a', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                <Lightbulb size={12} /> Next Configuration Suggestions
              </div>
              {suggestions.map((s, i) => (
                <div key={i} style={{ padding: '8px 10px', marginBottom: 8, background: 'var(--bg-overlay)', borderRadius: 'var(--r-sm)', borderLeft: '3px solid #b8943a' }}>
                  <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 4 }}>{s.label || `Config ${String.fromCharCode(65+i)}`}</div>
                  <div style={{ fontSize: 11, color: 'var(--text-secondary)', marginBottom: 4 }}>
                    {s.composition ? JSON.stringify(s.composition).substring(0, 100) : s.rationale?.substring(0, 100) || 'No details'}
                  </div>
                  {s.risk && (
                    <div style={{ fontSize: 10, color: s.risk === 'low' ? 'var(--score-high)' : s.risk === 'medium' ? 'var(--score-mid)' : 'var(--score-low)' }}>
                      Risk: {s.risk}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', paddingTop: 16, borderTop: '1px solid var(--glass-border)' }}>
            <button onClick={onClose} className="btn btn-secondary">Close</button>
          </div>
        </div>
      </div>
    </div>
  );
}