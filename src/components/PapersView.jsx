import { useState, useEffect, useRef } from 'react';
import { FileText, Upload, CheckCircle, AlertCircle, Loader, Clock, FolderOpen, Search, Database, Cpu, Trash2 } from 'lucide-react';
import DocumentDetails from './DocumentDetails';

const API_BASE = 'http://localhost:8000';

const STATUS_ICON = {
  pending: <Clock size={12} style={{ color: 'var(--text-muted)', animation: 'spin 1s linear infinite' }} />,
  processing: <Loader size={12} style={{ color: 'var(--score-mid)', animation: 'spin 1s linear infinite' }} />,
  completed: <CheckCircle size={12} style={{ color: 'var(--score-high)' }} />,
  failed: <AlertCircle size={12} style={{ color: 'var(--score-low)' }} />,
};

export default function PapersView() {
  const [papers, setPapers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [selectedDoc, setSelectedDoc] = useState(null);
  const [stats, setStats] = useState({ documents: 0, tds: 0, papers: 0, qdrant_parsed: 0 });
  const [bulkProcessing, setBulkProcessing] = useState(false);
  const [bulkProgress, setBulkProgress] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [parsedDocs, setParsedDocs] = useState([]);
  const [showParsed, setShowParsed] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [queuedJobs, setQueuedJobs] = useState([]);
  const inputRef = useRef();
  const folderInputRef = useRef();
  const jobsPollRef = useRef(null);

  useEffect(() => {
    fetchDocuments();
    fetchStats();
    fetchJobs();
    
    const interval = setInterval(() => {
      fetchDocuments();
      fetchStats();
      fetchJobs();
    }, 3000);
    
    return () => {
      clearInterval(interval);
      if (jobsPollRef.current) clearInterval(jobsPollRef.current);
    };
  }, []);

  const fetchDocuments = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/documents`);
      if (res.ok) {
        const data = await res.json();
        setPapers(data);
      }
    } catch (err) {
      console.error('Failed to fetch documents:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/stats`);
      if (res.ok) {
        const data = await res.json();
        setStats(data);
      }
    } catch (err) {
      console.error('Failed to fetch stats:', err);
    }
  };

  const fetchJobs = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/jobs?limit=20`);
      if (res.ok) {
        const data = await res.json();
        const activeJobs = data.jobs.filter(j => 
          ['queued', 'running', 'pending'].includes(j.status)
        );
        setQueuedJobs(activeJobs);
        
        if (activeJobs.length > 0) {
          const running = activeJobs.find(j => j.status === 'running');
          if (running) {
            setBulkProcessing(true);
            setBulkProgress({
              current: activeJobs.length,
              total: data.jobs.length,
              pct: ((data.jobs.length - activeJobs.length) / data.jobs.length) * 100,
              message: running.current_step || 'Processing...'
            });
          }
        } else {
          setBulkProcessing(false);
          setBulkProgress(null);
        }
      }
    } catch (err) {
      console.error('Failed to fetch jobs:', err);
    }
  };

  const handleFiles = async (files) => {
    if (!files?.length) return;
    
    const pdfFiles = Array.from(files).filter(f => f.name.endsWith('.pdf'));
    if (pdfFiles.length === 0) return;
    
    setUploading(true);
    setUploadProgress({ current: 0, total: pdfFiles.length, queued: 0 });
    
    const uploadPromises = pdfFiles.map(async (file, index) => {
      const formData = new FormData();
      formData.append('file', file);
      
      try {
        const res = await fetch(`${API_BASE}/api/documents/upload`, {
          method: 'POST',
          body: formData,
        });
        
        const result = await res.json();
        setUploadProgress(prev => ({ ...prev, queued: (prev?.queued || 0) + 1 }));
        
        if (res.ok) {
          await fetchJobs();
          return { success: true, filename: file.name, job_id: result.job_id };
        } else {
          return { success: false, filename: file.name, error: result.detail };
        }
      } catch (err) {
        return { success: false, filename: file.name, error: err.message };
      }
    });
    
    const results = await Promise.all(uploadPromises);
    
    setUploading(false);
    setUploadProgress(null);
    
    const successCount = results.filter(r => r.success).length;
    console.log(`Queued ${successCount}/${pdfFiles.length} files for processing`);
    
    await fetchJobs();
    await fetchStats();
  };

  const handleBulkParse = async () => {
    const folderPath = prompt('Enter folder path to parse:', 'E:\\rlresearchassistant\\backend\\data\\parsed');
    if (!folderPath) return;
    
    setBulkProcessing(true);
    setBulkProgress({ current: 0, total: 0, pct: 0, message: 'Starting...' });
    
    try {
      const response = await fetch(`${API_BASE}/api/bulk-parse`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ folder_path: folderPath, resume: true })
      });
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        
        const lines = decoder.decode(value).split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'progress') {
                setBulkProgress({ current: event.current, total: event.total, pct: event.pct, message: `Processing ${event.current}/${event.total}` });
              } else if (event.type === 'status') {
                setBulkProgress(prev => ({ ...prev, message: event.message }));
              } else if (event.type === 'summary') {
                setBulkProgress({ current: event.total, total: event.total, pct: 100, message: event.message });
                setTimeout(() => {
                  setBulkProcessing(false);
                  setBulkProgress(null);
                  fetchStats();
                }, 2000);
              }
            } catch (e) {}
          }
        }
      }
    } catch (err) {
      console.error('Bulk parse error:', err);
      setBulkProcessing(false);
      setBulkProgress(null);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    try {
      const res = await fetch(`${API_BASE}/api/search?q=${encodeURIComponent(searchQuery)}&limit=10`);
      if (res.ok) {
        const data = await res.json();
        setSearchResults(data.results);
      }
    } catch (err) {
      console.error('Search failed:', err);
    }
  };

  const fetchParsedDocs = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/parsed?limit=50`);
      if (res.ok) {
        const data = await res.json();
        setParsedDocs(data.documents);
      }
    } catch (err) {
      console.error('Failed to fetch parsed docs:', err);
    }
  };

  useEffect(() => {
    if (showParsed) fetchParsedDocs();
  }, [showParsed]);

  const handleBulkDelete = async () => {
    if (selectedIds.size === 0) return;
    if (!confirm(`Delete ${selectedIds.size} document(s)? This cannot be undone.`)) return;
    setBulkDeleting(true);
    try {
      await fetch(`${API_BASE}/api/documents/bulk-delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify([...selectedIds]),
      });
      setSelectedIds(new Set());
      await fetchDocuments();
      await fetchStats();
    } catch (err) {
      console.error('Bulk delete failed:', err);
    } finally {
      setBulkDeleting(false);
    }
  };

  const toggleSelect = (id, e) => {
    e.stopPropagation();
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === papers.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(papers.map(p => p.id)));
    }
  };

  const handleDrop = e => {
    e.preventDefault();
    setDragging(false);
    handleFiles(e.dataTransfer?.files);
  };

  if (loading) {
    return <SlideLoader />;
  }

  const tdsCount = papers.filter(p => p.doc_type === 'tds').length;
  const paperCount = papers.filter(p => p.doc_type === 'paper').length;
  const processingCount = papers.filter(p => p.extraction_status === 'processing').length;

  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--pad-md)', height: '100%' }}>
        <div className="flex gap-md">
          <StatCard value={stats.documents} label="Total Documents" color="var(--score-high)" />
          <StatCard value={stats.tds} label="TDS Files" color="#6eb4e6" />
          <StatCard value={stats.papers} label="Papers" color="#c47ee6" />
          <StatCard value={stats.qdrant_parsed} label="Qdrant Parsed" color="var(--accent)" />
        </div>

        <div style={{ display: 'flex', gap: 'var(--pad-sm)', alignItems: 'center' }}>
          <div style={{ flex: 1, display: 'flex', gap: 'var(--pad-sm)' }}>
            <input
              type="text"
              placeholder="Search parsed materials..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && handleSearch()}
              style={{
                flex: 1,
                background: 'var(--glass-bg)',
                border: '1px solid var(--glass-border)',
                borderRadius: 'var(--r-md)',
                padding: '8px 12px',
                color: 'var(--text-primary)',
                fontSize: 13,
              }}
            />
            <button className="btn btn-secondary btn-sm" onClick={handleSearch} disabled={!searchQuery.trim()}>
              <Search size={12} /> Search
            </button>
          </div>
          <button 
            className={`btn btn-sm ${showParsed ? 'btn-primary' : 'btn-secondary'}`}
            onClick={() => setShowParsed(!showParsed)}
          >
            <Database size={12} /> Qdrant ({stats.qdrant_parsed})
          </button>
          <button 
            className="btn btn-secondary btn-sm" 
            onClick={handleBulkParse}
            disabled={bulkProcessing}
          >
            {bulkProcessing ? <Loader size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <FolderOpen size={12} />}
            {bulkProcessing ? 'Processing...' : 'Bulk Parse'}
          </button>
        </div>

        {bulkProcessing && bulkProgress && (
          <div className="glass-panel" style={{ padding: '12px 16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Bulk Processing</span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{bulkProgress.pct.toFixed(1)}%</span>
            </div>
            <div style={{ 
              height: 6, 
              background: 'var(--glass-border)', 
              borderRadius: 3, 
              overflow: 'hidden' 
            }}>
              <div style={{ 
                height: '100%', 
                width: `${bulkProgress.pct}%`, 
                background: 'var(--accent)',
                transition: 'width 0.3s'
              }} />
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 6 }}>{bulkProgress.message}</div>
          </div>
        )}

        {uploadProgress && (
          <div className="glass-panel" style={{ padding: '12px 16px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Uploading Files</span>
              <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{uploadProgress.current}/{uploadProgress.total}</span>
            </div>
            <div style={{ 
              height: 6, 
              background: 'var(--glass-border)', 
              borderRadius: 3, 
              overflow: 'hidden' 
            }}>
              <div style={{ 
                height: '100%', 
                width: `${(uploadProgress.current / uploadProgress.total) * 100}%`, 
                background: 'var(--score-high)',
                transition: 'width 0.3s'
              }} />
            </div>
          </div>
        )}

        {queuedJobs.length > 0 && (
          <CyberExtractionBanner jobs={queuedJobs} />
        )}

        {searchResults && (
          <div className="glass-panel" style={{ padding: '12px' }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: 'var(--text-secondary)' }}>
              Search Results ({searchResults.length})
            </div>
            {searchResults.map((r, i) => (
              <div key={i} style={{ 
                padding: '8px 12px', 
                borderTop: i > 0 ? '1px solid var(--glass-border)' : 'none',
                cursor: 'pointer'
              }}>
                <div style={{ fontWeight: 500, fontSize: 13, color: 'var(--text-primary)' }}>{r.filename}</div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4 }}>{r.content?.substring(0, 150)}...</div>
                <div style={{ fontSize: 10, color: 'var(--accent)', marginTop: 4 }}>Score: {(r.score || 0).toFixed(3)}</div>
              </div>
            ))}
          </div>
        )}

        <div
          className="glass-panel"
          style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}
          onDragOver={e => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
        >
          <div className="panel-header">
            <FileText size={14} style={{ color: 'var(--accent)' }} />
            <span className="panel-title">{showParsed ? 'Qdrant Stored Materials' : 'Uploaded Documents'}</span>
            {selectedIds.size > 0 && !showParsed && (
              <button
                className="btn btn-sm"
                onClick={handleBulkDelete}
                disabled={bulkDeleting}
                style={{
                  background: 'rgba(146,58,58,0.15)',
                  border: '1px solid rgba(146,58,58,0.4)',
                  color: '#e07070',
                  display: 'flex', alignItems: 'center', gap: 5,
                  animation: 'fadeIn 0.15s ease',
                }}
              >
                {bulkDeleting
                  ? <Loader size={12} style={{ animation: 'spin 1s linear infinite' }} />
                  : <Trash2 size={12} />}
                Delete {selectedIds.size}
              </button>
            )}
            <button
              id="btn-upload-pdf"
              className="btn btn-primary btn-sm ml-auto"
              onClick={() => inputRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? <Loader size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Upload size={12} />}
              {uploading ? 'Processing...' : 'Upload'}
            </button>
            <input 
              ref={inputRef} 
              type="file" 
              accept=".pdf" 
              multiple 
              style={{ display: 'none' }} 
              onChange={e => handleFiles(e.target.files)}
            />
            <button
              className="btn btn-secondary btn-sm"
              onClick={() => folderInputRef.current?.click()}
              disabled={bulkProcessing}
              title="Upload a folder containing PDFs"
            >
              <FolderOpen size={12} /> Folder
            </button>
            <input
              ref={folderInputRef}
              type="file"
              webkitdirectory
              multiple
              accept=".pdf"
              style={{ display: 'none' }}
              onChange={e => {
                if (e.target.files?.length > 0) {
                  handleFiles(e.target.files);
                }
              }}
            />
          </div>

          {dragging && (
            <div style={{
              position: 'absolute', inset: 0, zIndex: 20,
              background: 'rgba(58,146,104,0.15)', border: '2px dashed var(--accent)',
              borderRadius: 'var(--r-lg)', display: 'flex', alignItems: 'center', justifyContent: 'center',
              backdropFilter: 'blur(4px)',
            }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: 36, marginBottom: 8 }}>PDF</div>
                <div style={{ fontSize: 14, color: 'var(--text-accent)', fontWeight: 600 }}>Drop PDFs to process</div>
              </div>
            </div>
          )}

          <div className="panel-body scroll-area" style={{ height: 'calc(100% - 49px)' }}>
            {showParsed ? (
              parsedDocs.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                  <Database size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
                  <div style={{ fontSize: 16, marginBottom: 8 }}>No parsed materials in Qdrant</div>
                  <div style={{ fontSize: 12 }}>Use Bulk Parse to add materials from a folder</div>
                </div>
              ) : (
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <thead>
                    <tr style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.6px' }}>
                      <th style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 600 }}>Filename</th>
                      <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Type</th>
                      <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Material</th>
                      <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Processed</th>
                      <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {parsedDocs.map((p) => {
                      const payload = p.payload || {};
                      return (
                        <tr
                          key={p.id}
                          style={{
                            borderTop: '1px solid var(--glass-border)',
                            fontSize: 12,
                            transition: 'background 0.15s',
                            cursor: 'pointer',
                          }}
                          onClick={() => setSelectedDoc({
                            id: p.id,
                            filename: payload.filename || 'Unknown',
                            doc_type: payload.doc_type || 'paper',
                            isQdrant: true,
                            properties: payload.properties || [],
                            processing_conditions: payload.processing_conditions || [],
                            material_name: payload.material_name || payload.filename || '',
                            extraction_confidence: payload.extraction_confidence || 0,
                          })}
                          onMouseEnter={e => e.currentTarget.style.background = 'var(--glass-hover)'}
                          onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                        >
                          <td style={{ padding: '10px 8px', maxWidth: 280 }}>
                            <div style={{ color: 'var(--text-primary)', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                              {payload.filename || 'Unknown'}
                            </div>
                          </td>
                          <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                            <span className={`tag ${payload.doc_type === 'tds' ? 'tag-tds' : 'tag-paper'}`}>
                              {payload.doc_type || 'unknown'}
                            </span>
                          </td>
                          <td style={{ padding: '10px 8px', textAlign: 'center', color: 'var(--text-secondary)' }}>
                            {payload.material_name || payload.filename || '-'}
                          </td>
                          <td style={{ padding: '10px 8px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 11 }}>
                            {payload.processed_at ? new Date(payload.processed_at).toLocaleDateString() : '-'}
                          </td>
                          <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                            <button 
                              className="btn btn-sm" 
                              style={{ padding: '4px 8px', fontSize: 10 }}
                              onClick={async () => {
                                if (confirm('Delete from Qdrant?')) {
                                  await fetch(`${API_BASE}/api/parsed/${p.id}`, { method: 'DELETE' });
                                  fetchParsedDocs();
                                  fetchStats();
                                }
                              }}
                            >
                              Delete
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )
            ) : papers.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 40, color: 'var(--text-muted)' }}>
                <FileText size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
                <div style={{ fontSize: 16, marginBottom: 8 }}>No documents yet</div>
                <div style={{ fontSize: 12 }}>Upload TDS or research papers to get started</div>
              </div>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.6px' }}>
                    <th style={{ width: 32, padding: '6px 8px' }}>
                      <input
                        type="checkbox"
                        checked={papers.length > 0 && selectedIds.size === papers.length}
                        onChange={toggleSelectAll}
                        style={{ accentColor: 'var(--accent)', cursor: 'pointer' }}
                      />
                    </th>
                    <th style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 600 }}>Document</th>
                    <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Type</th>
                    <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Status</th>
                    <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Confidence</th>
                    <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {papers.map((p) => {
                    const isChecked = selectedIds.has(p.id);
                    return (
                      <tr
                        key={p.id}
                        id={`paper-row-${p.id}`}
                        style={{
                          borderTop: '1px solid var(--glass-border)',
                          fontSize: 12,
                          transition: 'background 0.15s',
                          cursor: 'pointer',
                          background: isChecked ? 'rgba(58,146,104,0.08)' : 'transparent',
                        }}
                        onClick={() => setSelectedDoc(p)}
                        onMouseEnter={e => { if (!isChecked) e.currentTarget.style.background = 'var(--glass-hover)'; }}
                        onMouseLeave={e => { e.currentTarget.style.background = isChecked ? 'rgba(58,146,104,0.08)' : 'transparent'; }}
                      >
                        <td style={{ padding: '10px 8px', width: 32 }} onClick={e => toggleSelect(p.id, e)}>
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={() => {}}
                            style={{ accentColor: 'var(--accent)', cursor: 'pointer' }}
                          />
                        </td>
                        <td style={{ padding: '10px 8px', maxWidth: 260 }}>
                          <div style={{ color: 'var(--text-primary)', fontWeight: 500, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                            {p.filename}
                          </div>
                        </td>
                        <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                          <span className={`tag ${p.doc_type === 'tds' ? 'tag-tds' : 'tag-paper'}`}>
                            {p.doc_type === 'tds' ? 'TDS' : 'Paper'}
                          </span>
                        </td>
                        <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                          <div className="flex items-center gap-sm" style={{ justifyContent: 'center' }}>
                            {STATUS_ICON[p.status] || STATUS_ICON.completed}
                            <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>
                              {p.status || 'completed'}
                            </span>
                          </div>
                        </td>
                        <td style={{ padding: '10px 8px', textAlign: 'center' }}>
                          {p.extraction_confidence ? (
                            <span style={{
                              fontFamily: 'var(--font-mono)',
                              fontSize: 11,
                              color: p.extraction_confidence >= 0.7 ? 'var(--score-high)' :
                                     p.extraction_confidence >= 0.5 ? '#b8943a' : 'var(--score-low)'
                            }}>
                              {Math.round(p.extraction_confidence * 100)}%
                            </span>
                          ) : '-'}
                        </td>
                        <td style={{ padding: '10px 8px', textAlign: 'center', color: 'var(--text-muted)', fontSize: 11 }}>
                          {p.created_at ? new Date(p.created_at).toLocaleDateString() : '-'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {selectedDoc && (
        <DocumentDetails 
          document={selectedDoc} 
          onClose={() => setSelectedDoc(null)} 
        />
      )}
    </>
  );
}

// ── Chaos loader (initial page load) ─────────────────────────────────────────

function SlideLoader() {
  return (
    <div className="slide-loader">
      <div className="slide-loader__bar" />
      <div className="slide-loader__label">Loading</div>
    </div>
  );
}

// ── Cyber extraction animation ────────────────────────────────────────────────

const TICKER_TOKENS = [
  { text: 'INITIALISING NEURAL EXTRACTOR', cls: 'hi' },
  { text: '▸', cls: 'mid' },
  { text: 'PARSING PDF STRUCTURE', cls: 'mid' },
  { text: '▸', cls: 'mid' },
  { text: 'TOKENISING CONTENT', cls: 'mid' },
  { text: '▸', cls: 'mid' },
  { text: 'LLM SCHEMA EXTRACTION', cls: 'hi' },
  { text: '▸', cls: 'mid' },
  { text: 'IDENTIFYING MATERIAL NAME', cls: 'mid' },
  { text: '▸', cls: 'mid' },
  { text: 'EXTRACTING TENSILE DATA', cls: 'mid' },
  { text: '▸', cls: 'mid' },
  { text: 'VECTORISING CHUNKS', cls: 'hi' },
  { text: '▸', cls: 'mid' },
  { text: 'EMBEDDING 768-DIM SPACE', cls: 'mid' },
  { text: '▸', cls: 'mid' },
  { text: 'INDEXING MATERIAL PROPERTIES', cls: 'mid' },
  { text: '▸', cls: 'mid' },
  { text: 'BUILDING KNOWLEDGE GRAPH EDGES', cls: 'hi' },
  { text: '▸', cls: 'mid' },
  { text: 'PERSISTING TO QDRANT', cls: 'mid' },
  { text: '▸', cls: 'mid' },
  { text: 'VALIDATING EXTRACTION CONFIDENCE', cls: 'mid' },
  { text: '▸', cls: 'mid' },
];

const STEP_LABELS = {
  'Extracting text':      'PARSING PDF BYTES',
  'Running LLM extraction': 'NEURAL EXTRACTION · LLM INFERENCE',
  'Storing in Qdrant':    'EMBEDDING & VECTORISING CHUNKS',
  'Completed':            'EXTRACTION COMPLETE',
  'queued':               'QUEUED — AWAITING WORKER',
  'pending':              'INITIALISING',
};

function CyberExtractionBanner({ jobs }) {
  const running = jobs.find(j => j.status === 'running');
  const activeJob = running || jobs[0];
  const queuedCount = jobs.filter(j => j.status === 'queued').length;

  const rawStep = activeJob?.current_step || activeJob?.status || '';
  const stepLabel = STEP_LABELS[rawStep] || rawStep.toUpperCase() || 'PROCESSING';

  // Double the tokens so the infinite loop is seamless
  const allTokens = [...TICKER_TOKENS, ...TICKER_TOKENS];

  return (
    <div className="cyber-extraction" style={{ padding: '12px 16px' }}>
      {/* Sweeping scanline */}
      <div className="scanline" />

      {/* Header row */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <span className="cyber-hex">⬡</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 3 }}>
            <Cpu size={11} style={{ color: 'var(--accent)', flexShrink: 0 }} />
            <span style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              color: 'var(--text-muted)',
              letterSpacing: '0.1em',
              textTransform: 'uppercase',
            }}>
              AI EXTRACTION ENGINE
            </span>
            <span style={{
              marginLeft: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              color: 'var(--text-muted)',
            }}>
              {jobs.length} JOB{jobs.length !== 1 ? 'S' : ''}
              {queuedCount > 0 && ` · ${queuedCount} QUEUED`}
            </span>
          </div>
          {/* Active filename */}
          <div style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 12,
            color: 'var(--text-primary)',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            maxWidth: '100%',
          }}>
            {activeJob?.filename || '—'}
          </div>
        </div>
        {/* Priority badge */}
        {activeJob?.priority && (
          <span style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9,
            padding: '3px 7px',
            borderRadius: 4,
            letterSpacing: '0.08em',
            background: activeJob.priority === 'HIGH' ? 'rgba(77,184,130,0.18)'
                      : activeJob.priority === 'MEDIUM' ? 'rgba(184,148,58,0.18)'
                      : 'rgba(80,104,89,0.25)',
            color: activeJob.priority === 'HIGH' ? 'var(--score-high)'
                 : activeJob.priority === 'MEDIUM' ? 'var(--score-mid)'
                 : 'var(--text-muted)',
            border: `1px solid ${activeJob.priority === 'HIGH' ? 'rgba(77,184,130,0.35)'
                              : activeJob.priority === 'MEDIUM' ? 'rgba(184,148,58,0.35)'
                              : 'var(--glass-border)'}`,
          }}>
            {activeJob.priority}
          </span>
        )}
      </div>

      {/* Current step label */}
      <div className="cyber-step-label" key={stepLabel} style={{ marginBottom: 8 }}>
        <span>▶</span>{' '}{stepLabel}<span className="cursor">_</span>
      </div>

      {/* Sub progress bar */}
      <div className="cyber-subbar" style={{ marginBottom: 10 }}>
        <div className="cyber-subbar-fill" />
      </div>

      {/* Scrolling ticker */}
      <div className="cyber-ticker-wrap" style={{ paddingBottom: 2 }}>
        <div className="cyber-ticker-inner">
          {allTokens.map((t, i) => (
            <span key={i} className={`cyber-token ${t.cls}`}>
              {t.text}
              {i < allTokens.length - 1 && <span className="sep" />}
            </span>
          ))}
        </div>
      </div>

      {/* Queue list (compact, only if multiple jobs) */}
      {jobs.length > 1 && (
        <div style={{ marginTop: 10, borderTop: '1px solid var(--glass-border)', paddingTop: 8 }}>
          {jobs.slice(0, 5).map((job, i) => (
            <div key={job.job_id} style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '3px 0', fontSize: 11,
              borderBottom: i < Math.min(jobs.length, 5) - 1 ? '1px solid rgba(52,130,90,0.08)' : 'none',
            }}>
              {job.status === 'running'
                ? <Loader size={11} style={{ color: 'var(--accent-bright)', animation: 'spin 1s linear infinite', flexShrink: 0 }} />
                : <Clock size={11} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />}
              <span style={{
                flex: 1, color: job.status === 'running' ? 'var(--text-primary)' : 'var(--text-muted)',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                fontFamily: 'var(--font-mono)', fontSize: 11,
              }}>
                {job.filename}
              </span>
              <span style={{
                fontFamily: 'var(--font-mono)', fontSize: 9,
                color: job.status === 'running' ? 'var(--accent-bright)' : 'var(--text-muted)',
                letterSpacing: '0.06em',
              }}>
                {(STEP_LABELS[job.current_step] || job.current_step || job.status).toUpperCase().slice(0, 20)}
              </span>
            </div>
          ))}
          {jobs.length > 5 && (
            <div style={{ fontSize: 10, color: 'var(--text-muted)', paddingTop: 4, fontFamily: 'var(--font-mono)' }}>
              +{jobs.length - 5} MORE IN QUEUE
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function StatCard({ value, label, color }) {
  return (
    <div className="glass-panel anim-fade-in" style={{ flex: 1, padding: '14px 18px' }}>
      <div className="stat-number" style={{ color }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 4, textTransform: 'uppercase', letterSpacing: '0.7px' }}>{label}</div>
    </div>
  );
}
