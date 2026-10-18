import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { StartSessionPage } from './pages/StartSessionPage'
import { SessionDashboardPage } from './pages/SessionDashboardPage'
import { VerifyStartPage } from './pages/VerifyStartPage'
import { VerifyResultPage } from './pages/VerifyResultPage'
import { BatchStartPage } from './pages/BatchStartPage'
import { BatchResultPage } from './pages/BatchResultPage'
import { EditorPage } from './pages/EditorPage'
import { LoginPage } from './pages/LoginPage'
import { ObservabilityPage } from './pages/ObservabilityPage'
import { RequireAuth } from './components/RequireAuth'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<RequireAuth><StartSessionPage /></RequireAuth>} />
        <Route path="/sessions/:sessionId" element={<RequireAuth><SessionDashboardPage /></RequireAuth>} />
        <Route path="/verify" element={<RequireAuth><VerifyStartPage /></RequireAuth>} />
        <Route path="/verify/batch" element={<RequireAuth><BatchStartPage /></RequireAuth>} />
        <Route path="/verify/batch/:batchId" element={<RequireAuth><BatchResultPage /></RequireAuth>} />
        <Route path="/verify/:checkId" element={<RequireAuth><VerifyResultPage /></RequireAuth>} />
        <Route path="/verify/:checkId/editor" element={<RequireAuth><EditorPage /></RequireAuth>} />
        <Route path="/observability" element={<RequireAuth><ObservabilityPage /></RequireAuth>} />
      </Routes>
    </BrowserRouter>
  )
}

export default App
