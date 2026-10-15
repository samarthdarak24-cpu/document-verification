import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Documents from "./pages/Documents";
import DocumentDetail from "./pages/DocumentDetail";
import Upload from "./pages/Upload";
import Compare from "./pages/Compare";
import Duplicates from "./pages/Duplicates";
import Templates from "./pages/Templates";
import Reports from "./pages/Reports";
import AlgorithmLab from "./pages/AlgorithmLab";
import UnitPage from "./pages/UnitPage";
import Performance from "./pages/Performance";
import Settings from "./pages/Settings";
import NotFound from "./pages/NotFound";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/documents" element={<Documents />} />
        <Route path="/documents/:id" element={<DocumentDetail />} />
        <Route path="/upload" element={<Upload />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="/duplicates" element={<Duplicates />} />
        <Route path="/templates" element={<Templates />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/lab" element={<AlgorithmLab />} />
        <Route path="/lab/unit-:unit" element={<UnitPage />} />
        <Route path="/performance" element={<Performance />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/dashboard" element={<Navigate to="/" replace />} />
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
