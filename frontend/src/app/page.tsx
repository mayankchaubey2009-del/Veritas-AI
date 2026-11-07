"use client";

import React, { useCallback, useEffect, useState } from "react";
import Sidebar from "@/components/Sidebar";
import TopHeader from "@/components/TopHeader";
import GuidedDemoWalkthrough from "@/components/GuidedDemoWalkthrough";
import NewInvestigationModal from "@/components/NewInvestigationModal";
import CommandCentreView from "@/components/views/CommandCentreView";
import InvestigationsView from "@/components/views/InvestigationsView";
import DocumentIntelligenceView from "@/components/views/DocumentIntelligenceView";
import VisualForensicsView from "@/components/views/VisualForensicsView";
import ContextualIntelligenceView from "@/components/views/ContextualIntelligenceView";
import InvestigationDossiersView from "@/components/views/InvestigationDossiersView";
import AuditHistoryView from "@/components/views/AuditHistoryView";
import SettingsView from "@/components/views/SettingsView";
import { veritasApi } from "@/lib/api";
import {
  AuthenticatedUser,
  CommandCentreSummary,
  DemoPersonaItem,
  HealthStatusResponse,
  Investigation,
  NavigationSectionId,
} from "@/types/veritas";

export default function VeritasPlatformPage() {
  const [activeSection, setActiveSection] =
    useState<NavigationSectionId>("command-centre");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [newModalOpen, setNewModalOpen] = useState(false);

  const [health, setHealth] = useState<HealthStatusResponse | null>(null);
  const [summary, setSummary] = useState<CommandCentreSummary | null>(null);
  const [selectedInvestigation, setSelectedInvestigation] =
    useState<Investigation | null>(null);
  const [forensicsDocId, setForensicsDocId] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Phase 6 Authentication & Guided Demo State
  const [currentUser, setCurrentUser] = useState<AuthenticatedUser | null>(
    null
  );
  const [demoPersonas, setDemoPersonas] = useState<DemoPersonaItem[]>([]);
  const [demoModeEnabled, setDemoModeEnabled] = useState<boolean>(true);
  const [guidedDemoOpen, setGuidedDemoOpen] = useState<boolean>(true);

  const synchronizePlatform = useCallback(async () => {
    setLoading(true);
    setError(null);

    try {
      const authStatus = await veritasApi.getAuthStatus().catch(() => null);
      if (authStatus) {
        setDemoPersonas(authStatus.demo_personas || []);
        setDemoModeEnabled(authStatus.demo_mode_enabled);

        if (authStatus.authenticated && authStatus.user) {
          setCurrentUser(authStatus.user);
        } else if (
          authStatus.demo_mode_enabled &&
          authStatus.demo_personas.length > 0
        ) {
          // Auto-establish lead investigator session on initial demo boot
          const defaultSession = await veritasApi
            .switchDemoPersona("dr.rostova")
            .catch(() => null);
          if (defaultSession?.user) {
            setCurrentUser(defaultSession.user);
          }
        }
      }

      const [healthData, summaryData] = await Promise.all([
        veritasApi.getHealth(),
        veritasApi.getCommandCentreSummary(),
      ]);

      setHealth(healthData);
      setSummary(summaryData);

      setSelectedInvestigation((prev) => {
        const list = summaryData.recent_investigations;
        if (list.length === 0) return null;
        if (prev) {
          const updatedMatch = list.find((item) => item.id === prev.id);
          if (updatedMatch) return updatedMatch;
        }
        return list[0];
      });
    } catch (err: unknown) {
      const msg =
        err instanceof Error
          ? err.message
          : "Unable to synchronize with VERITAS AI FastAPI backend.";
      setError(msg);
      setHealth(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    synchronizePlatform();
  }, [synchronizePlatform]);

  const handleSwitchPersona = useCallback(
    async (username: string) => {
      const session = await veritasApi.switchDemoPersona(username);
      setCurrentUser(session.user);
      await synchronizePlatform();
    },
    [synchronizePlatform]
  );

  const handleLogin = useCallback(
    async (username: string, password: string) => {
      const session = await veritasApi.login({ username, password });
      setCurrentUser(session.user);
      await synchronizePlatform();
    },
    [synchronizePlatform]
  );

  const handleLogout = useCallback(async () => {
    await veritasApi.logout();
    setCurrentUser(null);
  }, []);

  const handleInvestigationCreated = (created: Investigation) => {
    setSelectedInvestigation(created);
    synchronizePlatform();
  };

  const backendHealthy =
    health === null
      ? error
        ? false
        : null
      : health.status === "healthy" && health.database.connected;

  return (
    <div className="flex min-h-screen bg-transparent text-slate-100">
      {/* Left Navigation Sidebar */}
      <Sidebar
        activeSection={activeSection}
        onSelectSection={setActiveSection}
        totalInvestigations={summary?.metrics.total_investigations ?? 0}
        backendHealthy={backendHealthy}
        mobileOpen={mobileMenuOpen}
        onCloseMobile={() => setMobileMenuOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex min-w-0 flex-1 flex-col">
        <TopHeader
          activeSection={activeSection}
          health={health}
          isLoading={loading}
          onRefresh={synchronizePlatform}
          onOpenNewInvestigation={() => setNewModalOpen(true)}
          onOpenMobileMenu={() => setMobileMenuOpen(true)}
          currentUser={currentUser}
          demoPersonas={demoPersonas}
          demoModeEnabled={demoModeEnabled}
          onSwitchPersona={handleSwitchPersona}
          onPasswordLogin={handleLogin}
          onLogout={handleLogout}
          guidedDemoOpen={guidedDemoOpen}
          onToggleGuidedDemo={() => setGuidedDemoOpen((prev) => !prev)}
        />

        <GuidedDemoWalkthrough
          isOpen={guidedDemoOpen}
          onClose={() => setGuidedDemoOpen(false)}
          activeSection={activeSection}
          onNavigateSection={setActiveSection}
          currentUser={currentUser}
          onSwitchPersona={handleSwitchPersona}
        />

        <main className="mx-auto w-full max-w-[1600px] flex-1 p-4 sm:p-6 lg:p-8">
          {activeSection === "command-centre" && (
            <CommandCentreView
              summary={summary}
              health={health}
              loading={loading}
              error={error}
              selectedInvestigation={selectedInvestigation}
              onSelectInvestigation={setSelectedInvestigation}
              onOpenNewInvestigation={() => setNewModalOpen(true)}
              onRefresh={synchronizePlatform}
              onNavigateSection={setActiveSection}
            />
          )}

          {activeSection === "investigations" && (
            <InvestigationsView
              selectedInvestigation={selectedInvestigation}
              onSelectInvestigation={setSelectedInvestigation}
              onOpenNewInvestigation={() => setNewModalOpen(true)}
              onGlobalRefresh={synchronizePlatform}
              onNavigateSection={setActiveSection}
            />
          )}

          {activeSection === "document-intelligence" && (
            <DocumentIntelligenceView
              investigations={summary?.recent_investigations ?? []}
              selectedInvestigation={selectedInvestigation}
              onSelectInvestigation={setSelectedInvestigation}
              onOpenNewInvestigation={() => setNewModalOpen(true)}
              onGlobalRefresh={synchronizePlatform}
              onOpenVisualForensics={(docId) => {
                setForensicsDocId(docId);
                setActiveSection("visual-forensics");
              }}
            />
          )}

          {activeSection === "visual-forensics" && (
            <VisualForensicsView
              investigations={summary?.recent_investigations ?? []}
              selectedInvestigation={selectedInvestigation}
              onSelectInvestigation={setSelectedInvestigation}
              initialDocumentId={forensicsDocId}
              onGlobalRefresh={synchronizePlatform}
            />
          )}

          {(activeSection === "contextual-intelligence" ||
            activeSection === "cross-document-analysis" ||
            activeSection === "evidence-explorer") && (
            <ContextualIntelligenceView
              activeSection={activeSection}
              investigations={summary?.recent_investigations ?? []}
              selectedInvestigation={selectedInvestigation}
              onSelectInvestigation={setSelectedInvestigation}
              onGlobalRefresh={synchronizePlatform}
              onOpenDocumentIntelligence={() => {
                setActiveSection("document-intelligence");
              }}
              onOpenVisualForensics={(docId) => {
                setForensicsDocId(docId);
                setActiveSection("visual-forensics");
              }}
            />
          )}

          {activeSection === "investigation-dossiers" && (
            <InvestigationDossiersView
              investigations={summary?.recent_investigations ?? []}
              selectedInvestigation={selectedInvestigation}
              onSelectInvestigation={setSelectedInvestigation}
              onGlobalRefresh={synchronizePlatform}
              onOpenDocumentIntelligence={() => {
                setActiveSection("document-intelligence");
              }}
              onOpenVisualForensics={(docId) => {
                setForensicsDocId(docId);
                setActiveSection("visual-forensics");
              }}
              onOpenContextualIntelligence={() => {
                setActiveSection("contextual-intelligence");
              }}
              currentUser={currentUser}
              onSwitchPersona={handleSwitchPersona}
            />
          )}

          {activeSection === "audit-history" && <AuditHistoryView />}

          {activeSection === "settings" && (
            <SettingsView
              health={health}
              onRefreshHealth={synchronizePlatform}
              currentUser={currentUser}
            />
          )}
        </main>
      </div>

      {/* Create Investigation Modal */}
      <NewInvestigationModal
        isOpen={newModalOpen}
        onClose={() => setNewModalOpen(false)}
        onCreated={handleInvestigationCreated}
      />
    </div>
  );
}
