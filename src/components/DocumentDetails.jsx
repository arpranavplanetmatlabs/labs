import { useState, useEffect } from 'react';
import { X, FileText, Loader, AlertCircle, CheckCircle, Clock, Info } from 'lucide-react';

const API_BASE = 'http://localhost:8000';

function getConfidenceColor(confidence) {
  if (confidence >= 0.9) return 'var(--score-high)';
  if (confidence >= 0.7) return '#b8943a';
  if (confidence >= 0.5) return '#c47ee6';
  return 'var(--score-low)';
}

function getConfidenceLabel(confidence) {
  if (confidence >= 0.9) return 'High';
  if (confidence >= 0.7) return 'Medium';
  if (confidence >= 0.5) return 'Low';
  return 'Very Low';
}

function ConfidenceBadge({ confidence }) {
  if (!confidence && confidence !== 0) return null;
  return (
    <span style={{
      display: 'inline-flex',
      alignItems: 'center',
      gap: 4,
      padding: '2px 8px',
      borderRadius: 12,
      fontSize: 10,
      fontWeight: 600,
      background: `${getConfidenceColor(confidence)}22`,
      color: getConfidenceColor(confidence),
      border: `1px solid ${getConfidenceColor(confidence)}44`,
    }}>
      <span style={{
        width: 6,
        height: 6,
        borderRadius: '50%',
        background: getConfidenceColor(confidence)
      }} />
      {getConfidenceLabel(confidence)} ({Math.round(confidence * 100)}%)
    </span>
  );
}

export default function DocumentDetails({ document, onClose }) {
  const [activeTab, setActiveTab] = useState('properties');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [usePassedData, setUsePassedData] = useState(false);

  useEffect(() => {
    if (document?.id) {
      // If already has properties in passed data, use that directly
      if (document.properties && document.properties.length > 0) {
        setData({
          ...document,
          extraction_status: 'completed',
          extraction_confidence: document.extraction_confidence || 0.8,
          additional_data: {
            conditions: { content: document.processing_conditions || [] },
            key_findings: { content: [] },
            formulations: { content: [] },
            limitations: { content: [] },
            methodology: { content: '' }
          }
        });
        setUsePassedData(true);
        setLoading(false);
      } else {
        fetchDocumentDetails();
      }
    }
  }, [document]);

  const fetchDocumentDetails = async () => {
    setLoading(true);
    try {
      if (document.isQdrant) {
        const res = await fetch(`${API_BASE}/api/parsed/${document.id}`);
        if (res.ok) {
          const result = await res.json();
          const payload = result.payload || {};
          
          // Helper to parse JSON strings if needed
          const parseJSON = (val) => {
            if (typeof val === 'string') {
              try { return JSON.parse(val); } catch (e) { return val; }
            }
            return val;
          };

          // Map Qdrant payload to component's expected data structure
          const mappedData = {
            id: document.id,
            filename: payload.filename,
            doc_type: payload.doc_type,
            extraction_status: 'completed',
            extraction_confidence: payload.extraction_confidence,
            properties: parseJSON(payload.properties || '[]').map(p => ({
              property: p.name || p.property,
              value: p.value,
              unit: p.unit,
              confidence: p.confidence || 0.8,
              context: p.context
            })),
            additional_data: {
              key_findings: { content: parseJSON(payload.key_findings || '[]') },
              conditions: { content: parseJSON(payload.processing_conditions || '[]') },
              formulations: { content: parseJSON(payload.formulations || '[]') },
              limitations: { content: parseJSON(payload.limitations || '[]') },
              methodology: { content: payload.methodology }
            },
            llm_output: payload // Show entire payload in Raw Data tab
          };
          setData(mappedData);
        }
      } else {
        const res = await fetch(`${API_BASE}/api/documents/${document.id}`);
        if (res.ok) {
          const result = await res.json();
          setData(result);
        }
      }
    } catch (err) {
      console.error('Failed to fetch document details:', err);
    } finally {
      setLoading(false);
    }
  };

  const getLoadingMessage = () => {
    if (usePassedData) return 'Loading...';
    const status = data?.extraction_status || '';
    if (status === 'processing') return 'Extracting with AI...';
    if (status === 'queued') return 'Waiting in queue...';
    if (status === 'completed') return 'Loading...';
    return 'Loading...';
  };

  const handleBackdropClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  if (!document) return null;

  const overallConfidence = data?.extraction_confidence || 0;

  return (
    <div style={{
      position: 'fixed',
      inset: 0,
      background: 'rgba(0, 0, 0, 0.7)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      backdropFilter: 'blur(4px)',
    }} onClick={handleBackdropClick}>
      <div style={{
        background: 'var(--bg-surface)',
        border: '1px solid var(--glass-border)',
        borderRadius: 'var(--r-lg)',
        width: '92%',
        maxWidth: 900,
        maxHeight: '88vh',
        display: 'flex',
        flexDirection: 'column',
        overflow: 'hidden',
        boxShadow: '0 20px 60px rgba(0, 0, 0, 0.5)',
      }}>
        {/* Header */}
        <div style={{
          padding: '16px 24px',
          borderBottom: '1px solid var(--glass-border)',
          display: 'flex',
          alignItems: 'center',
          gap: 12,
        }}>
          <FileText size={20} style={{ color: 'var(--accent)' }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>
              {document.filename}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4, display: 'flex', alignItems: 'center', gap: 8 }}>
              <span className={`tag ${document.doc_type === 'tds' ? 'tag-tds' : 'tag-paper'}`}>
                {document.doc_type?.toUpperCase()}
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <Clock size={10} />
                {data?.extraction_status || 'Processing'}
              </span>
              <ConfidenceBadge confidence={overallConfidence} />
            </div>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: '1px solid var(--glass-border)',
              borderRadius: 'var(--r-sm)',
              padding: '6px 8px',
              cursor: 'pointer',
              color: 'var(--text-muted)',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X size={16} />
          </button>
        </div>

        {/* Tabs */}
        <div style={{
          padding: '12px 24px',
          borderBottom: '1px solid var(--glass-border)',
          display: 'flex',
          gap: 8,
        }}>
          <TabButton active={activeTab === 'properties'} onClick={() => setActiveTab('properties')} label="Properties" />
          <TabButton active={activeTab === 'methodology'} onClick={() => setActiveTab('methodology')} label="Methodology" />
          <TabButton active={activeTab === 'findings'} onClick={() => setActiveTab('findings')} label="Findings" />
          <TabButton active={activeTab === 'limitations'} onClick={() => setActiveTab('limitations')} label="Limitations" />
          <TabButton active={activeTab === 'raw'} onClick={() => setActiveTab('raw')} label="Raw Data" />
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflow: 'auto', padding: 24 }}>
          {loading ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200 }}>
              <Loader size={24} style={{ animation: 'spin 1s linear infinite', color: 'var(--accent)' }} />
              <span style={{ marginLeft: 12, color: 'var(--text-muted)' }}>{getLoadingMessage()}</span>
            </div>
          ) : (
            <>
              {activeTab === 'properties' && <PropertiesTab properties={data?.properties || []} />}
              {activeTab === 'methodology' && <MethodologyTab data={data?.additional_data || {}} />}
              {activeTab === 'findings' && <FindingsTab data={data?.additional_data || {}} />}
              {activeTab === 'limitations' && <LimitationsTab data={data?.additional_data || {}} />}
              {activeTab === 'raw' && <RawDataTab data={data?.llm_output} />}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function TabButton({ active, onClick, label }) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 6,
        padding: '8px 16px',
        borderRadius: 'var(--r-md)',
        border: 'none',
        cursor: 'pointer',
        fontSize: 12,
        fontWeight: 500,
        background: active ? 'var(--glass-active)' : 'transparent',
        color: active ? 'var(--text-accent)' : 'var(--text-muted)',
        transition: 'all 0.15s ease',
      }}
    >
      {label}
    </button>
  );
}

function PropertiesTab({ properties }) {
  if (!properties || properties.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
        <AlertCircle size={48} style={{ opacity: 0.3, marginBottom: 12 }} />
        <div>No properties extracted yet</div>
        <div style={{ fontSize: 11, marginTop: 4 }}>Properties will appear after AI extraction</div>
      </div>
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
        <Info size={14} style={{ color: 'var(--text-muted)' }} />
        <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
          {properties.length} properties extracted with AI confidence scoring
        </span>
      </div>
      <table style={{ width: '100%', borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase' }}>
            <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '1px solid var(--glass-border)' }}>Property</th>
            <th style={{ textAlign: 'right', padding: '8px 12px', borderBottom: '1px solid var(--glass-border)' }}>Value</th>
            <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '1px solid var(--glass-border)' }}>Unit</th>
            <th style={{ textAlign: 'center', padding: '8px 12px', borderBottom: '1px solid var(--glass-border)' }}>Confidence</th>
            <th style={{ textAlign: 'left', padding: '8px 12px', borderBottom: '1px solid var(--glass-border)' }}>Context</th>
          </tr>
        </thead>
        <tbody>
          {properties.map((prop, i) => (
            <tr key={i} style={{ fontSize: 13 }}>
              <td style={{ padding: '10px 12px', borderBottom: '1px solid var(--glass-border)', color: 'var(--text-secondary)' }}>
                {prop.property}
              </td>
              <td style={{ padding: '10px 12px', borderBottom: '1px solid var(--glass-border)', textAlign: 'right', fontFamily: 'var(--font-mono)', color: 'var(--text-data)', fontWeight: 600 }}>
                {prop.value}
              </td>
              <td style={{ padding: '10px 12px', borderBottom: '1px solid var(--glass-border)', color: 'var(--text-muted)' }}>
                {prop.unit || '-'}
              </td>
              <td style={{ padding: '10px 12px', borderBottom: '1px solid var(--glass-border)', textAlign: 'center' }}>
                <ConfidenceBadge confidence={prop.confidence} />
              </td>
              <td style={{ padding: '10px 12px', borderBottom: '1px solid var(--glass-border)', color: 'var(--text-muted)', fontSize: 11, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                {prop.context || '-'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MethodologyTab({ data }) {
  const methodology = data?.methodology?.content || '';
  const conditions = data?.conditions?.content || [];

  if (!methodology && conditions.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
        <Info size={48} style={{ opacity: 0.3, marginBottom: 12 }} />
        <div>No methodology information extracted</div>
      </div>
    );
  }

  return (
    <div>
      {methodology && (
        <div style={{ marginBottom: 24 }}>
          <h4 style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 8 }}>Experimental Methods</h4>
          <div style={{ 
            background: 'var(--bg-overlay)', 
            borderRadius: 'var(--r-md)', 
            padding: 16, 
            fontSize: 13, 
            color: 'var(--text-secondary)', 
            lineHeight: 1.7 
          }}>
            {methodology}
          </div>
        </div>
      )}
      
      {conditions.length > 0 && (
        <div>
          <h4 style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 8 }}>Conditions Tested</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {conditions.map((c, i) => (
              <div key={i} style={{ 
                background: 'var(--bg-overlay)', 
                borderRadius: 'var(--r-sm)', 
                padding: '10px 14px',
                display: 'flex',
                alignItems: 'center',
                gap: 12
              }}>
                <span style={{ color: 'var(--text-primary)', flex: 1 }}>{c.name || c.condition || c.finding || c}</span>
                <ConfidenceBadge confidence={c.confidence} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function FindingsTab({ data }) {
  const findings = data?.key_findings?.content || [];
  const formulations = data?.formulations?.content || [];

  if (findings.length === 0 && formulations.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
        <CheckCircle size={48} style={{ opacity: 0.3, marginBottom: 12 }} />
        <div>No key findings extracted</div>
      </div>
    );
  }

  return (
    <div>
      {findings.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <h4 style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 8 }}>Key Findings</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {findings.map((f, i) => (
              <div key={i} style={{ 
                background: 'var(--bg-overlay)', 
                borderRadius: 'var(--r-md)', 
                padding: 14,
                borderLeft: '3px solid var(--accent)'
              }}>
                <div style={{ color: 'var(--text-primary)', fontSize: 13, marginBottom: 6 }}>{f.finding}</div>
                <ConfidenceBadge confidence={f.confidence} />
              </div>
            ))}
          </div>
        </div>
      )}
      
      {formulations.length > 0 && (
        <div>
          <h4 style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 8 }}>Formulations Tested</h4>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {formulations.map((f, i) => (
              <div key={i} style={{ 
                background: 'var(--bg-overlay)', 
                borderRadius: 'var(--r-md)', 
                padding: 14
              }}>
                <div style={{ color: 'var(--text-accent)', fontSize: 12, marginBottom: 4 }}>{f.composition}</div>
                <div style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{f.results}</div>
                <ConfidenceBadge confidence={f.confidence} />
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function LimitationsTab({ data }) {
  const limitations = data?.limitations?.content || [];

  if (limitations.length === 0) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
        <CheckCircle size={48} style={{ opacity: 0.3, marginBottom: 12 }} />
        <div>No limitations mentioned or detected</div>
        <div style={{ fontSize: 11, marginTop: 4 }}>This is good - authors may not have listed explicit limitations</div>
      </div>
    );
  }

  return (
    <div>
      <h4 style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 12 }}>Limitations Mentioned</h4>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {limitations.map((l, i) => (
          <div key={i} style={{ 
            background: 'rgba(146,58,58,0.1)', 
            border: '1px solid rgba(146,58,58,0.3)',
            borderRadius: 'var(--r-md)', 
            padding: 14,
            display: 'flex',
            alignItems: 'flex-start',
            gap: 12
          }}>
            <AlertCircle size={16} style={{ color: 'var(--score-low)', flexShrink: 0, marginTop: 2 }} />
            <div style={{ flex: 1 }}>
              <div style={{ color: 'var(--text-primary)', fontSize: 13 }}>{l.limitation}</div>
              <ConfidenceBadge confidence={l.confidence} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function RawDataTab({ data }) {
  if (!data) {
    return (
      <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
        <Info size={48} style={{ opacity: 0.3, marginBottom: 12 }} />
        <div>No raw data available</div>
      </div>
    );
  }

  return (
    <div>
      <h4 style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', marginBottom: 12 }}>Raw LLM Output</h4>
      <pre style={{ 
        background: 'var(--bg-overlay)', 
        borderRadius: 'var(--r-md)', 
        padding: 16, 
        fontSize: 11,
        fontFamily: 'var(--font-mono)',
        color: 'var(--text-secondary)',
        overflow: 'auto',
        maxHeight: 500,
        whiteSpace: 'pre-wrap',
        wordBreak: 'break-word'
      }}>
        {JSON.stringify(data, null, 2)}
      </pre>
    </div>
  );
}
