import React, { useState, useEffect } from 'react';
import { UserCheck, Check, Clock, AlertCircle, RefreshCw } from 'lucide-react';
import type { ExceptionDetail } from '../types';
import { api, ApiError } from '../api/client';
import { useAuth, DEMO_USERS } from '../context/AuthContext';

export const EmployeeConfirmationView: React.FC = () => {
  const { currentUser } = useAuth();
  const [confirmations, setConfirmations] = useState<ExceptionDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // When manager/HR is previewing employee confirmations
  const [selectedEmpId, setSelectedEmpId] = useState<string>(
    currentUser.role === 'EMPLOYEE' ? currentUser.id : 'e01'
  );

  useEffect(() => {
    if (currentUser.role === 'EMPLOYEE') {
      setSelectedEmpId(currentUser.id);
    }
  }, [currentUser]);

  const fetchConfirmations = async () => {
    setLoading(true);
    setError(null);
    const targetEmpId = currentUser.role === 'EMPLOYEE' ? currentUser.id : selectedEmpId;
    try {
      // Calls the employee-scoped confirmation endpoint (never the manager exception queue)
      const data = await api.getEmployeeConfirmations(targetEmpId, {
        role: currentUser.role,
        employeeId: currentUser.id,
      });
      setConfirmations(data);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`[${err.code}] ${err.message}`);
      } else {
        setError('Failed to load confirmations');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchConfirmations();
  }, [currentUser, selectedEmpId]);

  const handleConfirm = async (proposalId: string) => {
    setConfirmingId(proposalId);
    setError(null);
    try {
      await api.confirmProposal(proposalId, {
        role: currentUser.role,
        employeeId: currentUser.id,
      });
      await fetchConfirmations();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`Confirmation error: [${err.code}] ${err.message}`);
      } else {
        setError('Confirmation failed');
      }
    } finally {
      setConfirmingId(null);
    }
  };

  const activeEmpName =
    currentUser.role === 'EMPLOYEE'
      ? currentUser.name
      : DEMO_USERS.find((u) => u.id === selectedEmpId)?.name || selectedEmpId;

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Employee Selector Context Header */}
      <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <UserCheck className="w-5 h-5 text-indigo-600" />
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Employee Self-Service Portal</h1>
          </div>
          <p className="text-xs text-slate-500">
            Employees review proposed punch corrections and confirm accurate timestamps before manager approval.
          </p>
        </div>

        {currentUser.role !== 'EMPLOYEE' ? (
          <div className="bg-amber-50 border border-amber-200 rounded-lg p-2.5 text-xs text-amber-900 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
            <div>
              <span>Manager preview for employee:</span>
              <div className="mt-1 flex items-center gap-1 font-semibold text-indigo-700">
                {DEMO_USERS.filter((u) => u.role === 'EMPLOYEE').slice(0, 5).map((emp) => (
                  <button
                    key={emp.id}
                    onClick={() => setSelectedEmpId(emp.id)}
                    className={`px-1.5 py-0.5 rounded ${
                      selectedEmpId === emp.id
                        ? 'bg-indigo-600 text-white'
                        : 'underline hover:text-indigo-900'
                    }`}
                  >
                    {emp.name.split(' ')[0]} ({emp.id})
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="text-xs text-slate-500 bg-slate-50 border border-slate-200 px-3 py-1.5 rounded-lg">
            Signed in as: <strong className="text-slate-800">{currentUser.name} ({currentUser.id})</strong>
          </div>
        )}
      </div>

      {error && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-800 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Confirmation List */}
      <div className="space-y-4">
        {loading ? (
          <div className="py-20 text-center text-slate-500 text-xs flex flex-col items-center">
            <RefreshCw className="w-6 h-6 animate-spin text-indigo-600 mb-2" />
            Loading pending employee confirmations...
          </div>
        ) : confirmations.length === 0 ? (
          <div className="bg-white p-12 text-center rounded-xl border border-slate-200 shadow-sm">
            <UserCheck className="w-10 h-10 text-emerald-400 mx-auto mb-2" />
            <h3 className="text-base font-semibold text-slate-800">All Clear! No Pending Confirmations</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              There are no timecard changes awaiting confirmation for{' '}
              <strong className="text-slate-700">{activeEmpName}</strong>.
            </p>
          </div>
        ) : (
          confirmations.map((item) => {
            const exc = item.exception;
            const propRecord = item.proposal;
            const prop = propRecord?.resolution?.proposal;

            return (
              <div
                key={exc.id}
                className="bg-white border border-slate-200 rounded-xl shadow-sm p-6 space-y-4 hover:border-indigo-300 transition-colors"
              >
                <div className="flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-100">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs px-2.5 py-1 rounded bg-amber-100 text-amber-900 font-semibold border border-amber-200">
                      CONFIRMATION REQUIRED
                    </span>
                    <span className="text-xs font-semibold text-slate-900">{exc.type}</span>
                    <span className="text-xs text-slate-400 font-mono">({exc.id})</span>
                  </div>
                  <div className="text-xs text-slate-500 flex items-center gap-1.5 font-medium">
                    <Clock className="w-3.5 h-3.5 text-slate-400" />
                    <span>Work Date: {exc.work_date}</span>
                  </div>
                </div>

                <div className="bg-slate-50 p-3.5 rounded-lg border border-slate-200 text-xs text-slate-700">
                  <span className="font-semibold text-slate-900 block mb-1">Incident Detail:</span>
                  <p>{exc.detail}</p>
                </div>

                {prop && (
                  <div className="bg-indigo-50/70 p-4 rounded-lg border border-indigo-200 space-y-2 text-xs">
                    <span className="font-semibold text-indigo-950 block">Proposed Correction:</span>
                    <p className="text-indigo-900 leading-relaxed">{prop.rationale}</p>

                    {prop.changes && prop.changes.length > 0 && (
                      <div className="pt-2 border-t border-indigo-100 mt-2 space-y-1">
                        {prop.changes.map((ch, idx) => (
                          <div key={idx} className="flex items-center gap-2 font-mono text-[11px] text-indigo-800">
                            <span className="font-bold uppercase tracking-wider">{ch.op}:</span>
                            <span>{ch.type} punch at {ch.at}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div className="flex items-center justify-between pt-2">
                  <span className="text-[11px] text-slate-500">
                    * Confirming validates that you performed work as stated during this period.
                  </span>

                  {propRecord && (
                    <button
                      onClick={() => handleConfirm(propRecord.id)}
                      disabled={confirmingId === propRecord.id}
                      className="inline-flex items-center gap-2 px-5 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:bg-emerald-400 text-white text-xs font-semibold rounded-lg shadow transition-colors"
                    >
                      {confirmingId === propRecord.id ? (
                        <>
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                          Confirming...
                        </>
                      ) : (
                        <>
                          <Check className="w-4 h-4" />
                          Confirm This Timecard Change
                        </>
                      )}
                    </button>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
