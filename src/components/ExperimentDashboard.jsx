import { useState } from 'react';
import { FlaskConical, ChevronDown, ChevronUp, Award, Zap } from 'lucide-react';
import { MOCK_EXPERIMENTS } from '../mockData';
import UncertaintyBar from './UncertaintyBar';

const SCORE_COLOR = score =>
  score >= 0.8 ? 'var(--score-high)' : score >= 0.65 ? 'var(--score-mid)' : 'var(--score-low)';

function normalizeCandidates(candidates) {
  return candidates.map((c, i) => {
    const additiveParts = (c.composition?.additives ?? []).map(a => ({ name: a.name, pct: a.percentage ?? 0 }));
    const components = [
      { name: c.composition?.base_polymer ?? c.material_name ?? 'Base', pct: 100 - additiveParts.reduce((s, a) => s + a.pct, 0) },
      ...additiveParts,
    ];
    return {
      id: `iter-${i}`,
      label: c.label ?? `Config ${String.fromCharCode(65 + i)}`,
      rank: i + 1,
      composite_score: c.composite_score ?? 0,
      scores: c.scores ?? {},
      surrogate_predictions: c.surrogate_predictions ?? {},
      acquisition_score: c.acquisition_score ?? 0,
      acquisition_reason: c.hypothesis ?? '',
      components,
      process: { temperature: c.processing?.temperature_c ?? '—', cure_time: c.processing?.cure_time_min ?? '—' },
      hypothesis: c.hypothesis ?? '',
    };
  });
}

export default function ExperimentDashboard({ onSelect, loopState }) {
  const [expanded, setExpanded] = useState(null);

  const hasRealData = loopState?.candidates?.length > 0;
  const experiments = hasRealData ? normalizeCandidates(loopState.candidates) : MOCK_EXPERIMENTS;
  const iteration = loopState?.iteration ?? 3;

  return (
    <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="panel-header">
        <FlaskConical size={14} style={{ color: 'var(--accent)' }} />
        <span className="panel-title">Experiment Dashboard</span>
        <span className="ml-auto" style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          {hasRealData ? `Iter ${iteration} · ${experiments.length} configs` : `Mock · ${experiments.length} configs`}
        </span>
      </div>

      <div className="panel-body scroll-area" style={{ height: 'calc(100% - 49px)' }}>
        <div className="stagger-children flex flex-col gap-sm">
          {experiments.map(exp => (
            <ExperimentCard
              key={exp.id}
              exp={exp}
              isExpanded={expanded === exp.id}
              onToggle={() => setExpanded(expanded === exp.id ? null : exp.id)}
              onSelect={() => onSelect && onSelect(exp)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function ExperimentCard({ exp, isExpanded, onToggle, onSelect }) {
  return (
    <div
      id={`exp-card-${exp.id}`}
      className={`exp-card rank-${exp.rank} anim-fade-in`}
      onClick={onToggle}
    >
      {/* Header row */}
      <div className="flex items-center gap-sm" style={{ marginBottom: 8 }}>
        {exp.rank === 1 && <Award size={14} style={{ color: 'var(--score-high)', flexShrink: 0 }} />}
        <div>
          <span style={{ fontWeight: 700, fontSize: 13, color: 'var(--text-primary)' }}>{exp.label}</span>
          <span style={{ fontSize: 11, color: 'var(--text-muted)', marginLeft: 8, fontFamily: 'var(--font-mono)' }}>
            #{exp.id}
          </span>
        </div>
        <span className={`tag ml-auto ${exp.rank === 1 ? 'tag-success' : exp.rank === 2 ? 'tag-warning' : 'tag-danger'}`}>
          {exp.rank === 1 ? '🏆 Best' : `Rank #${exp.rank}`}
        </span>
        <button className="btn btn-icon btn-ghost" style={{ padding: 4 }} onClick={e => { e.stopPropagation(); onToggle(); }}>
          {isExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        </button>
      </div>

      {/* Composite score */}
      <div style={{ marginBottom: 8 }}>
        <div className="flex items-center gap-sm" style={{ marginBottom: 4 }}>
          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>Composite Score</span>
          <span style={{
            marginLeft: 'auto', fontFamily: 'var(--font-mono)', fontSize: 15, fontWeight: 700,
            color: SCORE_COLOR(exp.composite_score),
          }}>
            {exp.composite_score.toFixed(3)}
          </span>
        </div>
        <div className="score-bar-track" style={{ height: 6 }}>
          <div className="score-bar-fill" style={{
            width: `${exp.composite_score * 100}%`,
            background: `linear-gradient(90deg, ${SCORE_COLOR(exp.composite_score)}66, ${SCORE_COLOR(exp.composite_score)})`,
          }} />
        </div>
      </div>

      {/* Sub-scores: dynamic from schema or legacy */}
      {Object.keys(exp.scores).length > 0 && (
        <div className="flex gap-sm" style={{ flexWrap: 'wrap' }}>
          {Object.entries(exp.scores).map(([k, v]) => (
            <SubScore key={k} label={k.replace(/_/g,' ')} value={v} color="var(--score-high)" />
          ))}
        </div>
      )}

      {/* Acquisition score chip (BO mode) */}
      {exp.acquisition_score > 0 && (
        <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Zap size={11} style={{ color: '#a78bfa' }} />
          <span style={{ fontSize: 10, color: '#a78bfa' }}>
            EI score: {exp.acquisition_score.toFixed(3)}
          </span>
        </div>
      )}

      {/* Expanded content */}
      {isExpanded && (
        <div style={{ marginTop: 12, borderTop: '1px solid var(--glass-border)', paddingTop: 12 }}>
          {/* Surrogate predictions (GP μ ± σ) */}
          {Object.keys(exp.surrogate_predictions).length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 6 }}>
                Surrogate Predictions (GP)
              </div>
              {Object.entries(exp.surrogate_predictions).map(([name, pred]) => (
                <div key={name} style={{ marginBottom: 6 }}>
                  <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>{name.replace(/_/g,' ')}</div>
                  <UncertaintyBar
                    mean={pred?.mean ?? pred}
                    std={pred?.std ?? 0}
                    unit={pred?.unit ?? ''}
                    trained={pred?.trained !== false}
                  />
                </div>
              ))}
            </div>
          )}

          {/* Formulation */}
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.7px', marginBottom: 6 }}>
            Formulation
          </div>
          <div className="flex flex-col gap-sm" style={{ marginBottom: 10 }}>
            {exp.components.map(c => (
              <div key={c.name} className="flex items-center gap-sm" style={{ fontSize: 12 }}>
                <span style={{ color: 'var(--text-secondary)', minWidth: 160 }}>{c.name}</span>
                <div className="score-bar-track" style={{ flex: 1 }}>
                  <div className="score-bar-fill" style={{
                    width: `${c.pct}%`, background: 'linear-gradient(90deg, var(--accent-dim), var(--accent))',
                  }} />
                </div>
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-data)', minWidth: 36, textAlign: 'right' }}>
                  {c.pct}%
                </span>
              </div>
            ))}
          </div>

          {/* Process params */}
          <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.7px', marginBottom: 6 }}>
            Process Parameters
          </div>
          <div className="flex gap-sm" style={{ flexWrap: 'wrap' }}>
            <PropChip label="Temp" value={`${exp.process.temperature}°C`} />
            <PropChip label="Cure Time" value={`${exp.process.cure_time} min`} />
            <PropChip label="Pressure" value={`${exp.process.pressure} bar`} />
          </div>

          {/* Hypothesis */}
          <div style={{
            marginTop: 10, fontSize: 12, color: 'var(--text-secondary)',
            fontStyle: 'italic', borderLeft: '2px solid var(--accent-dim)',
            paddingLeft: 10, lineHeight: 1.6,
          }}>
            {exp.hypothesis}
          </div>

          <button
            id={`btn-select-${exp.id}`}
            className="btn btn-accent-ghost btn-sm mt-md"
            onClick={e => { e.stopPropagation(); onSelect(); }}
            style={{ width: '100%', justifyContent: 'center' }}
          >
            View Decision Analysis →
          </button>
        </div>
      )}
    </div>
  );
}

function SubScore({ label, value, color }) {
  return (
    <div style={{ flex: 1, background: 'var(--bg-overlay)', borderRadius: 'var(--r-sm)', padding: '4px 8px' }}>
      <div style={{ fontSize: 10, color: 'var(--text-muted)', marginBottom: 2 }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600, color }}>{value.toFixed(2)}</div>
    </div>
  );
}

function PropChip({ label, value, highlight }) {
  return (
    <div style={{
      background: highlight ? 'rgba(58,146,104,0.12)' : 'var(--bg-overlay)',
      border: `1px solid ${highlight ? 'var(--tag-tds-border)' : 'var(--glass-border)'}`,
      borderRadius: 'var(--r-sm)', padding: '4px 10px',
    }}>
      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{label}</div>
      <div style={{
        fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 600,
        color: highlight ? 'var(--text-accent)' : 'var(--text-data)',
      }}>{value}</div>
    </div>
  );
}
