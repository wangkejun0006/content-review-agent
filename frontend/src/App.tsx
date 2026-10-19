import { Navigate, Route, Routes } from 'react-router-dom'
import { useAuth } from './auth/AuthContext'
import { AppLayout } from './layout/AppLayout'
import { BriefsPage } from './pages/BriefsPage'
import { AuditPage } from './pages/AuditPage'
import { ClaimsPage } from './pages/ClaimsPage'
import { DashboardPage } from './pages/DashboardPage'
import { FeedbackPage } from './pages/FeedbackPage'
import { LoginPage } from './pages/LoginPage'
import { LLMSettingsPage } from './pages/LLMSettingsPage'
import { MarketingProgramsPage } from './pages/MarketingProgramsPage'
import { OperationsPage } from './pages/OperationsPage'
import { PlatformRulesPage } from './pages/PlatformRulesPage'
import { PublicationsPage } from './pages/PublicationsPage'
import { ProductsPage } from './pages/ProductsPage'
import { RunDetailPage } from './pages/RunDetailPage'
import { RunsPage } from './pages/RunsPage'
import { UsersPage } from './pages/UsersPage'

function ProtectedApp() {
  const { principal } = useAuth()
  if (!principal) return <Navigate to="/login" replace />
  return <AppLayout />
}

function AdminUsersPage() {
  const { principal } = useAuth()
  return principal?.role === 'admin' ? <UsersPage /> : <Navigate to="/" replace />
}

function AdminAuditPage() {
  const { principal } = useAuth()
  return principal?.role === 'admin' ? <AuditPage /> : <Navigate to="/" replace />
}

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<ProtectedApp />}>
        <Route index element={<DashboardPage />} />
        <Route path="products" element={<ProductsPage />} />
        <Route path="claims" element={<ClaimsPage />} />
        <Route path="briefs" element={<BriefsPage />} />
        <Route path="runs" element={<RunsPage />} />
        <Route path="runs/:runId" element={<RunDetailPage />} />
        <Route path="publications" element={<PublicationsPage />} />
        <Route path="feedback" element={<FeedbackPage />} />
        <Route path="platform-rules" element={<PlatformRulesPage />} />
        <Route path="marketing-programs" element={<MarketingProgramsPage />} />
        <Route path="settings/users" element={<AdminUsersPage />} />
        <Route path="settings/llm" element={<LLMSettingsPage />} />
        <Route path="settings/operations" element={<OperationsPage />} />
        <Route path="settings/audit" element={<AdminAuditPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
