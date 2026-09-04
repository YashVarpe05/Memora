import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

import App from './App.tsx';
import './index.css';
import { installServiceWorker } from './platform/serviceWorker';

// Browser: register it. Native shell: actively remove any worker already installed,
// or a new APK keeps rendering the previous build's cache.
installServiceWorker();

const root = document.getElementById('root');
if (!root) throw new Error('#root not found');

createRoot(root).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
