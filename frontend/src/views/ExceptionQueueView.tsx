import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  Play,
  Filter,
  CheckCircle,
  Clock,
  UserCheck,
  Search,
  RefreshCw,
  ChevronRight,
} from 'lucide-react';
import type { ExceptionRecord, ExceptionStatus, RiskTier } from '../types';
import { api, ApiError } from '../api/client';
import { useAuth } from '../context/AuthContext';
import { ExceptionDetailModal } from '../components/ExceptionDetailModal';

interface ExceptionQueueViewProps {
  initialSelectedId?: string | null;
}

export const ExceptionQueueView: React.FC<ExceptionQueueViewProps> = ({
  initialSelectedId = null,
}) => {
  const { currentUser } = useAuth();
  const [exceptions, setExceptions] = useState<ExceptionRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [statusFilter, setStatusFilter] = useState<string>('ALL');
  const [riskFilter, setRiskFilter] = useState<string>('ALL');
  const [searchTerm, setSearchTerm] = useState<string>('');

  // Period for scanning (default Week 3: 2026-11-02 to 2026-11-08)
  const [periodStart, setPeriodStart] = useState('2026-11-02');
  const [periodEnd, setPeriodEnd] = useState('2026-11-08');
  const [showScanModal, setShowScanModal] = useState(false);

  // Active modal
  const [selectedExceptionId, setSelectedExceptionId] = useState<string | null>(initialSelectedId);

  const fetchExceptions = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listExceptions(
        {
          status: statusFilter !== 'ALL' ? (statusFilter as ExceptionStatus) : undefined,
          risk: riskFilter !== 'ALL' ? (riskFilter as RiskTier) : undefined,
        },
        { role: currentUser.role, employeeId: currentUser.id }
      );
      setExceptions(data);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`[${err.code}] ${err.message}`);
      } else {
        setError('Failed to fetch exceptions');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExceptions();
  }, [statusFilter, riskFilter, currentUser]);

  const handleScanPeriod = async () => {
    setScanning(true);
    setError(null);
    try {
      await api.scan(
        { period_start: periodStart, period_end: periodEnd },
        { role: currentUser.role, employeeId: currentUser.id }
      );
      setShowScanModal(false);
      await fetchExceptions();
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`Scan failed: [${err.code}] ${err.message}`);
      } else {
        setError('Failed to scan pay period');
      }
    } finally {
      setScanning(false);
    }
  };

  // Filtered exceptions by search term
  const filteredExceptions = exceptions.filter((e) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      e.id.toLowerCase().includes(term) ||
      e.employee_id.toLowerCase().includes(term) ||
      e.type.toLowerCase().includes(term) ||
      e.detail.toLowerCase().includes(term)
    );
  });

  // KPI counts
  const totalCount = exceptions.length;
  const awaitingEmpCount = exceptions.filter((e) => e.status === 'AWAITING_EMPLOYEE').length;
  const awaitingApprCount = exceptions.filter((e) => e.status === 'AWAITING_APPROVAL').length;
  const resolvedCount = exceptions.filter((e) => e.status === 'RESOLVED').length;
  const highRiskCount = exceptions.filter((e) => e.risk === 'HIGH').length;

  const getRiskBadge = (risk?: RiskTier | null) => {
    switch (risk) {
      case 'HIGH':
        return <span className="px-2 py-0.5 text-[11px] font-bold rounded bg-rose-100 text-rose-800 border border-rose-300">HIGH</span>;
      case 'MEDIUM':
        return <span className="px-2 py-0.5 text-[11px] font-bold rounded bg-amber-100 text-amber-800 border border-amber-300">MED</span>;
      case 'LOW':
        return <span className="px-2 py-0.5 text-[11px] font-bold rounded bg-emerald-100 text-emerald-800 border border-emerald-300">LOW</span>;
      default:
        return <span className="px-2 py-0.5 text-[11px] font-semibold rounded bg-slate-100 text-slate-600 border border-slate-300">UNSET</span>;
    }
  };

  const getStatusBadge = (status: ExceptionStatus) => {
    switch (status) {
      case 'OPEN':
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-md bg-slate-100 text-slate-700">Open</span>;
      case 'AWAITING_EMPLOYEE':
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-md bg-amber-100 text-amber-800 border border-amber-200">Awaiting Employee</span>;
      case 'AWAITING_APPROVAL':
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-md bg-blue-100 text-blue-800 border border-blue-200">Awaiting Approval</span>;
      case 'RESOLVED':
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-md bg-emerald-100 text-emerald-800 border border-emerald-200">Resolved</span>;
      case 'ESCALATED':
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-md bg-purple-100 text-purple-800 border border-purple-200">Escalated</span>;
      default:
        return <span className="px-2.5 py-1 text-xs font-semibold rounded-md bg-slate-100 text-slate-700">{status}</span>;
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Banner & Scan Action */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-xl font-bold text-slate-900 tracking-tight">Timecard Exception Queue</h1>
          <p className="text-xs text-slate-500 mt-1">
            Deterministic rules detect violations &bull; LLM proposes resolution &bull; Deterministic engine validates &bull; Human approves
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => fetchExceptions()}
            disabled={loading}
            className="p-2 border border-slate-200 hover:bg-slate-50 text-slate-600 rounded-lg text-xs font-medium transition-colors"
            title="Refresh list"
            aria-label="Refresh list"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-indigo-600' : ''}`} />
          </button>

          {(currentUser.role === 'MANAGER' || currentUser.role === 'HR') && (
            <button
              onClick={() => setShowScanModal(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
            >
              <Play className="w-3.5 h-3.5 fill-current" />
              Scan Pay Period
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="p-4 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">Total Tracked</span>
          <span className="text-2xl font-bold text-slate-900 mt-1 block">{totalCount}</span>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <span className="text-[11px] font-semibold text-amber-600 uppercase tracking-wider block flex items-center gap-1">
            <UserCheck className="w-3.5 h-3.5" />
            Needs Confirmed
          </span>
          <span className="text-2xl font-bold text-amber-700 mt-1 block">{awaitingEmpCount}</span>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <span className="text-[11px] font-semibold text-blue-600 uppercase tracking-wider block flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" />
            Needs Approval
          </span>
          <span className="text-2xl font-bold text-blue-700 mt-1 block">{awaitingApprCount}</span>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <span className="text-[11px] font-semibold text-emerald-600 uppercase tracking-wider block flex items-center gap-1">
            <CheckCircle className="w-3.5 h-3.5" />
            Resolved
          </span>
          <span className="text-2xl font-bold text-emerald-700 mt-1 block">{resolvedCount}</span>
        </div>

        <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm">
          <span className="text-[11px] font-semibold text-rose-600 uppercase tracking-wider block flex items-center gap-1">
            <AlertTriangle className="w-3.5 h-3.5" />
            High Risk
          </span>
          <span className="text-2xl font-bold text-rose-700 mt-1 block">{highRiskCount}</span>
        </div>
      </div>

      {/* Filters & Search Toolbar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
        <div className="flex-1 relative">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            placeholder="Search exceptions by ID, employee, type, or detail..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full text-xs pl-9 pr-3 py-2 border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs text-slate-600 font-medium">
            <Filter className="w-3.5 h-3.5 text-slate-400" />
            <span>Status:</span>
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="text-xs bg-slate-50 border border-slate-200 rounded-md px-2 py-1.5 font-medium"
            >
              <option value="ALL">All Statuses</option>
              <option value="OPEN">Open</option>
              <option value="AWAITING_EMPLOYEE">Awaiting Employee</option>
              <option value="AWAITING_APPROVAL">Awaiting Approval</option>
              <option value="RESOLVED">Resolved</option>
              <option value="ESCALATED">Escalated</option>
            </select>
          </div>

          <div className="flex items-center gap-1.5 text-xs text-slate-600 font-medium ml-2">
            <span>Risk:</span>
            <select
              value={riskFilter}
              onChange={(e) => setRiskFilter(e.target.value)}
              className="text-xs bg-slate-50 border border-slate-200 rounded-md px-2 py-1.5 font-medium"
            >
              <option value="ALL">All Tiers</option>
              <option value="HIGH">High Risk</option>
              <option value="MEDIUM">Medium Risk</option>
              <option value="LOW">Low Risk</option>
            </select>
          </div>
        </div>
      </div>

      {/* Exceptions Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-24 text-center text-slate-500 text-xs flex flex-col items-center justify-center">
            <RefreshCw className="w-6 h-6 animate-spin text-indigo-600 mb-2" />
            <span>Loading exceptions from database...</span>
          </div>
        ) : filteredExceptions.length === 0 ? (
          <div className="py-20 text-center text-slate-500 text-xs">
            <AlertTriangle className="w-8 h-8 text-slate-300 mx-auto mb-2" />
            <span className="font-semibold text-slate-700 block text-sm">No exceptions found</span>
            <p className="text-slate-500 mt-1">Try clearing filters or click &ldquo;Scan Pay Period&rdquo; above.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[11px]">
                <tr>
                  <th className="py-3 px-4">Risk</th>
                  <th className="py-3 px-4">Exception Type</th>
                  <th className="py-3 px-4">Employee</th>
                  <th className="py-3 px-4">Work Date</th>
                  <th className="py-3 px-4">Finding Detail</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredExceptions.map((exc) => (
                  <tr
                    key={exc.id}
                    onClick={() => setSelectedExceptionId(exc.id)}
                    className="hover:bg-slate-50/80 cursor-pointer transition-colors group"
                  >
                    <td className="py-3.5 px-4 whitespace-nowrap">{getRiskBadge(exc.risk)}</td>
                    <td className="py-3.5 px-4 font-semibold text-slate-900 whitespace-nowrap">
                      <span className="font-mono text-xs">{exc.type}</span>
                    </td>
                    <td className="py-3.5 px-4 font-mono font-medium text-slate-700 whitespace-nowrap">
                      {exc.employee_id}
                    </td>
                    <td className="py-3.5 px-4 text-slate-600 whitespace-nowrap">{exc.work_date}</td>
                    <td className="py-3.5 px-4 text-slate-700 max-w-md truncate" title={exc.detail}>
                      {exc.detail}
                    </td>
                    <td className="py-3.5 px-4 whitespace-nowrap">{getStatusBadge(exc.status)}</td>
                    <td className="py-3.5 px-4 text-right whitespace-nowrap">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelectedExceptionId(exc.id);
                        }}
                        className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-600 hover:text-indigo-800 group-hover:translate-x-0.5 transition-all"
                      >
                        <span>Review</span>
                        <ChevronRight className="w-3.5 h-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {selectedExceptionId && (
        <ExceptionDetailModal
          exceptionId={selectedExceptionId}
          onClose={() => setSelectedExceptionId(null)}
          onUpdated={() => fetchExceptions()}
        />
      )}

      {/* Scan Pay Period Dialog */}
      {showScanModal && (
        <div className="fixed inset-0 bg-slate-900/50 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6 space-y-4">
            <h3 className="text-base font-bold text-slate-900">Scan Pay Period for Exceptions</h3>
            <p className="text-xs text-slate-600">
              Select date boundaries for the pay period to execute the deterministic rules engine across all employee timecards.
            </p>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[11px] font-semibold text-slate-600 block mb-1">Period Start</label>
                <input
                  type="date"
                  value={periodStart}
                  onChange={(e) => setPeriodStart(e.target.value)}
                  className="w-full text-xs p-2 border border-slate-300 rounded-lg font-mono"
                />
              </div>
              <div>
                <label className="text-[11px] font-semibold text-slate-600 block mb-1">Period End</label>
                <input
                  type="date"
                  value={periodEnd}
                  onChange={(e) => setPeriodEnd(e.target.value)}
                  className="w-full text-xs p-2 border border-slate-300 rounded-lg font-mono"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowScanModal(false)}
                className="px-3 py-1.5 text-xs font-semibold text-slate-600 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                onClick={handleScanPeriod}
                disabled={scanning}
                className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-400 text-white rounded-lg shadow-sm"
              >
                {scanning ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5 fill-current" />}
                Run Scan
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
