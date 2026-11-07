"use client";

import React, { useState } from "react";
import {
  ChevronDown,
  Compass,
  Database,
  KeyRound,
  LogOut,
  Menu,
  Plus,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  UserCheck,
  Wifi,
} from "lucide-react";
import {
  AuthenticatedUser,
  DemoPersonaItem,
  HealthStatusResponse,
  NavigationSectionId,
} from "@/types/veritas";
import { SIDEBAR_NAV_ITEMS } from "./Sidebar";

interface TopHeaderProps {
  activeSection: NavigationSectionId;
  health: HealthStatusResponse | null;
  isLoading: boolean;
  onRefresh: () => void;
  onOpenNewInvestigation: () => void;
  onOpenMobileMenu: () => void;
  currentUser: AuthenticatedUser | null;
  demoPersonas: DemoPersonaItem[];
  demoModeEnabled: boolean;
  onSwitchPersona: (username: string) => Promise<void>;
  onPasswordLogin: (username: string, password: string) => Promise<void>;
  onLogout: () => Promise<void>;
  guidedDemoOpen: boolean;
  onToggleGuidedDemo: () => void;
}

export default function TopHeader({
  activeSection,
  health,
  isLoading,
  onRefresh,
  onOpenNewInvestigation,
  onOpenMobileMenu,
  currentUser,
  demoPersonas,
  demoModeEnabled,
  onSwitchPersona,
  onPasswordLogin,
  onLogout,
  guidedDemoOpen,
  onToggleGuidedDemo,
}: TopHeaderProps) {
  const [authMenuOpen, setAuthMenuOpen] = useState(false);
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [usernameInput, setUsernameInput] = useState("");
  const [passwordInput, setPasswordInput] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  const activeItem =
    SIDEBAR_NAV_ITEMS.find((item) => item.id === activeSection) ||
    SIDEBAR_NAV_ITEMS[0];

  const isHealthy = health?.status === "healthy" && health?.database?.connected;
  const isViewer = currentUser?.role === "VIEWER";

  const roleBadgeColor = (role?: string) => {
    switch (role) {
      case "ADMIN":
        return "border-purple-500/40 bg-purple-500/15 text-purple-200";
      case "REVIEWER":
        return "border-emerald-500/40 bg-emerald-500/15 text-emerald-200";
      case "VIEWER":
        return "border-amber-500/40 bg-amber-500/15 text-amber-200";
      default:
        return "border-cyan-500/40 bg-cyan-500/15 text-cyan-200";
    }
  };

  const handlePersonaSelect = async (username: string) => {
    setAuthBusy(true);
    setAuthError(null);
    try {
      await onSwitchPersona(username);
      setAuthMenuOpen(false);
    } catch (err: unknown) {
      setAuthError(
        err instanceof Error ? err.message : "Failed to switch persona."
      );
    } finally {
      setAuthBusy(false);
    }
  };

  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!usernameInput.trim() || !passwordInput) return;
    setAuthBusy(true);
    setAuthError(null);
    try {
      await onPasswordLogin(usernameInput.trim(), passwordInput);
      setPasswordInput("");
      setShowPasswordForm(false);
      setAuthMenuOpen(false);
    } catch (err: unknown) {
      setAuthError(
        err instanceof Error ? err.message : "Authentication failed."
      );
    } finally {
      setAuthBusy(false);
    }
  };

  return (
    <header className="sticky top-0 z-30 flex h-20 items-center justify-between border-b border-slate-800/80 bg-[#070B16]/85 px-6 backdrop-blur-xl">
      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={onOpenMobileMenu}
          className="rounded-lg border border-slate-800 bg-slate-900/70 p-2 text-slate-300 hover:border-cyan-500/40 hover:text-white lg:hidden"
          aria-label="Open navigation menu"
        >
          <Menu className="h-5 w-5" />
        </button>

        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-lg font-semibold tracking-tight text-white sm:text-xl">
              {activeItem.label}
            </h1>
            <span className="hidden rounded border border-blue-500/30 bg-blue-500/10 px-2 py-0.5 font-mono text-[10px] font-medium uppercase tracking-widest text-blue-300 sm:inline-block">
              VERITAS CORE v2.0 · PHASE 6
            </span>
          </div>
          <p className="text-xs text-slate-400">
            Enterprise Document Forensics &amp; Contextual Intelligence Platform
          </p>
        </div>
      </div>

      {/* Right Telemetry, Guided Demo & Authenticated Session Controls */}
      <div className="flex items-center gap-2.5">
        {/* Guided 12-Step Live Demo Toggle */}
        <button
          type="button"
          onClick={onToggleGuidedDemo}
          className={`hidden items-center gap-2 rounded-xl border px-3 py-2 text-xs font-semibold transition sm:inline-flex ${
            guidedDemoOpen
              ? "border-cyan-400 bg-cyan-500/20 text-cyan-200 shadow-glow"
              : "border-cyan-500/30 bg-cyan-950/30 text-cyan-300 hover:border-cyan-400/60 hover:bg-cyan-900/30"
          }`}
        >
          <Compass className="h-3.5 w-3.5 text-cyan-400" />
          <span>Guided Demo (12 Steps)</span>
        </button>

        {/* Live Backend Health Pill */}
        <div
          className={`hidden items-center gap-2 rounded-xl border px-3 py-2 text-xs xl:flex ${
            health === null
              ? "border-slate-800 bg-slate-900/60 text-slate-400"
              : isHealthy
              ? "border-emerald-500/25 bg-emerald-950/20 text-emerald-300"
              : "border-rose-500/35 bg-rose-950/30 text-rose-300"
          }`}
        >
          {isHealthy ? (
            <Wifi className="h-3.5 w-3.5 text-emerald-400" />
          ) : (
            <ShieldAlert className="h-3.5 w-3.5 text-rose-400" />
          )}
          <span className="font-mono text-[11px] font-medium">
            {health === null
              ? "PROBING API..."
              : isHealthy
              ? `${health.database.latency_ms}ms`
              : "OFFLINE"}
          </span>
          {health?.database?.connected && (
            <span className="flex items-center gap-1 border-l border-emerald-500/25 pl-2 font-mono text-[10px] text-cyan-300">
              <Database className="h-3 w-3" />
              WAL
            </span>
          )}
        </div>

        {/* Authenticated Session & Role Switcher Dropdown */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setAuthMenuOpen((prev) => !prev)}
            className="flex items-center gap-2 rounded-xl border border-slate-800 bg-slate-900/90 px-3 py-2 text-xs text-slate-200 transition hover:border-cyan-500/40"
          >
            <UserCheck className="h-3.5 w-3.5 text-cyan-400" />
            <div className="hidden text-left md:block">
              <div className="flex items-center gap-1.5">
                <span className="font-medium text-white">
                  {currentUser ? currentUser.full_name : "Unauthenticated"}
                </span>
                {currentUser && (
                  <span
                    className={`rounded border px-1.5 py-0.2 font-mono text-[9px] font-bold uppercase ${roleBadgeColor(
                      currentUser.role
                    )}`}
                  >
                    {currentUser.role}
                  </span>
                )}
              </div>
            </div>
            <ChevronDown className="h-3.5 w-3.5 text-slate-400" />
          </button>

          {authMenuOpen && (
            <div className="absolute right-0 mt-2 w-80 rounded-2xl border border-slate-800 bg-[#080E1E] p-4 shadow-2xl">
              <div className="border-b border-slate-800/80 pb-3">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[10px] uppercase tracking-wider text-cyan-400">
                    Phase 6 RBAC Session Control
                  </span>
                  {currentUser?.is_demo_account && (
                    <span className="rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0.5 font-mono text-[9px] text-amber-300">
                      SYNTHETIC DEMO PERSONA
                    </span>
                  )}
                </div>
                {currentUser ? (
                  <div className="mt-2">
                    <p className="text-xs font-semibold text-white">
                      {currentUser.full_name}
                    </p>
                    <p className="text-[11px] text-slate-400">
                      {currentUser.title} ·{" "}
                      <code className="text-cyan-300">
                        @{currentUser.username}
                      </code>
                    </p>
                  </div>
                ) : (
                  <p className="mt-1 text-xs text-rose-300">
                    No active session. Sign in below.
                  </p>
                )}
              </div>

              {authError && (
                <div className="mt-2.5 rounded-lg border border-rose-500/40 bg-rose-950/40 p-2 text-[11px] text-rose-200">
                  {authError}
                </div>
              )}

              {demoModeEnabled && demoPersonas.length > 0 && (
                <div className="mt-3 space-y-1.5">
                  <p className="font-mono text-[10px] uppercase tracking-wider text-slate-400">
                    Switch Guided Demo Role (Dev Mode)
                  </p>
                  {demoPersonas.map((p) => {
                    const active = currentUser?.username === p.username;
                    return (
                      <button
                        key={p.username}
                        type="button"
                        disabled={authBusy}
                        onClick={() => handlePersonaSelect(p.username)}
                        className={`flex w-full flex-col rounded-xl border p-2.5 text-left transition ${
                          active
                            ? "border-cyan-500/50 bg-cyan-500/15"
                            : "border-slate-800/80 bg-[#050914] hover:border-slate-700"
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-white">
                            {p.full_name}
                          </span>
                          <span
                            className={`rounded border px-1.5 py-0.5 font-mono text-[9px] font-bold ${roleBadgeColor(
                              p.role
                            )}`}
                          >
                            {p.role}
                          </span>
                        </div>
                        <span className="mt-1 text-[10px] text-slate-400">
                          {p.badge_description}
                        </span>
                      </button>
                    );
                  })}
                </div>
              )}

              {/* Password Login Toggle */}
              <div className="mt-3 border-t border-slate-800/80 pt-3">
                <button
                  type="button"
                  onClick={() => setShowPasswordForm((prev) => !prev)}
                  className="flex w-full items-center justify-between rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs text-slate-300 hover:border-cyan-500/30 hover:text-white"
                >
                  <span className="inline-flex items-center gap-1.5">
                    <KeyRound className="h-3.5 w-3.5 text-cyan-400" />
                    <span>Standard Password Sign-In</span>
                  </span>
                  <ChevronDown className="h-3.5 w-3.5" />
                </button>

                {showPasswordForm && (
                  <form
                    onSubmit={handleLoginSubmit}
                    className="mt-2.5 space-y-2 rounded-xl border border-slate-800 bg-[#050914] p-3"
                  >
                    <input
                      type="text"
                      placeholder="Username or email"
                      value={usernameInput}
                      onChange={(e) => setUsernameInput(e.target.value)}
                      className="w-full rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                    />
                    <input
                      type="password"
                      placeholder="Password"
                      value={passwordInput}
                      onChange={(e) => setPasswordInput(e.target.value)}
                      className="w-full rounded-lg border border-slate-800 bg-slate-900 px-2.5 py-1.5 text-xs text-white placeholder-slate-500 focus:border-cyan-500 focus:outline-none"
                    />
                    <button
                      type="submit"
                      disabled={authBusy}
                      className="w-full rounded-lg bg-cyan-500 px-3 py-1.5 text-xs font-semibold text-slate-950 transition hover:bg-cyan-400 disabled:opacity-50"
                    >
                      {authBusy ? "Authenticating..." : "Sign In"}
                    </button>
                  </form>
                )}

                {currentUser && (
                  <button
                    type="button"
                    disabled={authBusy}
                    onClick={async () => {
                      setAuthBusy(true);
                      try {
                        await onLogout();
                        setAuthMenuOpen(false);
                      } finally {
                        setAuthBusy(false);
                      }
                    }}
                    className="mt-2 flex w-full items-center justify-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-950/30 px-3 py-1.5 text-xs font-medium text-rose-300 hover:bg-rose-950/50"
                  >
                    <LogOut className="h-3.5 w-3.5" />
                    <span>Revoke Session &amp; Log Out</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Manual Sync Button */}
        <button
          type="button"
          onClick={onRefresh}
          disabled={isLoading}
          title="Synchronize with SQLite backend"
          className="flex h-10 w-10 items-center justify-center rounded-xl border border-slate-800 bg-slate-900/80 text-slate-300 transition hover:border-cyan-500/40 hover:bg-slate-800/80 hover:text-cyan-300 disabled:opacity-50"
        >
          <RefreshCw
            className={`h-4 w-4 ${isLoading ? "animate-spin text-cyan-400" : ""}`}
          />
        </button>

        {/* Primary CTA: New Investigation (RBAC Guarded for VIEWER) */}
        <button
          type="button"
          onClick={onOpenNewInvestigation}
          disabled={isViewer}
          title={
            isViewer
              ? "VIEWER role is strictly read-only. Switch to INVESTIGATOR or ADMIN to create cases."
              : "Create a new forensic investigation"
          }
          className="inline-flex items-center gap-2 rounded-xl border border-cyan-400/40 bg-gradient-to-r from-blue-600 to-cyan-500 px-4 py-2.5 text-sm font-semibold text-white shadow-glow transition hover:from-blue-500 hover:to-cyan-400 active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Plus className="h-4 w-4 stroke-[2.5]" />
          <span className="hidden sm:inline">New Investigation</span>
        </button>
      </div>
    </header>
  );
}
