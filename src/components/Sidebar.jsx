import { useRef, useCallback } from 'react';
import { Microscope, FileText, FlaskConical, BarChart3, Brain, MessageSquare, Cpu, Database, Zap, ChevronLeft, ChevronRight } from 'lucide-react';

const NAV_ITEMS = [
  { id: 'research',     label: 'Research',     icon: Microscope },
  { id: 'papers',       label: 'Papers',       icon: FileText },
  { id: 'experiments',  label: 'Experiments',  icon: FlaskConical },
  { id: 'results',      label: 'Results',      icon: BarChart3 },
  { id: 'decisions',    label: 'Decisions',    icon: Brain },
  { id: 'chat',         label: 'Chat',         icon: MessageSquare },
];

export default function Sidebar({ active, onNav, counts = {}, collapsed = false, onToggleCollapse }) {
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
    <aside className={`sidebar${collapsed ? ' collapsed' : ''}`}>
      {/* Collapse toggle button */}
      <button
        className="sidebar-collapse-btn"
        onClick={onToggleCollapse}
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <ChevronRight size={12} /> : <ChevronLeft size={12} />}
      </button>

      {/* Logo */}
      <div className="sidebar-logo">
        <div className="logo-mark">
          <div className="logo-icon">M</div>
          <span className="logo-text sidebar-label-text">Planet Material Labs</span>
        </div>
        <div className="logo-sub sidebar-label-text">Material Experimentation Lab + AI</div>
      </div>

      {!collapsed && <p className="sidebar-section-label">Workspace</p>}

      <ul className="sidebar-nav stagger-children" role="menubar">
        {NAV_ITEMS.map(({ id, label, icon: Icon }, index) => {
          const badge = getBadge(id);
          return (
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
              title={collapsed ? label : undefined}
            >
              <span className="nav-icon"><Icon size={16} /></span>
              <span className="sidebar-label-text">{label}</span>
              {badge > 0 && !collapsed && (
                <span className="nav-badge">{badge}</span>
              )}
            </li>
          );
        })}
      </ul>

      <div className="sidebar-status">
        {!collapsed && <p className="sidebar-section-label" style={{ padding: '0 0 8px' }}>System</p>}
        <div className="flex flex-col gap-sm">
          <StatusRow icon={<Cpu size={12} />} label="Ollama" state="online" detail="qwen2.5:3b" collapsed={collapsed} />
          <StatusRow icon={<Database size={12} />} label="Qdrant" state="online" detail={`${counts.qdrant_parsed || 0} pts`} collapsed={collapsed} />
          <StatusRow icon={<Zap size={12} />} label="Engine" state="online" detail={`${counts.experiments || 0} exps`} collapsed={collapsed} />
        </div>
      </div>
    </aside>
  );
}

function StatusRow({ icon, label, state, detail, collapsed }) {
  return (
    <div className="status-dot" style={{ justifyContent: collapsed ? 'center' : 'space-between' }} title={collapsed ? `${label}: ${detail}` : undefined}>
      <div className="flex items-center gap-sm" style={{ color: 'var(--text-muted)', fontSize: 11, gap: 5 }}>
        <span className={`status-dot-indicator${state !== 'online' ? ' offline' : ''}`} />
        {icon}
        {!collapsed && <span className="status-label">{label}</span>}
      </div>
      {!collapsed && <span className="status-detail" style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)' }}>{detail}</span>}
    </div>
  );
}
