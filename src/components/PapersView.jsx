import { useState, useEffect, useRef } from 'react';
import { FileText, Upload, CheckCircle, AlertCircle, Loader, Clock, FolderOpen, Search, Database } from 'lucide-react';
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

  const handleDrop = e => { 
    e.preventDefault(); 
    setDragging(false);
    handleFiles(e.dataTransfer?.files);
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)' }}>
        <Loader size={24} style={{ animation: 'spin 1s linear infinite', marginRight: 12 }} />
        Loading documents...
      </div>
    );
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
          <div className="glass-panel" style={{ padding: '12px 16px' }}>
            <div style={{ fontSize: 12, fontWeight: 600, marginBottom: 8, color: 'var(--text-secondary)' }}>
              Processing Queue ({queuedJobs.length} active)
            </div>
            <div style={{ maxHeight: 150, overflow: 'auto' }}>
              {queuedJobs.slice(0, 10).map(job => (
                <div key={job.job_id} style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: 8, 
                  padding: '4px 0',
                  borderBottom: '1px solid var(--glass-border)',
                  fontSize: 11
                }}>
                  {job.status === 'running' ? (
                    <Loader size={12} style={{ animation: 'spin 1s linear infinite', color: 'var(--accent)' }} />
                  ) : job.status === 'queued' ? (
                    <Clock size={12} style={{ color: 'var(--text-muted)' }} />
                  ) : (
                    <CheckCircle size={12} style={{ color: 'var(--score-high)' }} />
                  )}
                  <span style={{ flex: 1, color: 'var(--text-primary)' }}>{job.filename}</span>
                  <span style={{ 
                    padding: '2px 6px', 
                    borderRadius: 4, 
                    fontSize: 9,
                    background: job.priority === 'HIGH' ? 'var(--score-high)' : job.priority === 'MEDIUM' ? 'var(--score-mid)' : 'var(--text-muted)',
                    color: '#fff'
                  }}>
                    {job.priority}
                  </span>
                  <span style={{ color: 'var(--text-muted)', minWidth: 60 }}>{job.current_step || job.status}</span>
                </div>
              ))}
              {queuedJobs.length > 10 && (
                <div style={{ fontSize: 10, color: 'var(--text-muted)', paddingTop: 4 }}>
                  +{queuedJobs.length - 10} more jobs
                </div>
              )}
            </div>
          </div>
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
                    <th style={{ textAlign: 'left', padding: '6px 8px', fontWeight: 600 }}>Document</th>
                    <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Type</th>
                    <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Status</th>
                    <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Confidence</th>
                    <th style={{ textAlign: 'center', padding: '6px 8px', fontWeight: 600 }}>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {papers.map((p) => (
                    <tr
                      key={p.id}
                      id={`paper-row-${p.id}`}
                      style={{
                        borderTop: '1px solid var(--glass-border)',
                        fontSize: 12,
                        transition: 'background 0.15s',
                        cursor: 'pointer',
                      }}
                      onClick={() => setSelectedDoc(p)}
                      onMouseEnter={e => e.currentTarget.style.background = 'var(--glass-hover)'}
                      onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
                    >
                      <td style={{ padding: '10px 8px', maxWidth: 280 }}>
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
                          {STATUS_ICON[p.extraction_status] || STATUS_ICON.completed}
                          <span style={{ color: 'var(--text-secondary)', fontSize: 11 }}>
                            {p.extraction_status || 'completed'}
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
                        {new Date(p.created_at).toLocaleDateString()}
                      </td>
                    </tr>
                  ))}
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

function StatCard({ value, label, color }) {
  return (
    <div className="glass-panel anim-fade-in" style={{ flex: 1, padding: '12px 16px' }}>
      <div style={{ fontFamily: 'var(--font-mono)', fontSize: 22, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.6px' }}>{label}</div>
    </div>
  );
}
