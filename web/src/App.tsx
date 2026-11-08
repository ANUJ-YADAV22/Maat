import { HashRouter, Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ToastProvider } from './hooks'
import Overview from './pages/Overview'
import Playground from './pages/Playground'
import Patches from './pages/Patches'
import Versions from './pages/Versions'
import Trust from './pages/Trust'
import Approvals from './pages/Approvals'
import Scenarios from './pages/Scenarios'
import Knowledge from './pages/Knowledge'
import Evaluation from './pages/Evaluation'
import Audit from './pages/Audit'

export default function App() {
  return (
    <ToastProvider>
      <HashRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Overview />} />
            <Route path="scenarios" element={<Scenarios />} />
            <Route path="playground" element={<Playground />} />
            <Route path="patches" element={<Patches />} />
            <Route path="patches/:id" element={<Patches />} />
            <Route path="approvals" element={<Approvals />} />
            <Route path="versions" element={<Versions />} />
            <Route path="trust" element={<Trust />} />
            <Route path="knowledge" element={<Knowledge />} />
            <Route path="evaluation" element={<Evaluation />} />
            <Route path="audit" element={<Audit />} />
          </Route>
        </Routes>
      </HashRouter>
    </ToastProvider>
  )
}
