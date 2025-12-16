import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import ProviderUpload from './pages/ProviderUpload'
import ValidationStatus from './pages/ValidationStatus'
import Comparison from './pages/Comparison'
import ViewData from './pages/ViewData'

function App() {
  return (
    <BrowserRouter>
      <div className="app-container">
        <Sidebar />
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/upload" element={<ProviderUpload />} />
            <Route path="/validation" element={<ValidationStatus />} />
            <Route path="/view-data" element={<ViewData />} />
            <Route path="/comparison/:id" element={<Comparison />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  )
}

export default App
