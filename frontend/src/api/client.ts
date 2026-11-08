import type {
  AuditEntry,
  AuditVerifyResult,
  DecisionRequest,
  ErrorResponse,
  EvalReport,
  ExceptionDetail,
  ExceptionRecord,
  ExceptionStatus,
  Metrics,
  ProposalRecord,
  RiskTier,
  Role,
  RunTrace,
  ScanRequest,
  ScanResponse,
} from '../types';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export class ApiError extends Error {
  code: string;
  details: Record<string, unknown>;
  status: number;

  constructor(status: number, err: ErrorResponse) {
    super(err.message || 'API request failed');
    this.name = 'ApiError';
    this.code = err.code || 'UNKNOWN_ERROR';
    this.details = err.details || {};
    this.status = status;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  auth: { role: Role; employeeId?: string }
): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    'X-Role': auth.role,
    ...(auth.employeeId ? { 'X-Employee-Id': auth.employeeId } : {}),
    ...(options.headers as Record<string, string>),
  };

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
  });

  if (!res.ok) {
    let errBody: ErrorResponse = {
      code: 'HTTP_' + res.status,
      message: res.statusText || 'Request failed',
      details: {},
    };
    try {
      const data = await res.json();
      if (data && (data.code || data.message || data.detail)) {
        if (data.detail && typeof data.detail === 'object' && data.detail.code) {
          errBody = data.detail;
        } else if (data.code) {
          errBody = data;
        } else if (data.message) {
          errBody = { code: 'HTTP_' + res.status, message: data.message, details: data.details || {} };
        }
      }
    } catch {
      // Fallback to default errBody
    }
    throw new ApiError(res.status, errBody);
  }

  return (await res.json()) as T;
}

export const api = {
  scan: (data: ScanRequest, auth: { role: Role; employeeId?: string }) =>
    request<ScanResponse>('/scan', { method: 'POST', body: JSON.stringify(data) }, auth),

  listExceptions: (
    params?: { status?: ExceptionStatus; risk?: RiskTier },
    auth?: { role: Role; employeeId?: string }
  ) => {
    const q = new URLSearchParams();
    if (params?.status) q.append('status', params.status);
    if (params?.risk) q.append('risk', params.risk);
    const qs = q.toString() ? `?${q.toString()}` : '';
    return request<ExceptionRecord[]>(`/exceptions${qs}`, { method: 'GET' }, auth || { role: 'MANAGER' });
  },

  getException: (id: string, auth: { role: Role; employeeId?: string }) =>
    request<ExceptionDetail>(`/exceptions/${id}`, { method: 'GET' }, auth),

  getEmployeeConfirmations: (employeeId: string, auth: { role: Role; employeeId?: string }) =>
    request<ExceptionDetail[]>(`/employees/${employeeId}/confirmations`, { method: 'GET' }, auth),

  resolveException: (id: string, auth: { role: Role; employeeId?: string }) =>
    request<ProposalRecord>(`/exceptions/${id}/resolve`, { method: 'POST' }, auth),

  confirmProposal: (id: string, auth: { role: Role; employeeId?: string }) =>
    request<ProposalRecord>(`/proposals/${id}/confirm`, { method: 'POST' }, auth),

  approveProposal: (id: string, body: DecisionRequest, auth: { role: Role; employeeId?: string }) =>
    request<ProposalRecord>(`/proposals/${id}/approve`, { method: 'POST', body: JSON.stringify(body) }, auth),

  rejectProposal: (id: string, body: DecisionRequest, auth: { role: Role; employeeId?: string }) =>
    request<ProposalRecord>(`/proposals/${id}/reject`, { method: 'POST', body: JSON.stringify(body) }, auth),

  getAudit: (limit = 100, auth?: { role: Role; employeeId?: string }) =>
    request<AuditEntry[]>(`/audit?limit=${limit}`, { method: 'GET' }, auth || { role: 'MANAGER' }),

  verifyAudit: (auth?: { role: Role; employeeId?: string }) =>
    request<AuditVerifyResult>('/audit/verify', { method: 'GET' }, auth || { role: 'MANAGER' }),

  getMetrics: (auth?: { role: Role; employeeId?: string }) =>
    request<Metrics>('/metrics', { method: 'GET' }, auth || { role: 'MANAGER' }),

  getRunTrace: (traceId: string, auth?: { role: Role; employeeId?: string }) =>
    request<RunTrace>(`/runs/${traceId}`, { method: 'GET' }, auth || { role: 'MANAGER' }),

  getLatestEval: (auth?: { role: Role; employeeId?: string }) =>
    request<EvalReport>('/evals/latest', { method: 'GET' }, auth || { role: 'MANAGER' }),
};
