import React from 'react';
import { Shield, Clock, UserCheck, Activity, Database, ChevronDown, FlaskConical } from 'lucide-react';
import { useAuth, DEMO_USERS } from '../context/AuthContext';

export type NavTab = 'exceptions' | 'scenario' | 'confirmation' | 'audit' | 'observability';

interface HeaderProps {
  activeTab: NavTab;
  onSelectTab: (tab: NavTab) => void;
  pendingConfirmationsCount?: number;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  onSelectTab,
  pendingConfirmationsCount = 0,
}) => {
  const { currentUser, setUserById } = useAuth();

  const isManagerRole = currentUser.role === 'MANAGER' || currentUser.role === 'HR';

  const getRoleBadgeClass = (role: string) => {
    switch (role) {
      case 'HR':
        return 'bg-purple-100 text-purple-800 border-purple-300';
      case 'MANAGER':
        return 'bg-blue-100 text-blue-800 border-blue-300';
      case 'EMPLOYEE':
        return 'bg-emerald-100 text-emerald-800 border-emerald-300';
      default:
        return 'bg-slate-100 text-slate-800 border-slate-300';
    }
  };

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-30 shadow-sm">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Brand */}
          <div className="flex items-center gap-8">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white shadow">
                <Shield className="w-5 h-5" />
              </div>
              <div>
                <span className="font-bold text-lg text-slate-900 tracking-tight">TimeGuard</span>
                <span className="text-xs text-indigo-600 block -mt-1 font-medium tracking-wide uppercase">Console</span>
              </div>
            </div>

            {/* Nav Tabs */}
            <nav className="hidden md:flex space-x-1" aria-label="Main Navigation">
              {isManagerRole && (
                <button
                  onClick={() => onSelectTab('exceptions')}
                  className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    activeTab === 'exceptions'
                      ? 'bg-slate-100 text-indigo-700'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
                >
                  <Clock className="w-4 h-4" />
                  Exceptions Queue
                </button>
              )}

              {isManagerRole && (
                <button
                  onClick={() => onSelectTab('scenario')}
                  className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    activeTab === 'scenario'
                      ? 'bg-slate-100 text-indigo-700'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
                >
                  <FlaskConical className="w-4 h-4" />
                  Try Your Own Scenario
                </button>
              )}

              <button
                onClick={() => onSelectTab('confirmation')}
                className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors relative ${
                  activeTab === 'confirmation'
                    ? 'bg-slate-100 text-indigo-700'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                }`}
              >
                <UserCheck className="w-4 h-4" />
                Employee Confirmation
                {pendingConfirmationsCount > 0 && (
                  <span className="ml-1.5 px-2 py-0.5 text-xs font-semibold rounded-full bg-amber-100 text-amber-800 border border-amber-300">
                    {pendingConfirmationsCount}
                  </span>
                )}
              </button>

              {isManagerRole && (
                <button
                  onClick={() => onSelectTab('audit')}
                  className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                    activeTab === 'audit'
                      ? 'bg-slate-100 text-indigo-700'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
                >
                  <Database className="w-4 h-4" />
                  Audit Trail
                </button>
              )}

              <button
                onClick={() => onSelectTab('observability')}
                className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'observability'
                    ? 'bg-slate-100 text-indigo-700'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                }`}
              >
                <Activity className="w-4 h-4" />
                Observability
              </button>
            </nav>
          </div>

          {/* Role Switcher */}
          <div className="flex items-center gap-3">
            <div className="flex items-center bg-slate-50 border border-slate-200 rounded-lg p-1.5 shadow-sm">
              <span className="text-xs font-medium text-slate-500 px-2 hidden sm:inline">Active Role:</span>
              <div className="relative">
                <select
                  value={currentUser.id}
                  onChange={(e) => setUserById(e.target.value)}
                  className="appearance-none bg-white border border-slate-300 text-slate-900 text-xs font-medium rounded-md pl-2.5 pr-8 py-1.5 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 cursor-pointer shadow-sm"
                  aria-label="Switch User and Role"
                >
                  {DEMO_USERS.map((user) => (
                    <option key={user.id} value={user.id}>
                      [{user.role}] {user.name} ({user.id})
                    </option>
                  ))}
                </select>
                <ChevronDown className="w-3.5 h-3.5 text-slate-500 absolute right-2 top-2.5 pointer-events-none" />
              </div>

              <span
                className={`ml-2 px-2 py-0.5 rounded text-[11px] font-semibold uppercase tracking-wider border ${getRoleBadgeClass(
                  currentUser.role
                )}`}
              >
                {currentUser.role}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Mobile navigation row */}
      <div className="md:hidden flex border-t border-slate-100 overflow-x-auto py-1 px-4 gap-1">
        {isManagerRole && (
          <button
            onClick={() => onSelectTab('exceptions')}
            className={`px-3 py-1.5 rounded text-xs font-medium whitespace-nowrap ${
              activeTab === 'exceptions' ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600'
            }`}
          >
            Exceptions
          </button>
        )}
        <button
          onClick={() => onSelectTab('confirmation')}
          className={`px-3 py-1.5 rounded text-xs font-medium whitespace-nowrap ${
            activeTab === 'confirmation' ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600'
          }`}
        >
          Confirmation ({pendingConfirmationsCount})
        </button>
        {isManagerRole && (
          <button
            onClick={() => onSelectTab('audit')}
            className={`px-3 py-1.5 rounded text-xs font-medium whitespace-nowrap ${
              activeTab === 'audit' ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600'
            }`}
          >
            Audit Trail
          </button>
        )}
        <button
          onClick={() => onSelectTab('observability')}
          className={`px-3 py-1.5 rounded text-xs font-medium whitespace-nowrap ${
            activeTab === 'observability' ? 'bg-indigo-50 text-indigo-700' : 'text-slate-600'
          }`}
        >
          Observability
        </button>
      </div>
    </header>
  );
};
