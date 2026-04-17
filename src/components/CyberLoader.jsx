import { useState, useEffect } from 'react';

const CHARS = '01ABCDEFHIJKLMNOPQRSTUVWXYZ$%&#@*+=';

export default function CyberLoader({ size = 20, label = "INITIALIZING", style = {} }) {
  const [text, setText] = useState('');
  
  useEffect(() => {
    const interval = setInterval(() => {
      let result = '';
      for (let i = 0; i < 6; i++) {
        result += CHARS.charAt(Math.floor(Math.random() * CHARS.length));
      }
      setText(result);
    }, 80);
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ 
      display: 'inline-flex', 
      alignItems: 'center', 
      gap: 8, 
      fontFamily: 'var(--font-mono)',
      color: 'var(--accent)',
      fontSize: size * 0.6,
      letterSpacing: '1px',
      ...style 
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: size,
        height: size,
        border: '1px solid var(--accent)',
        borderRadius: 2,
        position: 'relative',
        overflow: 'hidden',
        background: 'rgba(58, 146, 104, 0.1)'
      }}>
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '100%',
          height: '2px',
          background: 'var(--accent)',
          animation: 'scanline 1.5s ease-in-out infinite',
          boxShadow: '0 0 10px var(--accent)'
        }} />
        <span style={{ fontSize: size * 0.5, fontWeight: 900 }}>{text[0]}</span>
      </div>
      {label && <span style={{ textTransform: 'uppercase', opacity: 0.8, fontWeight: 600 }}>{label}...</span>}
      <span style={{ color: 'var(--text-muted)', fontSize: size * 0.5, width: 40 }}>[{text}]</span>

      <style>{`
        @keyframes scanline {
          0% { transform: translateY(-5px); }
          100% { transform: translateY(${size + 5}px); }
        }
      `}</style>
    </div>
  );
}
