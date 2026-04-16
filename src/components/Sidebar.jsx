import { useRef, useCallback } from 'react';
import { Microscope, FileText, FlaskConical, BarChart3, Brain, MessageSquare, Cpu, Database, Zap } from 'lucide-react';

const NAV_ITEMS = [
  { id: 'research', label: 'Research', icon: Microscope, badge: null },
  { id: 'papers', label: 'Papers', icon: FileText, badge: null },
  { id: 'experiments', label: 'Experiments', icon: FlaskConical, badge: null },
  { id: 'results', label: 'Results', icon: BarChart3, badge: null },
  { id: 'decisions', label: 'Decisions', icon: Brain, badge: null },
  { id: 'chat', label: 'Chat', icon: MessageSquare, badge: null },
];

export default function Sidebar({ active, onNav, counts = {} }) {
  const navRefs = useRef({});

  const handleKeyDown = useCallback((e, id, index) => {
    let nextIndex = index;
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
      e.preventDefault();
      nextIndex = (index + 1) % NAV_ITEMS.length;
    } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
      e.preventDefault();
      nextIndex = (index - 1 + NAV_ITEMS.length) % NAV_ITEMS.length;
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onNav(id);
      return;
    }
    
    if (nextIndex !== index) {
      navRefs.current[NAV_ITEMS[nextIndex].id]?.focus();
    }
  }, [onNav]);

  const getBadge = (id) => {
    if (id === 'papers') return counts.documents || null;
    if (id === 'experiments') return counts.experiments || null;
    return null;
  };

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="logo-mark">
          <div className="logo-icon">M</div>
          <span className="logo-text">Planet Material Labs</span>
        </div>
        <div className="logo-sub">Material Experimentation Lab + AI</div>
      </div>

      <p className="sidebar-section-label">Workspace</p>
      <ul className="sidebar-nav stagger-children" role="menubar">
        {NAV_ITEMS.map(({ id, label, icon: Icon, badge }, index) => (
          <li
            key={id}
            id={`nav-${id}`}
            className={`sidebar-nav-item anim-slide-in${active === id ? ' active' : ''}`}
            onClick={() => onNav(id)}
            onKeyDown={(e) => handleKeyDown(e, id, index)}
            ref={(el) => navRefs.current[id] = el}
            role="menuitem"
            tabIndex={active === id ? 0 : -1}
            aria-current={active === id ? 'page' : undefined}
          >
            <span className="nav-icon"><Icon size={16} /></span>
            {label}
            {badge && <span className="nav-badge">{badge}</span>}
            {!badge && getBadge(id) > 0 && <span className="nav-badge">{getBadge(id)}</span>}
          </li>
        ))}
      </ul>

      <div className="sidebar-status">
        <p className="sidebar-section-label" style={{ padding: '0 0 8px' }}>System</p>
        <div className="flex flex-col gap-sm">
          <StatusRow icon={<Cpu size={12} />} label="Ollama" state="online" detail="qwen2.5:3b" />
          <StatusRow icon={<Database size={12} />} label="Qdrant" state="online" detail={`${counts.qdrant_parsed || 0} pts`} />
          <StatusRow icon={<Zap size={12} />} label="DuckDB" state="online" detail={`${counts.experiments || 0} exps`} />
        </div>
      </div>
    </aside>
  );
}

function StatusRow({ icon, label, state, detail }) {
  return (
    <div className="status-dot" style={{ justifyContent: 'space-between' }}>
      <div className="flex items-center gap-sm" style={{ color: 'var(--text-muted)', fontSize: 11, gap: 5 }}>
        <span className={`status-dot-indicator${state !== 'online' ? ' offline' : ''}`} />
        {icon}
        <span>{label}</span>
      </div>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>{detail}</span>
    </div>
  );
}
