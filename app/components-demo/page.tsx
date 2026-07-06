// app/components-demo/page.tsx
'use client';

import LiveCaptionDisplay from '@/components/deafference/LiveCaptionDisplay';
import SignLanguageStateMachine from '@/components/deafference/SignLanguageStateMachine';

export default function ComponentsDemo() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4rem', padding: '2rem' }}>
      <section>
        <h1>LiveCaptionDisplay Demo</h1>
        <p>
          This component simulates real-time ASL recognition streaming with mock words displayed one at a time.
        </p>
        <LiveCaptionDisplay />
      </section>

      <section style={{ marginTop: '4rem' }}>
        <h1>SignLanguageStateMachine Demo</h1>
        <p>
          This component demonstrates the complete state machine workflow with a debug control panel at the bottom.
          Click the buttons in the debug panel to test each state.
        </p>
        <SignLanguageStateMachine />
      </section>
    </div>
  );
}
