import { Route, Routes } from 'react-router-dom'
import { NavBar } from './components/layout/NavBar'
import { Footer } from './components/layout/Footer'
import Dashboard from './pages/Dashboard'
import Methodology from './pages/Methodology'
import OddsBoard from './pages/OddsBoard'

export default function App() {
  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/odds" element={<OddsBoard />} />
          <Route path="/methodology" element={<Methodology />} />
        </Routes>
      </main>
      <Footer />
    </div>
  )
}
