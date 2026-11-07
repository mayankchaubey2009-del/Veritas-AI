import {
  AuditLogEntry,
  AuditVerificationResult,
  AuthenticatedUser,
  AuthSessionResponse,
  AuthStatusResponse,
  BackgroundJob,
  CommandCentreSummary,
  ContextualAnalysisBundle,
  ContextualFinding,
  DatabaseBackupManifest,
  DocumentDetail,
  DocumentExtractionBundle,
  DocumentPage,
  DocumentSummary,
  DossierDetail,
  DossierSummary,
  FinancialValidationResult,
  ForensicAnalysisDetail,
  ForensicFinding,
  HealthStatusResponse,
  Investigation,
  InvestigationCreatePayload,
  InvestigationDetail,
  InvestigationEntityGraph,
  InvestigationReasoning,
  InvestigationUpdatePayload,
  MultiDocumentUploadResponse,
  QualityBenchmarkReport,
  SanitizedSystemConfig,
} from "@/types/veritas";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:8000/api";
const SESSION_TOKEN_STORAGE_KEY = "veritas_phase6_session_token";

let inMemorySessionToken: string | null = null;

export function getStoredSessionToken(): string | null {
  if (inMemorySessionToken) return inMemorySessionToken;
  if (typeof window !== "undefined") {
    try {
      const val = window.localStorage.getItem(SESSION_TOKEN_STORAGE_KEY);
      if (val && val.trim().length > 0) {
        inMemorySessionToken = val.trim();
        return inMemorySessionToken;
      }
    } catch {
      // Ignore storage access errors
    }
  }
  return null;
}

export function setStoredSessionToken(token: string | null): void {
  inMemorySessionToken = token && token.trim() ? token.trim() : null;
  if (typeof window !== "undefined") {
    try {
      if (inMemorySessionToken) {
        window.localStorage.setItem(
          SESSION_TOKEN_STORAGE_KEY,
          inMemorySessionToken
        );
      } else {
        window.localStorage.removeItem(SESSION_TOKEN_STORAGE_KEY);
      }
    } catch {
      // Ignore storage access errors
    }
  }
}

export function getApiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL;
  if (configured && configured.trim().length > 0) {
    return configured.trim().replace(/\/+$/, "");
  }
  return DEFAULT_API_BASE_URL;
}

function appendTokenQuery(url: string): string {
  const tok = getStoredSessionToken();
  if (!tok) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(tok)}`;
}

export class ApiClientError extends Error {
  public readonly statusCode: number;
  public readonly code: string;
  public readonly details?: unknown;

  constructor(
    message: string,
    statusCode = 500,
    code = "API_ERROR",
    details?: unknown
  ) {
    super(message);
    this.name = "ApiClientError";
    this.statusCode = statusCode;
    this.code = code;
    this.details = details;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${getApiBaseUrl()}${path.startsWith("/") ? path : `/${path}`}`;
  const token = getStoredSessionToken();

  const authHeaders: Record<string, string> = {};
  if (token) {
    authHeaders["Authorization"] = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
        ...authHeaders,
        ...(options.headers || {}),
      },
      cache: "no-store",
    });
  } catch (networkErr) {
    throw new ApiClientError(
      `Unable to reach VERITAS AI Backend at ${getApiBaseUrl()}. Verify FastAPI is running on port 8000.`,
      0,
      "NETWORK_UNREACHABLE",
      networkErr
    );
  }

  if (!response.ok) {
    let errorMessage = `Backend request failed (${response.status})`;
    let errorCode = `HTTP_${response.status}`;
    let errorDetails: unknown = undefined;

    try {
      const errBody = await response.json();
      if (errBody?.error) {
        errorMessage = errBody.error.message || errorMessage;
        errorCode = errBody.error.code || errorCode;
        errorDetails = errBody.error.details;
      } else if (errBody?.detail) {
        errorMessage =
          typeof errBody.detail === "string"
            ? errBody.detail
            : JSON.stringify(errBody.detail);
      }
    } catch {
      // Response was not JSON
    }

    throw new ApiClientError(
      errorMessage,
      response.status,
      errorCode,
      errorDetails
    );
  }

  return (await response.json()) as T;
}

export const veritasApi = {
  // PHASE 6 — Authentication, RBAC & Demo Persona Switching
  getAuthStatus: (): Promise<AuthStatusResponse> =>
    request<AuthStatusResponse>("/auth/me"),

  login: async (payload: {
    username: string;
    password: string;
  }): Promise<AuthSessionResponse> => {
    const res = await request<AuthSessionResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (res.access_token) {
      setStoredSessionToken(res.access_token);
    }
    return res;
  },

  logout: async (): Promise<{ logged_out: boolean }> => {
    try {
      return await request<{ logged_out: boolean }>("/auth/logout", {
        method: "POST",
      });
    } finally {
      setStoredSessionToken(null);
    }
  },

  switchDemoPersona: async (username: string): Promise<AuthSessionResponse> => {
    const res = await request<AuthSessionResponse>("/auth/demo-session", {
      method: "POST",
      body: JSON.stringify({ username }),
    });
    if (res.access_token) {
      setStoredSessionToken(res.access_token);
    }
    return res;
  },

  bootstrapInitialAdmin: async (payload: {
    username: string;
    full_name: string;
    password: string;
    email?: string;
    title?: string;
    bootstrap_token?: string;
  }): Promise<AuthSessionResponse> => {
    const res = await request<AuthSessionResponse>("/auth/bootstrap", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (res.access_token) {
      setStoredSessionToken(res.access_token);
    }
    return res;
  },

  listUsers: (): Promise<AuthenticatedUser[]> =>
    request<AuthenticatedUser[]>("/auth/users"),

  createUser: (payload: {
    username: string;
    full_name: string;
    role: string;
    title?: string;
    email?: string;
    password: string;
  }): Promise<AuthenticatedUser> =>
    request<AuthenticatedUser>("/auth/users", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  // Core Health, System Config, Quality Benchmark & Backups
  getHealth: (): Promise<HealthStatusResponse> =>
    request<HealthStatusResponse>("/health"),

  getSystemConfig: (): Promise<SanitizedSystemConfig> =>
    request<SanitizedSystemConfig>("/system/config"),

  runQualityBenchmark: (): Promise<QualityBenchmarkReport> =>
    request<QualityBenchmarkReport>("/system/benchmark", {
      method: "POST",
    }),

  listBackups: (): Promise<DatabaseBackupManifest[]> =>
    request<DatabaseBackupManifest[]>("/system/backups"),

  createBackup: (label?: string): Promise<DatabaseBackupManifest> =>
    request<DatabaseBackupManifest>("/system/backups", {
      method: "POST",
      body: JSON.stringify({ label: label ?? "Manual Forensic Store Snapshot" }),
    }),

  verifyOrRestoreBackup: (
    backupId: string,
    performRestore = false
  ): Promise<Record<string, unknown>> =>
    request<Record<string, unknown>>(
      `/system/backups/${encodeURIComponent(backupId)}/verify`,
      {
        method: "POST",
        body: JSON.stringify({ perform_restore: performRestore }),
      }
    ),

  // PHASE 6 — Background Jobs & Recovery
  listJobs: (params?: {
    investigation_id?: string;
    limit?: number;
  }): Promise<BackgroundJob[]> => {
    const query = new URLSearchParams();
    if (params?.investigation_id)
      query.set("investigation_id", params.investigation_id);
    if (params?.limit) query.set("limit", String(params.limit));
    const qs = query.toString();
    return request<BackgroundJob[]>(`/jobs${qs ? `?${qs}` : ""}`);
  },

  enqueueJob: (payload: {
    investigation_id: string;
    document_id?: string | null;
    job_type: string;
    execute_immediately?: boolean;
    simulate_failure_once?: boolean;
  }): Promise<BackgroundJob> =>
    request<BackgroundJob>("/jobs/enqueue", {
      method: "POST",
      body: JSON.stringify({
        investigation_id: payload.investigation_id,
        document_id: payload.document_id ?? null,
        job_type: payload.job_type,
        execute_immediately: payload.execute_immediately ?? true,
        simulate_failure_once: payload.simulate_failure_once ?? false,
      }),
    }),

  retryJob: (jobId: string): Promise<BackgroundJob> =>
    request<BackgroundJob>(`/jobs/${encodeURIComponent(jobId)}/retry`, {
      method: "POST",
    }),

  cancelJob: (jobId: string): Promise<BackgroundJob> =>
    request<BackgroundJob>(`/jobs/${encodeURIComponent(jobId)}/cancel`, {
      method: "POST",
    }),

  getCommandCentreSummary: (): Promise<CommandCentreSummary> =>
    request<CommandCentreSummary>("/dashboard/summary"),

  listInvestigations: (params?: {
    status?: string;
    priority?: string;
    search?: string;
    limit?: number;
  }): Promise<Investigation[]> => {
    const query = new URLSearchParams();
    if (params?.status) query.set("status", params.status);
    if (params?.priority) query.set("priority", params.priority);
    if (params?.search) query.set("search", params.search);
    if (params?.limit) query.set("limit", String(params.limit));
    const qs = query.toString();
    return request<Investigation[]>(`/investigations${qs ? `?${qs}` : ""}`);
  },

  getInvestigationDetail: (id: string): Promise<InvestigationDetail> =>
    request<InvestigationDetail>(`/investigations/${encodeURIComponent(id)}`),

  createInvestigation: (
    payload: InvestigationCreatePayload
  ): Promise<Investigation> =>
    request<Investigation>("/investigations", {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  updateInvestigation: (
    id: string,
    payload: InvestigationUpdatePayload
  ): Promise<Investigation> =>
    request<Investigation>(`/investigations/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),

  addCaseNote: (
    id: string,
    payload: { actor: string; note: string }
  ): Promise<AuditLogEntry> =>
    request<AuditLogEntry>(`/investigations/${encodeURIComponent(id)}/notes`, {
      method: "POST",
      body: JSON.stringify(payload),
    }),

  deleteInvestigation: (
    id: string
  ): Promise<{ deleted: boolean; id: string; case_code: string }> =>
    request<{ deleted: boolean; id: string; case_code: string }>(
      `/investigations/${encodeURIComponent(id)}`,
      {
        method: "DELETE",
      }
    ),

  listAuditLogs: (params?: {
    investigation_id?: string;
    limit?: number;
  }): Promise<AuditLogEntry[]> => {
    const query = new URLSearchParams();
    if (params?.investigation_id)
      query.set("investigation_id", params.investigation_id);
    if (params?.limit) query.set("limit", String(params.limit));
    const qs = query.toString();
    return request<AuditLogEntry[]>(`/audit-logs${qs ? `?${qs}` : ""}`);
  },

  verifyAuditLogs: (): Promise<AuditVerificationResult> =>
    request<AuditVerificationResult>("/audit-logs/verify"),

  // PHASE 2A — Document Intelligence & Dual-Path Extraction Endpoints
  uploadInvestigationDocuments: (
    investigationId: string,
    files: File[],
    actor = "Lead Forensic Analyst",
    onProgress?: (percent: number) => void
  ): Promise<MultiDocumentUploadResponse> => {
    return new Promise((resolve, reject) => {
      const url = `${getApiBaseUrl()}/investigations/${encodeURIComponent(
        investigationId
      )}/documents`;
      const formData = new FormData();
      for (const file of files) {
        formData.append("files", file);
      }
      formData.append("actor", actor);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", url, true);
      xhr.withCredentials = true;
      xhr.setRequestHeader("Accept", "application/json");
      const token = getStoredSessionToken();
      if (token) {
        xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      }

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable && onProgress) {
          const pct = Math.min(95, Math.round((event.loaded / event.total) * 100));
          onProgress(pct);
        }
      };

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          if (onProgress) onProgress(100);
          try {
            const parsed = JSON.parse(
              xhr.responseText
            ) as MultiDocumentUploadResponse;
            resolve(parsed);
          } catch (parseErr) {
            reject(
              new ApiClientError(
                "Invalid JSON response from document upload endpoint.",
                xhr.status,
                "PARSE_ERROR",
                parseErr
              )
            );
          }
        } else {
          let errMsg = `Document upload failed (${xhr.status})`;
          let errCode = `HTTP_${xhr.status}`;
          let errDetails: unknown = undefined;
          try {
            const errJson = JSON.parse(xhr.responseText);
            if (errJson?.error) {
              errMsg = errJson.error.message || errMsg;
              errCode = errJson.error.code || errCode;
              errDetails = errJson.error.details;
            }
          } catch {
            // Non-JSON response
          }
          reject(new ApiClientError(errMsg, xhr.status, errCode, errDetails));
        }
      };

      xhr.onerror = () => {
        reject(
          new ApiClientError(
            `Network error while uploading documents to ${getApiBaseUrl()}.`,
            0,
            "NETWORK_ERROR"
          )
        );
      };

      xhr.send(formData);
    });
  },

  listInvestigationDocuments: (
    investigationId: string
  ): Promise<DocumentSummary[]> =>
    request<DocumentSummary[]>(
      `/investigations/${encodeURIComponent(investigationId)}/documents`
    ),

  getDocumentDetail: (documentId: string): Promise<DocumentDetail> =>
    request<DocumentDetail>(`/documents/${encodeURIComponent(documentId)}`),

  getDocumentDownloadUrl: (documentId: string): string =>
    appendTokenQuery(
      `${getApiBaseUrl()}/documents/${encodeURIComponent(documentId)}/download`
    ),

  getDocumentExtraction: (
    documentId: string,
    params?: {
      page_number?: number;
      extraction_method?: string;
      structured_only?: boolean;
    }
  ): Promise<DocumentExtractionBundle> => {
    const query = new URLSearchParams();
    if (params?.page_number !== undefined)
      query.set("page_number", String(params.page_number));
    if (params?.extraction_method)
      query.set("extraction_method", params.extraction_method);
    if (params?.structured_only) query.set("structured_only", "true");
    const qs = query.toString();
    return request<DocumentExtractionBundle>(
      `/documents/${encodeURIComponent(documentId)}/extraction${
        qs ? `?${qs}` : ""
      }`
    );
  },

  getDocumentPage: (
    documentId: string,
    pageNumber: number
  ): Promise<DocumentPage> =>
    request<DocumentPage>(
      `/documents/${encodeURIComponent(documentId)}/pages/${pageNumber}`
    ),

  getDocumentPagePreviewUrl: (
    documentId: string,
    pageNumber: number
  ): string =>
    appendTokenQuery(
      `${getApiBaseUrl()}/documents/${encodeURIComponent(
        documentId
      )}/pages/${pageNumber}/preview`
    ),

  // PHASE 3 — Visual Forensics & Document Authenticity Signal Analysis Endpoints
  analyzeDocumentForensics: (
    documentId: string,
    params?: {
      actor?: string;
      ela_jpeg_quality?: number;
      ela_amplification_scale?: number;
      force_reanalyze?: boolean;
    }
  ): Promise<ForensicAnalysisDetail> =>
    request<ForensicAnalysisDetail>(
      `/documents/${encodeURIComponent(documentId)}/forensics/analyze`,
      {
        method: "POST",
        body: JSON.stringify({
          actor: params?.actor ?? "Dr. Elena Rostova (Principal Forensic Analyst)",
          ela_jpeg_quality: params?.ela_jpeg_quality ?? 90,
          ela_amplification_scale: params?.ela_amplification_scale ?? 18.0,
          force_reanalyze: params?.force_reanalyze ?? true,
        }),
      }
    ),

  getDocumentForensics: (documentId: string): Promise<ForensicAnalysisDetail> =>
    request<ForensicAnalysisDetail>(
      `/documents/${encodeURIComponent(documentId)}/forensics`
    ),

  listDocumentForensicFindings: (
    documentId: string,
    params?: {
      severity?: string;
      module_name?: string;
      review_status?: string;
    }
  ): Promise<ForensicFinding[]> => {
    const query = new URLSearchParams();
    if (params?.severity) query.set("severity", params.severity);
    if (params?.module_name) query.set("module_name", params.module_name);
    if (params?.review_status) query.set("review_status", params.review_status);
    const qs = query.toString();
    return request<ForensicFinding[]>(
      `/documents/${encodeURIComponent(documentId)}/forensics/findings${
        qs ? `?${qs}` : ""
      }`
    );
  },

  getForensicAnalysisById: (
    analysisId: string
  ): Promise<ForensicAnalysisDetail> =>
    request<ForensicAnalysisDetail>(
      `/forensics/analyses/${encodeURIComponent(analysisId)}`
    ),

  getForensicFindingById: (findingId: string): Promise<ForensicFinding> =>
    request<ForensicFinding>(
      `/forensics/findings/${encodeURIComponent(findingId)}`
    ),

  reviewForensicFinding: (
    findingId: string,
    payload: {
      review_status: string;
      reviewer: string;
      notes: string;
    }
  ): Promise<ForensicFinding> =>
    request<ForensicFinding>(
      `/forensics/findings/${encodeURIComponent(findingId)}/review`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),

  getForensicArtifactUrl: (artifactId: string): string =>
    appendTokenQuery(
      `${getApiBaseUrl()}/forensics/artifacts/${encodeURIComponent(artifactId)}`
    ),

  // PHASE 4 — Contextual Intelligence & Cross-Document Contradiction Analysis Endpoints
  analyzeInvestigationContext: (
    investigationId: string,
    params?: {
      actor?: string;
      force_reanalyze?: boolean;
    }
  ): Promise<ContextualAnalysisBundle> =>
    request<ContextualAnalysisBundle>(
      `/investigations/${encodeURIComponent(investigationId)}/context/analyze`,
      {
        method: "POST",
        body: JSON.stringify({
          actor: params?.actor ?? "Dr. Elena Rostova (Principal Forensic Analyst)",
          force_reanalyze: params?.force_reanalyze ?? true,
        }),
      }
    ),

  getInvestigationContext: (
    investigationId: string
  ): Promise<ContextualAnalysisBundle> =>
    request<ContextualAnalysisBundle>(
      `/investigations/${encodeURIComponent(investigationId)}/context`
    ),

  listInvestigationContextualFindings: (
    investigationId: string,
    params?: {
      severity?: string;
      status?: string;
      review_status?: string;
    }
  ): Promise<ContextualFinding[]> => {
    const query = new URLSearchParams();
    if (params?.severity) query.set("severity", params.severity);
    if (params?.status) query.set("status", params.status);
    if (params?.review_status) query.set("review_status", params.review_status);
    const qs = query.toString();
    return request<ContextualFinding[]>(
      `/investigations/${encodeURIComponent(investigationId)}/context/findings${
        qs ? `?${qs}` : ""
      }`
    );
  },

  getInvestigationGraph: (
    investigationId: string
  ): Promise<InvestigationEntityGraph> =>
    request<InvestigationEntityGraph>(
      `/investigations/${encodeURIComponent(investigationId)}/context/graph`
    ),

  getInvestigationFinancialValidation: (
    investigationId: string
  ): Promise<FinancialValidationResult[]> =>
    request<FinancialValidationResult[]>(
      `/investigations/${encodeURIComponent(
        investigationId
      )}/context/financial-validation`
    ),

  getContextualFindingById: (findingId: string): Promise<ContextualFinding> =>
    request<ContextualFinding>(
      `/context/findings/${encodeURIComponent(findingId)}`
    ),

  reviewContextualFinding: (
    findingId: string,
    payload: {
      review_status: string;
      reviewer: string;
      notes: string;
    }
  ): Promise<ContextualFinding> =>
    request<ContextualFinding>(
      `/context/findings/${encodeURIComponent(findingId)}/review`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),

  // PHASE 5 — AI Investigation Reasoning & Automated Evidence Dossier Generation Endpoints
  generateInvestigationReasoning: (
    investigationId: string,
    params?: {
      actor?: string;
      use_ai_provider_if_available?: boolean;
    }
  ): Promise<InvestigationReasoning> =>
    request<InvestigationReasoning>(
      `/investigations/${encodeURIComponent(investigationId)}/reasoning/generate`,
      {
        method: "POST",
        body: JSON.stringify({
          actor: params?.actor ?? "Dr. Elena Rostova (Principal Forensic Analyst)",
          use_ai_provider_if_available:
            params?.use_ai_provider_if_available ?? true,
        }),
      }
    ),

  getInvestigationReasoning: (
    investigationId: string
  ): Promise<InvestigationReasoning> =>
    request<InvestigationReasoning>(
      `/investigations/${encodeURIComponent(investigationId)}/reasoning`
    ),

  generateInvestigationDossier: (
    investigationId: string,
    params?: {
      actor?: string;
      title?: string;
      regenerate_reasoning?: boolean;
    }
  ): Promise<DossierDetail> =>
    request<DossierDetail>(
      `/investigations/${encodeURIComponent(investigationId)}/dossiers/generate`,
      {
        method: "POST",
        body: JSON.stringify({
          actor: params?.actor ?? "Dr. Elena Rostova (Principal Forensic Analyst)",
          title: params?.title ?? null,
          regenerate_reasoning: params?.regenerate_reasoning ?? true,
        }),
      }
    ),

  listInvestigationDossiers: (
    investigationId: string
  ): Promise<DossierSummary[]> =>
    request<DossierSummary[]>(
      `/investigations/${encodeURIComponent(investigationId)}/dossiers`
    ),

  getDossierDetail: (dossierId: string): Promise<DossierDetail> =>
    request<DossierDetail>(`/dossiers/${encodeURIComponent(dossierId)}`),

  getDossierPdfUrl: (dossierId: string): string =>
    appendTokenQuery(
      `${getApiBaseUrl()}/dossiers/${encodeURIComponent(dossierId)}/pdf`
    ),

  getDossierJsonUrl: (dossierId: string): string =>
    appendTokenQuery(
      `${getApiBaseUrl()}/dossiers/${encodeURIComponent(dossierId)}/json`
    ),

  reviewDossier: (
    dossierId: string,
    payload: {
      review_status: string;
      reviewer?: string;
      notes: string;
    }
  ): Promise<DossierDetail> =>
    request<DossierDetail>(
      `/dossiers/${encodeURIComponent(dossierId)}/review`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    ),
};
