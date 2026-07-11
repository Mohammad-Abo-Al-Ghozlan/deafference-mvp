'use client';

interface LoadingSpinnerProps {
  label?: string;
}

export default function LoadingSpinner({ label = 'Initializing TensorFlow.js...' }: LoadingSpinnerProps) {
  return (
    <div style={{ textAlign: 'center' }} role="status" aria-live="polite">
      <div
        style={{
          width: '100%',
          height: '4px',
          background: 'rgba(148, 163, 184, 0.2)',
          borderRadius: '2px',
          overflow: 'hidden',
          marginBottom: '1rem',
        }}
      >
        <div
          style={{
            height: '100%',
            background: '#3b82f6',
            animation: 'slideRight 2s infinite',
            width: '30%',
          }}
        />
      </div>
      <p style={{ color: '#cbd5e1' }}>{label}</p>

      <style>{`
        @keyframes slideRight {
          from { transform: translateX(-100%); }
          to { transform: translateX(100%); }
        }
      `}</style>
    </div>
  );
}
