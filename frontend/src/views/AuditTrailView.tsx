import React, { useState, useEffect } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  Database,
  RefreshCw,
  Search,
  ChevronDown,
  ChevronUp,
  Hash,
} from 'lucide-react';
import type { AuditEntry, AuditVerifyResult } from '../types';
import { api, ApiError } from '../api/client';
import { useAuth } from '../context/AuthContext';

export const AuditTrailView: React.FC = () => {
  const { currentUser } = useAuth();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [verifyResult, setVerifyResult] = useState<AuditVerifyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedSeq, setExpandedSeq] = useState<number | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  const loadAuditData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [entriesData, verifyData] = await Promise.all([
        api.getAudit(100, { role: currentUser.role, employeeId: currentUser.id }),
        api.verifyAudit({ role: currentUser.role, employeeId: currentUser.id }),
      ]);
      setEntries(entriesData);
      setVerifyResult(verifyData);
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        setError(`[${err.code}] ${err.message}`);
      } else {
        setError('Failed to load audit trail');
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAuditData();
  }, [currentUser]);

  const toggleExpand = (seq: number) => {
    setExpandedSeq((prev) => (prev === seq ? null : seq));
  };

  const filteredEntries = entries.filter((e) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      e.action.toLowerCase().includes(term) ||
      e.actor.toLowerCase().includes(term) ||
      e.entity_id.toLowerCase().includes(term) ||
      e.hash.toLowerCase().includes(term)
    );
  });

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <Database className="w-5 h-5 text-indigo-600" />
            <h1 className="text-xl font-bold text-slate-900 tracking-tight">Cryptographic Audit Trail</h1>
          </div>
          <p className="text-xs text-slate-500">
            Append-only tamper-evident audit ledger chained with SHA-256 hashes. Every scan, resolution, confirmation, and approval is logged.
          </p>
        </div>

        <button
          onClick={loadAuditData}
          disabled={loading}
          className="inline-flex items-center gap-2 px-3 py-2 border border-slate-200 hover:bg-slate-50 text-slate-700 rounded-lg text-xs font-medium transition-colors"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-indigo-600' : ''}`} />
          Verify &amp; Refresh
        </button>
      </div>

      {error && (
        <div className="p-3 bg-rose-50 border border-rose-200 rounded-lg text-rose-800 text-xs">
          {error}
        </div>
      )}

      {/* Cryptographic Chain Status Banner */}
      {verifyResult && (
        <div
          className={`p-4 rounded-xl border flex items-center justify-between shadow-sm ${
            verifyResult.valid
              ? 'bg-emerald-50/80 border-emerald-300 text-emerald-950'
              : 'bg-rose-50 border-rose-300 text-rose-950'
          }`}
        >
          <div className="flex items-center gap-3">
            {verifyResult.valid ? (
              <div className="w-10 h-10 rounded-lg bg-emerald-600 text-white flex items-center justify-center shrink-0 shadow">
                <ShieldCheck className="w-6 h-6" />
              </div>
            ) : (
              <div className="w-10 h-10 rounded-lg bg-rose-600 text-white flex items-center justify-center shrink-0 shadow">
                <ShieldAlert className="w-6 h-6" />
              </div>
            )}
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-sm tracking-tight">
                  {verifyResult.valid
                    ? 'Audit Hash Chain Cryptographically Verified'
                    : 'Audit Hash Chain Integrity Compromised!'}
                </h3>
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase tracking-wider ${
                    verifyResult.valid ? 'bg-emerald-200 text-emerald-900' : 'bg-rose-200 text-rose-900'
                  }`}
                >
                  {verifyResult.valid ? 'INTEGRITY OK' : 'TAMPER DETECTED'}
                </span>
              </div>
              <p className="text-xs text-slate-600 mt-0.5">
                {verifyResult.valid
                  ? `All ${verifyResult.entries_checked} sequential records verified against SHA-256 parent hash hashes.`
                  : `Chain verification failed at sequence #${verifyResult.first_bad_seq}. Ledger tampering detected!`}
              </p>
            </div>
          </div>

          <div className="hidden sm:block text-right">
            <span className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 block">
              Checked Entries
            </span>
            <span className="font-mono font-bold text-slate-900 text-base">
              {verifyResult.entries_checked}
            </span>
          </div>
        </div>
      )}

      {/* Search Toolbar */}
      <div className="bg-white p-3 rounded-xl border border-slate-200 shadow-sm flex items-center gap-2">
        <Search className="w-4 h-4 text-slate-400 ml-2" />
        <input
          type="text"
          placeholder="Filter audit log by action, actor, entity ID, or hash..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full text-xs py-1.5 focus:outline-none"
        />
      </div>

      {/* Audit Log Entries Table */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="py-20 text-center text-slate-500 text-xs flex flex-col items-center">
            <RefreshCw className="w-6 h-6 animate-spin text-indigo-600 mb-2" />
            Verifying cryptographic ledger...
          </div>
        ) : filteredEntries.length === 0 ? (
          <div className="py-16 text-center text-slate-500 text-xs">
            No audit records found matching criteria.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[11px]">
                <tr>
                  <th className="py-3 px-4 w-16">Seq</th>
                  <th className="py-3 px-4">Timestamp</th>
                  <th className="py-3 px-4">Action</th>
                  <th className="py-3 px-4">Actor</th>
                  <th className="py-3 px-4">Entity</th>
                  <th className="py-3 px-4">SHA-256 Hash</th>
                  <th className="py-3 px-4 text-right">Payload</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-sans">
                {filteredEntries.map((entry) => {
                  const isExpanded = expandedSeq === entry.seq;
                  return (
                    <React.Fragment key={entry.seq}>
                      <tr
                        onClick={() => toggleExpand(entry.seq)}
                        className={`hover:bg-slate-50/80 cursor-pointer transition-colors ${
                          isExpanded ? 'bg-indigo-50/40' : ''
                        }`}
                      >
                        <td className="py-3 px-4 font-mono font-bold text-slate-500">#{entry.seq}</td>
                        <td className="py-3 px-4 text-slate-600 whitespace-nowrap font-mono text-[11px]">
                          {entry.at.replace('T', ' ').slice(0, 19)}
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-800 border border-slate-200">
                            {entry.action}
                          </span>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span className="font-semibold text-slate-900 block">{entry.actor}</span>
                          <span className="text-[10px] text-slate-500 uppercase font-mono font-semibold">
                            {entry.role}
                          </span>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap font-mono text-slate-700">
                          <span className="text-slate-400 text-[10px] block uppercase">{entry.entity_type}</span>
                          <span className="text-xs font-medium">{entry.entity_id}</span>
                        </td>
                        <td className="py-3 px-4 whitespace-nowrap font-mono text-[11px] text-slate-600">
                          <div className="flex items-center gap-1" title={entry.hash}>
                            <Hash className="w-3 h-3 text-slate-400" />
                            <span>{entry.hash.slice(0, 14)}...</span>
                          </div>
                        </td>
                        <td className="py-3 px-4 text-right whitespace-nowrap">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpand(entry.seq);
                            }}
                            className="p-1 rounded text-slate-400 hover:text-indigo-600 transition-colors"
                            aria-label="Toggle details"
                          >
                            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                          </button>
                        </td>
                      </tr>

                      {/* Expanded Payload Viewer */}
                      {isExpanded && (
                        <tr className="bg-slate-900 text-slate-100">
                          <td colSpan={7} className="p-4 font-mono text-[11px] space-y-2">
                            <div className="flex flex-wrap items-center justify-between gap-2 pb-2 border-b border-slate-800 text-slate-400">
                              <div>
                                <span>Record Hash: </span>
                                <span className="text-emerald-400 font-bold">{entry.hash}</span>
                              </div>
                              <div>
                                <span>Prev Hash: </span>
                                <span className="text-indigo-400">{entry.prev_hash}</span>
                              </div>
                            </div>
                            <div>
                              <span className="text-slate-400 block mb-1">Payload:</span>
                              <pre className="bg-slate-950 p-3 rounded-lg overflow-x-auto text-emerald-300 border border-slate-800">
                                {JSON.stringify(entry.payload, null, 2)}
                              </pre>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
