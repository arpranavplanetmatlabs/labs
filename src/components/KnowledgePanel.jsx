import { useState } from 'react';
import { BookOpen, Layers, Lightbulb, ExternalLink, Search } from 'lucide-react';
import { MOCK_PAPERS, MOCK_INSIGHTS } from '../mockData';

export default function KnowledgePanel() {
  const [tab, setTab] = useState('papers');
  const [query, setQuery] = useState('');

  const filteredPapers = MOCK_PAPERS.filter(p =>
    !query || p.title.toLowerCase().includes(query.toLowerCase()) || p.authors.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <div className="panel-header">
        <BookOpen size={14} style={{ color: 'var(--accent)' }} />
        <span className="panel-title">Knowledge View</span>
        <div className="ml-auto flex items-center gap-sm">
          <div className="pill-tabs">
            <button id="tab-papers"   className={`pill-tab${tab === 'papers'   ? ' active' : ''}`} onClick={() => setTab('papers')}>Papers</button>
            <button id="tab-insights" className={`pill-tab${tab === 'insights' ? ' active' : ''}`} onClick={() => setTab('insights')}>Insights</button>
          </div>
        </div>
      </div>

      {/* Search bar */}
      <div style={{ padding: '8px 16px', borderBottom: '1px solid var(--glass-border)' }}>
        <div className="flex items-center gap-sm" style={{
          background: 'var(--bg-overlay)', borderRadius: 'var(--r-sm)',
          border: '1px solid var(--glass-border)', padding: '6px 10px',
        }}>
          <Search size={12} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
          <input
            id="knowledge-search"
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder={tab === 'papers' ? 'Search papers & TDS…' : 'Search insights…'}
            style={{
              background: 'transparent', border: 'none', outline: 'none',
              color: 'var(--text-primary)', fontSize: 12, width: '100%',
            }}
          />
        </div>
      </div>

      <div className="panel-body scroll-area" style={{ height: 'calc(100% - 100px)' }}>
        {tab === 'papers' ? (
          <div className="stagger-children">
            {filteredPapers.map(p => <PaperCard key={p.id} paper={p} />)}
          </div>
        ) : (
          <div className="stagger-children">
            {MOCK_INSIGHTS.map(i => <InsightChip key={i.id} insight={i} />)}
          </div>
        )}
      </div>
    </div>
  );
}

function PaperCard({ paper }) {
  return (
    <div className={`know-card anim-fade-in`} id={`paper-${paper.id}`}>
      <div className="flex items-center gap-sm mb-sm">
        <span className={`tag ${paper.type === 'tds' ? 'tag-tds' : 'tag-paper'}`}>
          {paper.type === 'tds' ? '⬡ TDS' : '📄 Paper'}
        </span>
        <span className="tag tag-success" style={{ marginLeft: 'auto' }}>
          {(paper.relevance * 100).toFixed(0)}% match
        </span>
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2, lineHeight: 1.4 }}>
        {paper.title}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginBottom: 8 }}>
        {paper.authors} · {paper.year}
        {paper.status === 'processing' && (
          <span className="tag tag-warning" style={{ marginLeft: 8 }}>Processing…</span>
        )}
      </div>
      <div style={{ fontSize: 12, color: 'var(--text-secondary)', lineHeight: 1.5, marginBottom: 8 }}>
        {paper.excerpt}
      </div>

      {paper.type === 'tds' && paper.properties && (
        <div className="flex gap-sm" style={{ flexWrap: 'wrap', marginBottom: 8 }}>
          {Object.entries(paper.properties).map(([k, v]) => (
            <div key={k} className="metric-chip" style={{ minWidth: 80 }}>
              <div className="metric-chip-value" style={{ fontSize: 13 }}>{v}</div>
              <div className="metric-chip-label">{k.replace(/_/g, ' ')}</div>
            </div>
          ))}
        </div>
      )}

      <div className="flex items-center gap-sm" style={{ fontSize: 11, color: 'var(--text-muted)' }}>
        <Layers size={11} /> {paper.chunks} chunks
        {paper.insights > 0 && (
          <><Lightbulb size={11} style={{ marginLeft: 4 }} /> {paper.insights} insights</>
        )}
        <button className="btn btn-ghost btn-sm ml-auto" style={{ padding: '3px 8px', fontSize: 11 }}>
          <ExternalLink size={10} /> View
        </button>
      </div>
    </div>
  );
}

function InsightChip({ insight }) {
  return (
    <div className="insight-chip anim-fade-in" id={`insight-${insight.id}`}>
      <Lightbulb size={14} style={{ color: 'var(--score-mid)', flexShrink: 0, marginTop: 2 }} />
      <div style={{ flex: 1 }}>
        <div style={{ marginBottom: 4 }}>
          <span className="cause">{insight.cause}</span>
          <span style={{ color: 'var(--text-muted)', margin: '0 6px' }}>→</span>
          <span className="effect">{insight.effect}</span>
        </div>
        <div className="flex items-center gap-sm">
          <div className="score-bar-wrapper" style={{ flex: 1 }}>
            <div className="score-bar-track">
              <div className="score-bar-fill" style={{
                width: `${insight.confidence * 100}%`,
                background: `linear-gradient(90deg, var(--accent-dim), var(--accent-bright))`,
              }} />
            </div>
            <div className="score-bar-label">{(insight.confidence * 100).toFixed(0)}%</div>
          </div>
          <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
            [{insight.source}]
          </span>
        </div>
      </div>
    </div>
  );
}
