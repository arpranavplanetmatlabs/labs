import { useState, useEffect, useRef } from 'react';
import { Brain, CheckCircle, Edit3, XCircle, ChevronRight, ArrowRight, Check, Loader } from 'lucide-react';
import { MOCK_DECISION_REASONING, MOCK_NEXT_HYPOTHESIS, MOCK_EXPERIMENTS, LOOP_STEPS } from '../mockData';

export default function DecisionPanel({ onApprove, onEditHypothesis, onStopLoop, loopState, loopLoading }) {
  const [approved, setApproved] = useState(false);
  const [editingHyp, setEditingHyp] = useState(false);
  const [hypDraft, setHypDraft] = useState('');

  const status    = loopState?.status ?? 'idle';
  const iteration = loopState?.iteration ?? 0;
  const reasoning = loopState?.reasoning || MOCK_DECISION_REASONING;
  const nextHyp   = loopState?.next_hypothesis || MOCK_NEXT_HYPOTHESIS;
  const best      = loopState?.best_candidate || MOCK_EXPERIMENTS[0];
  const activeStep = loopState?.active_step ?? 4;

  // Reset approved flag when a new iteration comes in
  useEffect(() => {
    if (status === 'awaiting_approval') setApproved(false);
  }, [status, iteration]);

  const handleApprove = async () => {
    setApproved(true);
    await onApprove?.();
  };

  const handleStartEdit = () => {
    setHypDraft(nextHyp);
    setEditingHyp(true);
  };

  const handleSaveEdit = async () => {
    setEditingHyp(false);
    await onEditHypothesis?.(hypDraft);
  };

  const handleStop = () => onStopLoop?.();

  const isRunning = loopLoading || status === 'running';
  const canApprove = status === 'awaiting_approval' && !approved && !isRunning;

  return (
    <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="panel-header">
        <Brain size={14} style={{ color: 'var(--accent)' }} />
        <span className="panel-title">Decision Reasoning</span>
        <div className="ml-auto flex items-center gap-sm">
          <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)' }}>
            {iteration > 0 ? `Iteration ${iteration}` : 'No iterations yet'}
          </span>
          {isRunning ? (
            <span className="tag tag-success" style={{ animation: 'pulse 1.5s ease-in-out infinite' }}>
              ⟳ Processing
            </span>
          ) : status === 'awaiting_approval' ? (
            <span className="tag tag-success">● Awaiting Approval</span>
          ) : approved ? (
            <span className="tag tag-success"><Check size={10} /> Approved</span>
          ) : (
            <span className="tag" style={{ color: 'var(--text-muted)', borderColor: 'var(--glass-border)' }}>
              {status === 'idle' ? 'Idle' : status === 'stopped' ? 'Stopped' : status}
            </span>
          )}
        </div>
      </div>

      {/* Loop progress bar */}
      <LoopProgressBar activeStep={activeStep} isRunning={isRunning} />

      <div className="panel-body scroll-area" style={{ height: 'calc(100% - 100px)', display: 'flex', flexDirection: 'column', gap: 12 }}>

        {/* Running spinner overlay */}
        {isRunning && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10,
            background: 'rgba(61,153,112,0.08)', border: '1px solid var(--accent)',
            borderRadius: 'var(--r-md)', padding: '10px 16px',
          }}>
            <Loader size={16} style={{ color: 'var(--accent)', animation: 'spin 1s linear infinite' }} />
            <span style={{ fontSize: 13, color: 'var(--accent)' }}>
              {LOOP_STEPS[activeStep] ?? 'Processing'}… LLM inference in progress
            </span>
          </div>
        )}

        {/* Winner chip */}
        {best && <WinnerChip exp={best} />}

        {/* Reasoning block */}
        <div>
          <SectionLabel>System Reasoning</SectionLabel>
          {isRunning
            ? <div style={{ height: 80, background: 'var(--bg-overlay)', borderRadius: 'var(--r-md)', animation: 'pulse 2s ease-in-out infinite' }} />
            : <TypewriterBlock key={reasoning} html={reasoning} />
          }
        </div>

        {/* Next hypothesis */}
        <div>
          <SectionLabel><ArrowRight size={11} style={{ display: 'inline', marginRight: 4 }} />Next Hypothesis</SectionLabel>
          {editingHyp ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              <textarea
                className="goal-textarea"
                rows={3}
                value={hypDraft}
                onChange={e => setHypDraft(e.target.value)}
                style={{ fontSize: 13 }}
                autoFocus
              />
              <div className="flex gap-sm">
                <button className="btn btn-approve btn-sm" onClick={handleSaveEdit}>Save</button>
                <button className="btn btn-ghost btn-sm" onClick={() => setEditingHyp(false)}>Cancel</button>
              </div>
            </div>
          ) : (
            <div className="hypothesis-card" onClick={handleStartEdit} style={{ cursor: 'pointer' }} title="Click to edit">
              <div className="hyp-icon">🔬</div>
              <div>
                <div className="hyp-label">
                  {iteration > 0 ? `Iteration ${iteration + 1} Proposal` : 'Starting Hypothesis'}
                </div>
                <div className="hyp-text">{nextHyp}</div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Approval row */}
      <div className="approval-row">
        <button
          id="btn-approve-iter"
          className="btn btn-approve"
          onClick={handleApprove}
          disabled={!canApprove}
          title={!canApprove && !isRunning ? 'Nothing pending approval' : ''}
        >
          <CheckCircle size={14} />
          {approved ? 'Approved!' : isRunning ? 'Processing…' : 'Approve & Continue'}
        </button>
        <button
          id="btn-edit-hyp"
          className="btn btn-edit"
          onClick={handleStartEdit}
          disabled={isRunning}
        >
          <Edit3 size={14} />
          Edit Hypothesis
        </button>
        <button
          id="btn-stop-loop"
          className="btn btn-stop ml-auto"
          onClick={handleStop}
          disabled={status === 'idle' || status === 'stopped'}
        >
          <XCircle size={14} />
          Stop Loop
        </button>
      </div>
    </div>
  );
}

/* ── Loop progress bar ── */
function LoopProgressBar({ activeStep, isRunning }) {
  return (
    <div className="loop-status-bar">
      {LOOP_STEPS.map((step, i) => (
        <div key={step} className="flex items-center gap-sm">
          <div className={`loop-step ${i < activeStep ? 'done' : i === activeStep ? 'active' : ''}`}>
            <span style={{
              width: 16, height: 16, borderRadius: '50%', display: 'inline-flex',
              alignItems: 'center', justifyContent: 'center', fontSize: 9, fontWeight: 700,
              background: i < activeStep ? 'var(--accent-dim)' : i === activeStep ? 'var(--accent)' : 'var(--bg-overlay)',
              color: i <= activeStep ? '#fff' : 'var(--text-muted)',
              boxShadow: i === activeStep ? '0 0 8px var(--accent-glow)' : 'none',
              flexShrink: 0,
              animation: i === activeStep && isRunning ? 'pulse 1s ease-in-out infinite' : 'none',
            }}>
              {i < activeStep ? '✓' : i + 1}
            </span>
            {step}
          </div>
          {i < LOOP_STEPS.length - 1 && (
            <ChevronRight size={12} style={{ color: i < activeStep ? 'var(--accent-dim)' : 'var(--text-muted)', flexShrink: 0 }} />
          )}
        </div>
      ))}
    </div>
  );
}

/* ── Winner banner ── */
function WinnerChip({ exp }) {
  if (!exp) return null;
  const score = exp.composite_score ?? exp.confidence_score ?? 0;
  const tensile = exp.predicted?.tensile_strength ?? exp.scores?.strength;
  const elong   = exp.predicted?.elongation ?? exp.scores?.flexibility;
  return (
    <div style={{
      background: 'linear-gradient(135deg, rgba(58,146,104,0.12), rgba(58,146,104,0.04))',
      border: '1px solid var(--tag-tds-border)',
      borderRadius: 'var(--r-md)', padding: '10px 16px',
      display: 'flex', alignItems: 'center', gap: 12,
    }}>
      <span style={{ fontSize: 22 }}>🏆</span>
      <div>
        <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.7px', marginBottom: 2 }}>
          Selected Configuration
        </div>
        <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text-primary)' }}>
          {exp.label ?? exp.name ?? 'Best Config'}
          <span style={{ marginLeft: 12, fontFamily: 'var(--font-mono)', fontSize: 18, color: 'var(--score-high)' }}>
            {typeof score === 'number' ? score.toFixed(3) : 'N/A'}
          </span>
        </div>
      </div>
      <div className="flex gap-sm ml-auto">
        {tensile != null && <MiniProp label="Tensile" value={`${typeof tensile === 'number' ? tensile.toFixed(1) : tensile} MPa`} ok={tensile >= 45} />}
        {elong   != null && <MiniProp label="Elong."  value={`${typeof elong   === 'number' ? elong.toFixed(0)   : elong}%`}      ok={elong >= 150}  />}
      </div>
    </div>
  );
}

function MiniProp({ label, value, ok }) {
  return (
    <div style={{
      background: ok ? 'rgba(58,146,104,0.12)' : 'var(--bg-overlay)',
      border: `1px solid ${ok ? 'var(--tag-tds-border)' : 'var(--glass-border)'}`,
      borderRadius: 'var(--r-sm)', padding: '4px 10px', textAlign: 'center',
    }}>
      <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{label}</div>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, fontWeight: 700, color: ok ? 'var(--text-accent)' : 'var(--text-data)' }}>
        {value}
      </div>
    </div>
  );
}

/* ── Typewriter reasoning block ── */
function TypewriterBlock({ html }) {
  const [displayed, setDisplayed] = useState('');
  const [done, setDone] = useState(false);
  const indexRef = useRef(0);
  const plain = (html || '').replace(/<[^>]*>/g, '');

  useEffect(() => {
    setDisplayed('');
    setDone(false);
    indexRef.current = 0;

    if (!plain) return;

    const interval = setInterval(() => {
      indexRef.current += 3;
      if (indexRef.current >= plain.length) {
        setDisplayed(plain);
        setDone(true);
        clearInterval(interval);
      } else {
        setDisplayed(plain.slice(0, indexRef.current));
      }
    }, 18);

    return () => clearInterval(interval);
  }, [html]);

  return (
    <div className="decision-reasoning-block" style={{ minHeight: 80 }}>
      {done
        ? <span dangerouslySetInnerHTML={{ __html: html }} />
        : <span>{displayed}<span className="typewriter-cursor" /></span>
      }
    </div>
  );
}

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 10, textTransform: 'uppercase', letterSpacing: '0.8px',
      color: 'var(--text-muted)', marginBottom: 6, display: 'flex', alignItems: 'center', gap: 4,
    }}>
      {children}
    </div>
  );
}
