/**
 * Development-server-only browser fixture. Not referenced from index.html,
 * Vite's production build, or any authenticated operator route.
 * All API calls are intercepted by the isolated Chromium smoke runner.
 */
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { ApiAccess } from "../App";
import { CatalogCreateSessionRoot } from "../features/search/CatalogCreateSession";
import { InitialCaseCreationDialog } from "../features/search/InitialCaseCreationDialog";
import { CaseDirectOpen } from "../pages/CaseDirectOpen";
import "../styles.css";

const siteId = "synthetic-site-uuid";
const auth = { username: "synthetic.operator", role: "admin" as const };
const access: ApiAccess = {
  auth, useStubAuth: true, bearerToken: null, canLoadSecureApi: true, accessGeneration: 1,
};

function InitialCreate() {
  const navigate = useNavigate();
  return <InitialCaseCreationDialog
    open siteId={siteId} auth={auth} useStubAuth bearerToken={null} accessGeneration={1}
    onClose={() => {}} onVerifiedOpen={(id) => navigate(`/cases/${encodeURIComponent(id)}`)}
  />;
}

function Destination() {
  const location = useLocation();
  return <main role="main">
    <h1>Canonical Case workspace routing verified</h1>
    <output aria-label="Canonical workspace destination" data-testid="workspace-destination">
      {location.pathname + location.search}
    </output>
  </main>;
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <BrowserRouter><CatalogCreateSessionRoot><Routes>
    <Route path="/initial-case-browser-fixture.html" element={<InitialCreate />} />
    <Route path="/cases/:caseId" element={<CaseDirectOpen access={access} />} />
    <Route path="/search" element={<Destination />} />
  </Routes></CatalogCreateSessionRoot></BrowserRouter>,
);
