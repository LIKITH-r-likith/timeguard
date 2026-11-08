import React, { useState, useEffect } from 'react';
import { X, Calendar, User, Clock, AlertCircle, RefreshCw } from 'lucide-react';
import type { ExceptionDetail } from '../types';
import { api, ApiError } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { DayTimeline } from './DayTimeline';
import { ProposalCard } from './ProposalCard';

interface ExceptionDetailModalProps {
  exceptionId: string | null;
  onClose: () => void;
  onUpdated: () => void;
}

export const ExceptionDetailModal: React.FC<ExceptionDetailModalProps> = ({
  exceptionId,
  onClose,
  onUpdated,
}) => {
  const { currentUser } = useAuth();
  const [detail, setDetail] = useState<ExceptionDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(null);

  const loadDetail = async () => {
    if (!exceptionId) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getException(exceptionId, {
        role: currentUser.role,
        employeeId: currentUser.id,
      });
      setDetail(data);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`[${err.code}] ${err.message}`);
      } else {
        setError('Failed to load exception detail');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDetail();
  }, [exceptionId, currentUser]);

  if (!exceptionId) return null;

  const handleResolve = async () => {
    if (!exceptionId) return;
    setResolving(true);
    setError(null);
    try {
      await api.resolveException(exceptionId, {
        role: currentUser.role,
        employeeId: currentUser.id,
      });
      await loadDetail();
      onUpdated();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`Resolution failed: [${err.code}] ${err.message}`);
      } else {
        setError('Failed to resolve exception');
      }
    } finally {
      setResolving(false);
    }
  };

  const handleApprove = async (comment?: string) => {
    if (!detail?.proposal?.id) return;
    setError(null);
    try {
      await api.approveProposal(detail.proposal.id, { comment }, {
        role: currentUser.role,
        employeeId: currentUser.id,
      });
      await loadDetail();
      onUpdated();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`Approval error: [${err.code}] ${err.message}`);
      } else {
        setError('Approval failed');
      }
    }
  };

  const handleReject = async (comment?: string) => {
    if (!detail?.proposal?.id) return;
    setError(null);
    try {
      await api.rejectProposal(detail.proposal.id, { comment }, {
        role: currentUser.role,
        employeeId: currentUser.id,
      });
      await loadDetail();
      onUpdated();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`Rejection error: [${err.code}] ${err.message}`);
      } else {
        setError('Rejection failed');
      }
    }
  };

  const handleConfirm = async () => {
    if (!detail?.proposal?.id) return;
    setError(null);
    try {
      await api.confirmProposal(detail.proposal.id, {
        role: currentUser.role,
        employeeId: currentUser.id,
      });
      await loadDetail();
      onUpdated();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`Confirmation error: [${err.code}] ${err.message}`);
      } else {
        setError('Confirmation failed');
      }
    }
  };

  const exc = detail?.exception;
  const timecard = detail?.timecard;
  const proposalRecord = detail?.proposal;
  const proposedChanges = proposalRecord?.resolution?.proposal?.changes || [];

  return (
    <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-3 sm:p-6 overflow-y-auto">
      <div className="bg-white rounded-2xl shadow-2xl max-w-5xl w-full max-h-[92vh] flex flex-col overflow-hidden border border-slate-200">
        {/* Modal Header */}
        <div className="px-6 py-4 bg-slate-900 text-white flex items-center justify-between border-b border-slate-800">
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs px-2.5 py-1 rounded bg-indigo-900/80 text-indigo-200 border border-indigo-700">
              {exc ? exc.type : 'Exception'}
            </span>
            <h2 className="text-base font-bold text-white tracking-tight truncate">
              {exc ? exc.id : 'Loading exception...'}
            </h2>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1">
          {error && (
            <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-800 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
              <span>{error}</span>
            </div>
          )}

          {loading && !detail ? (
            <div className="py-20 text-center text-slate-500 text-sm">
              <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-600" />
              Loading exception context and timecard data...
            </div>
          ) : detail && exc && timecard ? (
            <>
              {/* Context Summary Cards */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg flex items-center gap-2.5">
                  <User className="w-4 h-4 text-slate-400 shrink-0" />
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase font-semibold">Employee</span>
                    <span className="font-semibold text-slate-800">{exc.employee_id}</span>
                  </div>
                </div>

                <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg flex items-center gap-2.5">
                  <Calendar className="w-4 h-4 text-slate-400 shrink-0" />
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase font-semibold">Work Date</span>
                    <span className="font-semibold text-slate-800">{exc.work_date}</span>
                  </div>
                </div>

                <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg flex items-center gap-2.5">
                  <Clock className="w-4 h-4 text-slate-400 shrink-0" />
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase font-semibold">Jurisdiction</span>
                    <span className="font-semibold text-slate-800">{timecard.jurisdiction}</span>
                  </div>
                </div>

                <div className="bg-slate-50 border border-slate-200 p-3 rounded-lg flex items-center gap-2.5">
                  <div
                    className={`w-2.5 h-2.5 rounded-full ${
                      exc.risk === 'HIGH'
                        ? 'bg-rose-500'
                        : exc.risk === 'MEDIUM'
                        ? 'bg-amber-500'
                        : 'bg-emerald-500'
                    }`}
                  />
                  <div>
                    <span className="text-slate-500 block text-[10px] uppercase font-semibold">Status / Risk</span>
                    <span className="font-semibold text-slate-800">{exc.status} ({exc.risk || 'UNSET'})</span>
                  </div>
                </div>
              </div>

              {/* Exception Detail Text */}
              <div className="bg-amber-50/70 border border-amber-200 rounded-lg p-3 text-xs text-amber-900 flex items-start gap-2">
                <AlertCircle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                <div>
                  <span className="font-bold">Exception Finding:</span> {exc.detail}
                </div>
              </div>

              {/* Day Timeline Component */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                  Day Schedule &amp; Punch Visualizer
                </h3>
                <DayTimeline
                  workDate={exc.work_date}
                  shifts={timecard.shifts || []}
                  punches={timecard.punches || []}
                  exceptionType={exc.type}
                  highlightedEvidenceId={selectedEvidenceId}
                  proposedChanges={proposedChanges}
                  onSelectEvidence={(id) => setSelectedEvidenceId(id)}
                />
              </div>

              {/* Proposal & Validator Component */}
              <div>
                <ProposalCard
                  exceptionId={exc.id}
                  proposalRecord={proposalRecord}
                  policyClauses={detail.policy_clauses}
                  riskTier={exc.risk}
                  onResolve={handleResolve}
                  onApprove={handleApprove}
                  onReject={handleReject}
                  onConfirm={handleConfirm}
                  onSelectEvidence={(id) => setSelectedEvidenceId(id)}
                  selectedEvidenceId={selectedEvidenceId}
                  isResolving={resolving}
                />
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
};
