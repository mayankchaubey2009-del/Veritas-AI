"use client";

import React from "react";
import {
  Activity,
  BrainCircuit,
  FileSearch,
  FileSpreadsheet,
  FolderKanban,
  GitCompareArrows,
  History,
  LayoutDashboard,
  ScanEye,
  Settings,
  ShieldCheck,
  X,
} from "lucide-react";
import { NavigationSectionId } from "@/types/veritas";

export interface NavItemConfig {
  id: NavigationSectionId;
  label: string;
  shortTag?: string;
  phaseBadge?: string;
  icon: React.ComponentType<{ className?: string }>;
}

export const SIDEBAR_NAV_ITEMS: NavItemConfig[] = [
  {
    id: "command-centre",
    label: "Command Centre",
    shortTag: "LIVE",
    icon: LayoutDashboard,
  },
  {
    id: "investigations",
    label: "Investigations",
    icon: FolderKanban,
  },
  {
    id: "document-intelligence",
    label: "Document Intelligence",
    shortTag: "LIVE",
    icon: FileSearch,
  },
  {
    id: "visual-forensics",
    label: "Visual Forensics",
    shortTag: "LIVE",
    icon: ScanEye,
  },
  {
    id: "contextual-intelligence",
    label: "Contextual Intelligence",
    shortTag: "LIVE",
    icon: BrainCircuit,
  },
  {
    id: "cross-document-analysis",
    label: "Cross-Document Analysis",
    shortTag: "LIVE",
    icon: GitCompareArrows,
  },
  {
    id: "evidence-explorer",
    label: "Evidence Explorer",
    shortTag: "LIVE",
    icon: ShieldCheck,
  },
  {
    id: "investigation-dossiers",
    label: "Investigation Dossiers",
    shortTag: "LIVE",
    icon: FileSpreadsheet,
  },
  {
    id: "audit-history",
    label: "Audit History",
    icon: History,
  },
  {
    id: "settings",
    label: "Settings",
    icon: Settings,
  },
];

interface SidebarProps {
  activeSection: NavigationSectionId;
  onSelectSection: (section: NavigationSectionId) => void;
  totalInvestigations: number;
  backendHealthy: boolean | null;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}

export default function Sidebar({
  activeSection,
  onSelectSection,
  totalInvestigations,
  backendHealthy,
  mobileOpen,
  onCloseMobile,
}: SidebarProps) {
  return (
    <>
      {/* Mobile Backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/70 backdrop-blur-sm lg:hidden"
          onClick={onCloseMobile}
        />
      )}

      <aside
        className={`fixed inset-y-0 left-0 z-50 flex w-72 flex-col border-r border-slate-800/80 bg-[#070B16]/95 backdrop-blur-xl transition-transform duration-300 lg:static lg:translate-x-0 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {/* Brand Identity Header */}
        <div className="flex h-20 items-center justify-between border-b border-slate-800/80 px-6">
          <div className="flex items-center gap-3.5">
            <div className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-cyan-500/40 bg-gradient-to-br from-blue-600/25 via-cyan-500/15 to-transparent shadow-glow">
              <ShieldCheck className="h-5 w-5 text-cyan-400" />
              <span className="absolute -right-0.5 -top-0.5 flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-cyan-400 opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-cyan-400" />
              </span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base font-bold tracking-wider text-white">
                  VERITAS
                </span>
                <span className="rounded border border-cyan-500/30 bg-cyan-500/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold tracking-widest text-cyan-300">
                  AI
                </span>
              </div>
              <p className="font-mono text-[10px] uppercase tracking-widest text-slate-400">
                Forensic Intelligence
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onCloseMobile}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-800/60 hover:text-white lg:hidden"
            aria-label="Close navigation menu"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Navigation Section */}
        <div className="flex-1 overflow-y-auto px-3 py-5">
          <div className="mb-2 px-3 font-mono text-[10px] font-semibold uppercase tracking-widest text-slate-500">
            Forensic Operations
          </div>

          <nav className="space-y-1" aria-label="Main Sidebar Navigation">
            {SIDEBAR_NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const isActive = activeSection === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    onSelectSection(item.id);
                    onCloseMobile();
                  }}
                  className={`group relative flex w-full items-center justify-between rounded-xl px-3.5 py-2.5 text-left text-sm font-medium transition-all duration-200 ${
                    isActive
                      ? " border border-cyan-500/30 bg-gradient-to-r from-blue-600/20 via-cyan-500/10 to-transparent text-white shadow-[0_0_20px_-6px_rgba(6,182,212,0.35)]"
                      : "border border-transparent text-slate-400 hover:border-slate-800 hover:bg-slate-900/70 hover:text-slate-200"
                  }`}
                >
                  {isActive && (
                    <span className="absolute left-0 top-2 bottom-2 w-1 rounded-r-full bg-gradient-to-b from-cyan-400 to-blue-500" />
                  )}
                  <span className="flex items-center gap-3 truncate">
                    <Icon
                      className={`h-4 w-4 shrink-0 transition-colors ${
                        isActive
                          ? "text-cyan-400"
                          : "text-slate-500 group-hover:text-cyan-400/80"
                      }`}
                    />
                    <span className="truncate">{item.label}</span>
                  </span>

                  {item.id === "investigations" && (
                    <span
                      className={`ml-2 rounded-md px-1.5 py-0.5 font-mono text-[11px] ${
                        isActive
                          ? "bg-cyan-500/20 text-cyan-300"
                          : "bg-slate-800/90 text-slate-400"
                      }`}
                    >
                      {totalInvestigations}
                    </span>
                  )}

                  {item.shortTag && (
                    <span className="ml-2 rounded border border-emerald-500/30 bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-300">
                      {item.shortTag}
                    </span>
                  )}

                  {item.phaseBadge && (
                    <span className="ml-2 rounded border border-slate-700/80 bg-slate-900/90 px-1.5 py-0.5 font-mono text-[10px] text-slate-400">
                      {item.phaseBadge}
                    </span>
                  )}
                </button>
              );
            })}
          </nav>
        </div>

        {/* Live Telemetry Footer */}
        <div className="border-t border-slate-800/80 bg-[#050811]/90 p-4">
          <div className="rounded-xl border border-slate-800/90 bg-slate-900/50 p-3.5">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-wider text-slate-300">
                <Activity className="h-3.5 w-3.5 text-cyan-400" />
                Core Telemetry
              </span>
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 font-mono text-[10px] font-semibold ${
                  backendHealthy === null
                    ? "bg-slate-800 text-slate-400"
                    : backendHealthy
                    ? "border border-emerald-500/30 bg-emerald-500/10 text-emerald-300"
                    : "border border-rose-500/30 bg-rose-500/10 text-rose-300"
                }`}
              >
                <span
                  className={`h-1.5 w-1.5 rounded-full ${
                    backendHealthy === null
                      ? "bg-slate-400"
                      : backendHealthy
                      ? "bg-emerald-400"
                      : "bg-rose-400"
                  }`}
                />
                {backendHealthy === null
                  ? "SYNCING"
                  : backendHealthy
                  ? "ONLINE"
                  : "OFFLINE"}
              </span>
            </div>
            <div className="mt-2.5 flex items-center justify-between font-mono text-[11px] text-slate-400">
              <span>Architecture</span>
              <span className="text-cyan-300">Phase 5 Dossiers</span>
            </div>
            <div className="mt-1 flex items-center justify-between font-mono text-[11px] text-slate-400">
              <span>Persistence</span>
              <span className="text-slate-300">SQLite WAL</span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
