import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import './shell.css'
import App from './App.tsx'
import './appearance.css'
import './layout.css'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
