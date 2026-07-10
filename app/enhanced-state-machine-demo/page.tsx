'use client';

import EnhancedSignLanguageStateMachine from '@/components/deafference/EnhancedSignLanguageStateMachine';

export default function EnhancedStateMachineDemoPage() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-8">
      <div className="max-w-7xl mx-auto">
        <div className="mb-12">
          <h1 className="text-5xl font-bold text-white mb-4">
            Enhanced State Machine Demo
          </h1>
          <p className="text-xl text-slate-300 mb-8">
            10-state machine with professional error/fallback screens and inactivity monitoring
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
            <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-6">
              <h2 className="text-lg font-semibold text-white mb-3">States Included:</h2>
              <ul className="space-y-2 text-slate-300 text-sm">
                <li>✓ permission_needed - Camera permission request</li>
                <li>✓ loading_model - ML model initialization</li>
                <li>✓ listening - Active sign recognition</li>
                <li>✓ sign_recognized - Successfully recognized sign</li>
                <li>✓ speaking - Text-to-speech audio</li>
                <li>✓ error - Sign discard error with auto-recovery</li>
                <li>🆕 camera_denied - Permission denied fallback</li>
                <li>🆕 browser_unsupported - API compatibility fallback</li>
                <li>🆕 no_signs_detected - Inactivity timeout overlay</li>
              </ul>
            </div>

            <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-6">
              <h2 className="text-lg font-semibold text-white mb-3">Features:</h2>
              <ul className="space-y-2 text-slate-300 text-sm">
                <li>✓ Debug panel with buttons for all 10 states</li>
                <li>✓ Current state display with highlighting</li>
                <li>✓ Mock event generator integration</li>
                <li>✓ Inactivity timeout monitoring</li>
                <li>✓ Auto-recovery from error states</li>
                <li>✓ State change callbacks</li>
                <li>✓ Smooth animations & transitions</li>
                <li>✓ Production-grade styling</li>
              </ul>
            </div>
          </div>

          <div className="bg-blue-900/20 border border-blue-700/50 rounded-lg p-6 mb-8">
            <h3 className="text-white font-semibold mb-2">💡 How to Test:</h3>
            <p className="text-slate-300 text-sm">
              Use the debug panel below to transition between states. Test the camera denied screen, 
              browser unsupported detection, and inactivity timeout (default 10 seconds). 
              The mock event generator will simulate sign recognition events while in listening state.
            </p>
          </div>
        </div>

        <div className="bg-slate-800/30 border border-slate-700 rounded-lg p-8">
          <EnhancedSignLanguageStateMachine
            inactivityTimeoutSeconds={10}
            onStateChange={(state) => {
              console.log('State changed to:', state);
            }}
          />
        </div>
      </div>
    </main>
  );
}
