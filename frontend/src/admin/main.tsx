import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { App } from './App';
import '../styles/tokens.css';
import './admin.css';

const root = document.getElementById('admin-root');
if (!root) throw new Error('Missing admin root');

// 同源托管在 /admin/ 下
createRoot(root).render(
  <StrictMode>
    <BrowserRouter basename="/admin">
      <App />
    </BrowserRouter>
  </StrictMode>,
);
