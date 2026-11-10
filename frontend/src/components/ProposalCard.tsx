import React, { useState } from 'react';
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
  RotateCcw,
  ShieldAlert,
  Sparkles,
  FileText,
  DollarSign,
  Tag,
  Check,
  X,
  UserCheck,
} from 'lucide-react';
import type { ProposalRecord, PolicyClause, RiskTier } from '../types';
import { useAuth } from '../context/AuthContext';

interface ProposalCardProps {
  exceptionId: string;
  proposalRecord: ProposalRecord | null | undefined;
  policyClauses: PolicyClause[];
  riskTier?: RiskTier | null;
  onResolve: () => Promise<void>;
  onApprove: (comment?: string) => Promise<void>;
  onReject: (comment?: string) => Promise<void>;
  onConfirm: () => Promise<void>;
  onSelectEvidence: (evidenceId: string) => void;
  selectedEvidenceId?: string | null;
  isResolving?: boolean;
}

export const ProposalCard: React.FC<ProposalCardProps> = ({
  exceptionId: _exceptionId,
  proposalRecord,
  policyClauses,
  riskTier,
  onResolve,
  onApprove,
  onReject,
  onConfirm,
  onSelectEvidence,
  selectedEvidenceId,
  isResolving = false,
}) => {
  const { currentUser } = useAuth();
  const [rejectComment, setRejectComment] = useState('');
  const [showRejectDialog, setShowRejectDialog] = useState(false);
  const [actionInProgress, setActionInProgress] = useState(false);

  // If no proposal has been generated yet
  if (!proposalRecord) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm text-center">
        <div className="w-12 h-12 rounded-full bg-indigo-50 border border-indigo-100 flex items-center justify-center mx-auto mb-3 text-indigo-600">
          <Sparkles className="w-6 h-6" />
        </div>
        <h3 className="text-base font-semibold text-slate-900">No Proposal Generated Yet</h3>
        <p className="text-sm text-slate-500 max-w-md mx-auto mt-1 mb-5">
          Run the AI agent resolution loop. The agent inspects context, proposes a fix, and deterministic code validates it before human approval.
        </p>
        <button
          onClick={onResolve}
          disabled={isResolving}
          className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white text-sm font-medium rounded-lg shadow transition-colors"
        >
          {isResolving ? (
            <>
              <RotateCcw className="w-4 h-4 animate-spin" />
              Resolving with Agent...
            </>
          ) : (
            <>
              <Sparkles className="w-4 h-4" />
              Run Agent Resolution
            </>
          )}
        </button>
      </div>
    );
  }

  const res = proposalRecord.resolution;
  const proposal = res.proposal;
  const validation = res.validation;
  const attempts = res.attempts;
  const usedFallback = res.used_fallback;
  const currentRisk = proposalRecord.risk || riskTier || 'LOW';
  const status = proposalRecord.status;

  // RBAC checks for approve/reject
  const isHR = currentUser.role === 'HR';
  const isManager = currentUser.role === 'MANAGER';
  const isEmployee = currentUser.role === 'EMPLOYEE';

  // Can approve logic:
  // - HIGH risk: only HR can approve
  // - MEDIUM risk: Manager or HR
  // - LOW risk: Manager or HR, but if PENDING_CONFIRMATION, must be confirmed first!
  const isHighRisk = currentRisk === 'HIGH';
  const needsConfirmation = status === 'PENDING_CONFIRMATION';
  const isApproved = status === 'APPROVED';
  const isRejected = status === 'REJECTED';

  const canApprove =
    !isApproved &&
    !isRejected &&
    !needsConfirmation &&
    ((isHighRisk && isHR) || (!isHighRisk && (isManager || isHR)));

  const handleApprove = async () => {
    setActionInProgress(true);
    try {
      await onApprove();
    } finally {
      setActionInProgress(false);
    }
  };

  const handleReject = async () => {
    setActionInProgress(true);
    try {
      await onReject(rejectComment);
      setShowRejectDialog(false);
    } finally {
      setActionInProgress(false);
    }
  };

  const handleConfirm = async () => {
    setActionInProgress(true);
    try {
      await onConfirm();
    } finally {
      setActionInProgress(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
      {/* Proposal Header Banner */}
      <div className="bg-slate-50 border-b border-slate-200 px-6 py-4 flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">Proposed Action:</span>
          <span className="px-2.5 py-1 rounded-md text-xs font-bold bg-indigo-100 text-indigo-800 border border-indigo-200">
            {proposal.action}
          </span>

          {/* Badges */}
          {attempts === 2 && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-amber-100 text-amber-800 border border-amber-300">
              <RotateCcw className="w-3.5 h-3.5" />
              Attempt 2 after validator feedback
            </span>
          )}

          {usedFallback && (
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-purple-100 text-purple-800 border border-purple-300">
              <ShieldAlert className="w-3.5 h-3.5" />
              Safe fallback used
            </span>
          )}

          <span
            className={`px-2.5 py-1 rounded-md text-xs font-semibold border ${
              currentRisk === 'HIGH'
                ? 'bg-rose-100 text-rose-800 border-rose-300'
                : currentRisk === 'MEDIUM'
                ? 'bg-amber-100 text-amber-800 border-amber-300'
                : 'bg-emerald-100 text-emerald-800 border-emerald-300'
            }`}
          >
            {currentRisk} RISK
          </span>

          {/* Model Badge */}
          {proposalRecord.model && (
            <span
              className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold border ${
                proposalRecord.model.startsWith('Live model:')
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-300'
                  : 'bg-blue-50 text-blue-800 border-blue-300'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              {proposalRecord.model}
            </span>
          )}
        </div>

        {/* Status indicator */}
        <div>
          {isApproved && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800 border border-emerald-300">
              <Check className="w-3.5 h-3.5" />
              APPROVED
            </span>
          )}
          {isRejected && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-300">
              <X className="w-3.5 h-3.5" />
              REJECTED
            </span>
          )}
          {status === 'PENDING_CONFIRMATION' && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-300">
              <UserCheck className="w-3.5 h-3.5" />
              AWAITING EMPLOYEE CONFIRMATION
            </span>
          )}
          {status === 'PENDING_APPROVAL' && (
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-blue-100 text-blue-800 border border-blue-300">
              <AlertTriangle className="w-3.5 h-3.5" />
              AWAITING {isHighRisk ? 'HR' : 'MANAGER'} APPROVAL
            </span>
          )}
        </div>
      </div>

      <div className="p-6 space-y-6">
        {/* Rationale Block */}
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1.5">Agent Rationale</h4>
          <p className="text-sm text-slate-800 bg-slate-50 p-3 rounded-lg border border-slate-200 leading-relaxed font-sans">
            {proposal.rationale}
          </p>
        </div>

        {/* Clickable Evidence Chips */}
        {proposal.evidence && proposal.evidence.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
              Cited Evidence (Click to Highlight on Timeline)
            </h4>
            <div className="flex flex-wrap gap-2">
              {proposal.evidence.map((ev, idx) => {
                const isSelected = selectedEvidenceId === ev.id;
                return (
                  <button
                    key={`${ev.kind}-${ev.id}-${idx}`}
                    onClick={() => onSelectEvidence(ev.id)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono font-medium border transition-all ${
                      isSelected
                        ? 'bg-indigo-600 text-white border-indigo-700 shadow-sm ring-2 ring-indigo-300'
                        : 'bg-slate-100 hover:bg-slate-200 text-slate-800 border-slate-300'
                    }`}
                  >
                    <Tag className="w-3 h-3 text-slate-500" />
                    <span>
                      {ev.kind}:{ev.id}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        )}

        {/* Policy Clause Citation */}
        {policyClauses && policyClauses.length > 0 && (
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Policy Reference</h4>
            <div className="space-y-2">
              {policyClauses.map((clause) => (
                <div key={clause.id} className="bg-slate-50 border border-slate-200 rounded-lg p-3 text-xs">
                  <div className="flex items-center gap-2 font-semibold text-slate-900 mb-1">
                    <FileText className="w-3.5 h-3.5 text-indigo-600" />
                    <span>[{clause.id}] {clause.title}</span>
                  </div>
                  <p className="text-slate-600 leading-relaxed">{clause.text}</p>
                  {clause.params && Object.keys(clause.params).length > 0 && (
                    <div className="mt-2 pt-2 border-t border-slate-200 flex flex-wrap gap-2">
                      {Object.entries(clause.params).map(([k, v]) => (
                        <span key={k} className="font-mono text-[11px] bg-slate-200/70 px-2 py-0.5 rounded text-slate-700">
                          {k}: {String(v)}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Deterministic Validator Checklist (7 Checks) */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              Deterministic Validator Checklist (7 Checks)
            </h4>
            <span
              className={`text-xs font-semibold px-2 py-0.5 rounded ${
                validation.passed ? 'bg-emerald-100 text-emerald-800' : 'bg-rose-100 text-rose-800'
              }`}
            >
              {validation.passed ? 'ALL CHECKS PASSED' : 'VALIDATION FAILED'}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {validation.checks.map((chk, idx) => (
              <div
                key={`${chk.name}-${idx}`}
                className={`p-2.5 rounded-lg border text-xs flex items-start gap-2 ${
                  chk.passed ? 'bg-emerald-50/50 border-emerald-200' : 'bg-rose-50/60 border-rose-200'
                }`}
              >
                {chk.passed ? (
                  <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                ) : (
                  <XCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                )}
                <div className="min-w-0">
                  <span className="font-mono font-medium text-slate-800 block truncate">{chk.name}</span>
                  <span className="text-slate-600 text-[11px] block">{chk.detail}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Pay Impact Card */}
        {validation.pay_impact && (
          <div className="bg-slate-50 border border-slate-200 rounded-lg p-3.5">
            <div className="flex items-center gap-2 mb-2 text-xs font-semibold uppercase tracking-wider text-slate-700">
              <DollarSign className="w-3.5 h-3.5 text-emerald-600" />
              <span>Pay &amp; Cost Impact (Estimated Mock Value)</span>
            </div>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="bg-white p-2 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block">Regular Time</span>
                <span className="font-bold text-slate-900 text-sm">
                  {validation.pay_impact.regular_minutes_delta > 0 ? '+' : ''}
                  {validation.pay_impact.regular_minutes_delta}m
                </span>
              </div>
              <div className="bg-white p-2 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block">Overtime</span>
                <span className="font-bold text-slate-900 text-sm">
                  {validation.pay_impact.overtime_minutes_delta > 0 ? '+' : ''}
                  {validation.pay_impact.overtime_minutes_delta}m
                </span>
              </div>
              <div className="bg-white p-2 rounded border border-slate-200">
                <span className="text-[11px] text-slate-500 block">Cost Delta</span>
                <span className="font-bold text-emerald-700 text-sm">
                  {validation.pay_impact.currency} {validation.pay_impact.estimated_cost_delta.toFixed(2)}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Actions Bar */}
        <div className="pt-4 border-t border-slate-200 flex flex-wrap items-center justify-between gap-3">
          <div className="text-xs text-slate-500">
            {needsConfirmation && (
              <span className="text-amber-700 font-medium">
                * Low-risk punch adjustment requires employee confirmation prior to manager approval.
              </span>
            )}
            {isHighRisk && !isHR && !isApproved && !isRejected && (
              <span className="text-rose-700 font-medium">
                * High-risk proposals require HR Compliance review to approve.
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {/* If employee is logged in and proposal needs confirmation */}
            {needsConfirmation && isEmployee && (
              <button
                onClick={handleConfirm}
                disabled={actionInProgress}
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
              >
                <UserCheck className="w-4 h-4" />
                Confirm Punch Time
              </button>
            )}

            {/* Reject button */}
            {!isApproved && !isRejected && (isManager || isHR) && (
              <button
                onClick={() => setShowRejectDialog(true)}
                disabled={actionInProgress}
                className="inline-flex items-center gap-1.5 px-3.5 py-2 border border-slate-300 hover:bg-slate-100 text-slate-700 text-xs font-semibold rounded-lg transition-colors"
              >
                <X className="w-4 h-4 text-slate-500" />
                Reject
              </button>
            )}

            {/* Approve button */}
            {!isApproved && !isRejected && (isManager || isHR) && (
              <button
                onClick={handleApprove}
                disabled={!canApprove || actionInProgress}
                title={
                  needsConfirmation
                    ? 'Awaiting employee confirmation'
                    : isHighRisk && !isHR
                    ? 'Requires HR role to approve'
                    : 'Approve proposal'
                }
                className="inline-flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-slate-300 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
              >
                <Check className="w-4 h-4" />
                Approve Proposal
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Reject Comment Dialog */}
      {showRejectDialog && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4">
            <h3 className="text-base font-bold text-slate-900">Reject Proposal</h3>
            <p className="text-xs text-slate-600">
              Provide an optional comment or reason for rejecting this resolution proposal.
            </p>
            <textarea
              value={rejectComment}
              onChange={(e) => setRejectComment(e.target.value)}
              placeholder="e.g. Schedule was modified offline; employee took unrecorded leave."
              className="w-full text-xs p-3 border border-slate-300 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:outline-none min-h-[90px]"
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowRejectDialog(false)}
                className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={handleReject}
                disabled={actionInProgress}
                className="px-4 py-1.5 text-xs font-semibold bg-rose-600 hover:bg-rose-700 text-white rounded-lg shadow-sm"
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
