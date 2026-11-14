/**
 * Development-server-only browser fixture. Not referenced from index.html,
 * Vite's production build, or any authenticated operator route.
 * All API calls are intercepted by the isolated Chromium smoke runner.
 */
import React, { useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { ApiAccess } from "../App";
import { CatalogCreateSessionRoot } from "../features/search/CatalogCreateSession";
import { InitialCaseCreationDialog } from "../features/search/InitialCaseCreationDialog";
import { CompanySiteCreationDialog } from "../features/search/CompanySiteCreationDialog";
import { PhysicalLineCreationDialog } from "../features/search/PhysicalLineCreationDialog";
import { CaseDirectOpen } from "../pages/CaseDirectOpen";
import "../styles.css";

const siteId = "synthetic-site-uuid";
const canCreate = {action_key: "create_site", readiness_status: "available" as const, label: "Tạo mới", detail: "Synthetic creation only", required_permissions: ["case.edit"]};
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

/**
 * Full browser-only catalog journey. IDs only originate from actual CREATE
 * payloads and subsequent canonical GETs. No app state hardcodes them.
 */
function CatalogJourney() {
  const navigate = useNavigate();
  const [stage, setStage] = useState<"catalog" | "physical" | "initial">("catalog");
  const [persistedSiteId, setPersistedSiteId] = useState<string | null>(null);
  const [showCatalog, setShowCatalog] = useState(true);
  return <main>
    <h1>Company → Site → physical UUID → first Case (synthetic)</h1>
    {stage === "catalog" && <CompanySiteCreationDialog
      openAction={showCatalog ? "create_company" : null}
      ownerIdentity="synthetic-catalog-company-site"
      auth={auth} useStubAuth bearerToken={null}
      companyAction={canCreate} siteAction={canCreate}
      onClose={() => setShowCatalog(false)}
      onSiteVerified={(id) => { setPersistedSiteId(id); setStage("physical"); }}
    />}
    {stage === "physical" && <PhysicalLineCreationDialog
      open siteId={persistedSiteId} action={canCreate}
      auth={auth} useStubAuth bearerToken={null} accessGeneration={1}
      onClose={() => setStage("initial")}
    />}
    {stage === "initial" && <InitialCaseCreationDialog
      open siteId={persistedSiteId}
      auth={auth} useStubAuth bearerToken={null} accessGeneration={1}
      onClose={() => {}} onVerifiedOpen={(id) => navigate(`/cases/${encodeURIComponent(id)}`)}
    />}
  </main>;
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
    <Route path="/catalog-journey-browser-fixture.html" element={<CatalogJourney />} />
    <Route path="/cases/:caseId" element={<CaseDirectOpen access={access} />} />
    <Route path="/search" element={<Destination />} />
  </Routes></CatalogCreateSessionRoot></BrowserRouter>,
);
