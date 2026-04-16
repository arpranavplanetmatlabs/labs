import { useState, useEffect } from 'react';
import { Sparkles, SlidersHorizontal, Play, RotateCcw, ChevronRight } from 'lucide-react';
import { MOCK_GOAL, MOCK_WEIGHTS } from '../mockData';

export default function GoalPanel({ onRunIteration, onToggleLoop, loopState, loopLoading }) {
  const [goal, setGoal] = useState(MOCK_GOAL);
  const [weights, setWeights] = useState(MOCK_WEIGHTS);

  // Sync loopActive with real loop state from parent
  const loopActive = loopState?.status === 'running' || loopState?.status === 'awaiting_approval';
  const isRunning  = loopLoading || loopState?.status === 'running';

  const handleToggleLoop = () => {
    onToggleLoop?.({ active: !loopActive, goal, weights });
  };

  const handleRunIteration = () => {
    onRunIteration?.({ goal, weights });
  };

  const total = Object.values(weights).reduce((a, b) => a + b, 0);

  return (
    <div className="glass-panel" style={{ minHeight: 220 }}>
      <div className="panel-header">
        <Sparkles size={14} className="panel-title-icon" style={{ color: 'var(--accent)' }} />
        <span className="panel-title">Goal Configuration</span>
        <div className="ml-auto flex items-center gap-sm">
          {isRunning && (
            <span className="tag tag-success" style={{ animation: 'pulse 2s ease-in-out infinite' }}>
              ● Loop Running
            </span>
          )}
          {loopState?.status === 'awaiting_approval' && !isRunning && (
            <span className="tag" style={{ background: 'rgba(61,153,112,0.15)', color: 'var(--accent)', borderColor: 'var(--accent)' }}>
              ▲ Awaiting Approval
            </span>
          )}
          <button
            id="btn-reset-goal"
            className="btn btn-ghost btn-sm"
            onClick={() => { setGoal(MOCK_GOAL); setWeights(MOCK_WEIGHTS); }}
            title="Reset"
          >
            <RotateCcw size={12} />
          </button>
        </div>
      </div>

      <div className="panel-body" style={{ height: 'auto', overflow: 'visible' }}>
        <div className="flex gap-md" style={{ flexWrap: 'wrap' }}>
          {/* Goal text */}
          <div style={{ flex: '1 1 360px' }}>
            <label style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.7px', display: 'block', marginBottom: 8 }}>
              Research Goal
            </label>
            <textarea
              id="goal-input"
              className="goal-textarea"
              rows={3}
              value={goal}
              onChange={e => setGoal(e.target.value)}
              placeholder="Describe your optimization objective in natural language..."
            />
          </div>

          {/* Weights */}
          <div style={{ flex: '1 1 260px' }}>
            <div className="flex items-center" style={{ marginBottom: 8 }}>
              <label style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.7px' }}>
                <SlidersHorizontal size={11} style={{ display: 'inline', marginRight: 5 }} />
                Optimization Weights
              </label>
              <span
                style={{ marginLeft: 'auto', fontSize: 10, fontFamily: 'var(--font-mono)',
                  color: Math.abs(total - 1) > 0.01 ? 'var(--score-low)' : 'var(--text-muted)' }}
              >
                Σ = {total.toFixed(2)}
              </span>
            </div>

            <WeightSlider id="w-strength"    label="Tensile Strength"  color="#4db882" value={weights.strength}    onChange={v => setWeights(w => ({ ...w, strength: v }))} />
            <WeightSlider id="w-flexibility" label="Flexibility"        color="#6eb4e6" value={weights.flexibility} onChange={v => setWeights(w => ({ ...w, flexibility: v }))} />
            <WeightSlider id="w-cost"        label="Cost Efficiency"    color="#b8943a" value={weights.cost}        onChange={v => setWeights(w => ({ ...w, cost: v }))} />
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-sm mt-md">
          <button
            id="btn-run-loop"
            className="btn btn-primary btn-lg"
            onClick={handleToggleLoop}
            disabled={isRunning}
          >
            <Play size={14} />
            {isRunning ? 'Running…' : loopActive ? 'Loop Active' : 'Start Research Loop'}
          </button>
          <button
            id="btn-next-iter"
            className="btn btn-ghost"
            onClick={handleRunIteration}
            disabled={isRunning}
          >
            <ChevronRight size={14} />
            Run 1 Iteration
          </button>
          <div className="ml-auto flex items-center gap-sm" style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            <span>Auto-run</span>
            <Toggle active={loopActive} onChange={() => handleToggleLoop()} id="toggle-autorun" />
          </div>
        </div>
      </div>
    </div>
  );
}

function WeightSlider({ id, label, color, value, onChange }) {
  return (
    <div className="weight-slider-row">
      <div className="weight-slider-label" style={{ fontSize: 12, color: 'var(--text-secondary)' }}>{label}</div>
      <input
        id={id}
        type="range"
        min="0" max="1" step="0.05"
        value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        className="weight-slider"
        style={{ '--thumb-color': color }}
      />
      <div className="weight-slider-value" style={{ color }}>{value.toFixed(2)}</div>
    </div>
  );
}

function Toggle({ active, onChange, id }) {
  return (
    <div
      id={id}
      onClick={() => onChange(v => !v)}
      style={{
        width: 36, height: 20, borderRadius: 20, cursor: 'pointer',
        background: active ? 'var(--accent)' : 'var(--bg-overlay)',
        border: '1px solid var(--glass-border)',
        position: 'relative', transition: 'background 0.25s',
        boxShadow: active ? '0 0 10px var(--accent-glow)' : 'none',
      }}
    >
      <div style={{
        width: 14, height: 14, borderRadius: '50%', background: '#fff',
        position: 'absolute', top: 2,
        left: active ? 18 : 2,
        transition: 'left 0.2s',
      }} />
    </div>
  );
}
