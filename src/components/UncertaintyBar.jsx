/**
 * UncertaintyBar — displays a predicted value μ with ±σ confidence band.
 * Used in ExperimentDashboard and DecisionPanel for surrogate predictions.
 */
export default function UncertaintyBar({ mean, std, unit = '', target, direction, trained = true }) {
  if (mean === undefined || mean === null) return null;

  const fmt = (v) => typeof v === 'number' ? (Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(2)) : v;

  // Determine if prediction is moving toward target
  let statusColor = 'var(--accent, #3b82f6)';
  if (target !== undefined && target !== null) {
    const onTrack =
      direction === 'maximize' ? mean >= target * 0.8 :
      direction === 'minimize' ? mean <= target * 1.2 :
      Math.abs(mean - target) <= Math.abs(target) * 0.15;
    statusColor = onTrack ? '#22c55e' : '#f59e0b';
  }

  const uncertaintyPct = mean !== 0 ? Math.min(100, (std / (Math.abs(mean) + 1e-9)) * 100) : 50;

  return (
    <div style={{ fontSize: 11, marginBottom: 4 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 2 }}>
        <span style={{ color: statusColor, fontWeight: 600 }}>
          {fmt(mean)} {unit}
        </span>
        {std > 0 && (
          <span style={{ color: 'var(--text-muted)', fontSize: 10 }}>
            ±{fmt(std)} {unit}
          </span>
        )}
      </div>

      {/* Uncertainty band visualization */}
      <div style={{
        height: 4, background: 'rgba(255,255,255,0.08)', borderRadius: 2, position: 'relative', overflow: 'hidden'
      }}>
        {/* Main prediction bar */}
        <div style={{
          position: 'absolute', left: 0, top: 0, bottom: 0,
          width: `${Math.min(100, Math.max(5, (1 - uncertaintyPct / 100) * 100))}%`,
          background: statusColor, borderRadius: 2, opacity: 0.9,
          transition: 'width 0.4s ease',
        }} />
        {/* Uncertainty overlay */}
        {std > 0 && (
          <div style={{
            position: 'absolute', left: 0, top: 0, bottom: 0, width: '100%',
            background: `linear-gradient(90deg, transparent 60%, ${statusColor}33 100%)`,
            borderRadius: 2,
          }} />
        )}
      </div>

      {!trained && (
        <div style={{ fontSize: 9, color: '#f59e0b', marginTop: 2 }}>
          Prior estimate — no training data yet
        </div>
      )}

      {target !== undefined && target !== null && (
        <div style={{ fontSize: 9, color: 'var(--text-muted)', marginTop: 1 }}>
          Target: {direction === 'maximize' ? '≥' : direction === 'minimize' ? '≤' : '='} {fmt(target)} {unit}
        </div>
      )}
    </div>
  );
}
