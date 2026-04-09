import { Routes, Route } from "react-router-dom";
import { Layout } from "./components/Layout";
import { ErrorBoundary } from "./components/ErrorBoundary";
import Overview from "./pages/Overview";
import Alerts from "./pages/Alerts";
import Explorer from "./pages/Explorer";
import SettingsPage from "./pages/Settings";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<ErrorBoundary><Overview /></ErrorBoundary>} />
        <Route path="alerts" element={<ErrorBoundary><Alerts /></ErrorBoundary>} />
        <Route path="explorer" element={<ErrorBoundary><Explorer /></ErrorBoundary>} />
        <Route path="settings" element={<ErrorBoundary><SettingsPage /></ErrorBoundary>} />
      </Route>
    </Routes>
  );
}
