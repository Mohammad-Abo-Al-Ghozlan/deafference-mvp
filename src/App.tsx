/**
 * Main Application Entry - React App Wrapper
 * 
 * This file sets up the React application and renders the Sign Language Recognition App
 */

import React from 'react';
import SignLanguageApp from './components/SignLanguageApp';

/**
 * App Component
 * Root component that wraps the entire application
 */
const App: React.FC = () => {
  return (
    <div style={{ width: '100%', height: '100vh' }}>
      <SignLanguageApp />
    </div>
  );
};

export default App;
