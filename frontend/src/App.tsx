import React, { useState, useEffect } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import { Header, NavTab } from './components/Header';
import { Footer } from './components/Footer';
import { ExceptionQueueView } from './views/ExceptionQueueView';
import { EmployeeConfirmationView } from './views/EmployeeConfirmationView';
import { AuditTrailView } from './views/AuditTrailView';
import { ObservabilityView } from './views/ObservabilityView';
import { TryScenarioView } from './views/TryScenarioView';
import { api } from './api/client';

const AppContent: React.FC = () => {
  const params = new URLSearchParams(window.location.search);
  const initialTab = (params.get('tab') as NavTab) || 'exceptions';
  const initialException = params.get('exception') || null;

  const [activeTab, setActiveTab] = useState<NavTab>(initialTab);
  const [pendingConfirmationsCount, setPendingConfirmationsCount] = useState(0);
  const { currentUser } = useAuth();
  const isManagerRole = currentUser.role === 'MANAGER' || currentUser.role === 'HR';

  // Automatically switch tab away from Queue/Audit/Scenario if on non-manager role
  useEffect(() => {
    if (!isManagerRole && (activeTab === 'exceptions' || activeTab === 'audit' || activeTab === 'scenario')) {
      setActiveTab('confirmation');
    }
  }, [currentUser, isManagerRole, activeTab]);

  // Poll or check pending employee confirmations count
  useEffect(() => {
    let mounted = true;
    const checkConfirmations = async () => {
      try {
        if (currentUser.role === 'EMPLOYEE') {
          const list = await api.getEmployeeConfirmations(currentUser.id, {
            role: currentUser.role,
            employeeId: currentUser.id,
          });
          if (mounted) {
            setPendingConfirmationsCount(list.length);
          }
        } else {
          const list = await api.listExceptions(
            { status: 'AWAITING_EMPLOYEE' },
            { role: currentUser.role, employeeId: currentUser.id }
          );
          if (mounted) {
            setPendingConfirmationsCount(list.length);
          }
        }
      } catch {
        // quiet failure on initial count check
      }
    };
    checkConfirmations();
    const interval = setInterval(checkConfirmations, 15000);
    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [currentUser]);

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 text-slate-900">
      <Header
        activeTab={activeTab}
        onSelectTab={setActiveTab}
        pendingConfirmationsCount={pendingConfirmationsCount}
      />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {isManagerRole && activeTab === 'exceptions' && (
          <ExceptionQueueView initialSelectedId={initialException} />
        )}
        {isManagerRole && activeTab === 'scenario' && <TryScenarioView />}
        {activeTab === 'confirmation' && <EmployeeConfirmationView />}
        {isManagerRole && activeTab === 'audit' && <AuditTrailView />}
        {activeTab === 'observability' && <ObservabilityView />}
      </main>

      <Footer />
    </div>
  );
};

export const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
};

export default App;
