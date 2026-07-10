// app/mock-testing-demo/page.tsx
'use client';

import SignLanguageStateMachineWithMock from '@/components/deafference/SignLanguageStateMachineWithMock';

export default function MockTestingDemo() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem', padding: '2rem' }}>
      <section>
        <h1 style={{ marginBottom: '1rem' }}>MockEventGenerator - Testing Demo</h1>
        <p style={{ color: '#999', marginBottom: '2rem' }}>
          This demo showcases the <strong>useMockEventGenerator</strong> hook integrated with the state machine.
          Click "Start Mock Events" to simulate real-time sign language recognition without a live ML model.
        </p>
      </section>

      <SignLanguageStateMachineWithMock
        mockIntervalMs={3500}
        autoStartMock={false}
      />
    </div>
  );
}
