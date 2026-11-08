import React, { createContext, useContext, useState, useEffect } from 'react';
import type { Role } from '../types';

export interface AuthUser {
  id: string;
  name: string;
  role: Role;
  title: string;
}

export const DEMO_USERS: AuthUser[] = [
  { id: 'm01', name: 'Mary Manager', role: 'MANAGER', title: 'Shift Operations Manager' },
  { id: 'hr01', name: 'Helen HR', role: 'HR', title: 'HR Compliance Officer' },
  { id: 'e01', name: 'Alice Employee', role: 'EMPLOYEE', title: 'Operations Associate (CA)' },
  { id: 'e02', name: 'Bob Worker', role: 'EMPLOYEE', title: 'Senior Associate (CA)' },
  { id: 'e03', name: 'Charlie Staff', role: 'EMPLOYEE', title: 'Specialist (CA)' },
  { id: 'e04', name: 'David Contractor', role: 'EMPLOYEE', title: 'External Tech (XX)' },
  { id: 'e05', name: 'Emma Shift', role: 'EMPLOYEE', title: 'Logistics Associate (CA)' },
];

interface AuthContextValue {
  currentUser: AuthUser;
  setCurrentUser: (user: AuthUser) => void;
  setUserById: (id: string) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [currentUser, setCurrentUser] = useState<AuthUser>(() => {
    const params = new URLSearchParams(window.location.search);
    const userParam = params.get('user');
    const roleParam = params.get('role');

    if (userParam) {
      const found = DEMO_USERS.find((u) => u.id === userParam);
      if (found) return found;
    }
    if (roleParam) {
      const found = DEMO_USERS.find((u) => u.role === roleParam.toUpperCase());
      if (found) return found;
    }

    const saved = localStorage.getItem('timeguard_user_id');
    const found = DEMO_USERS.find((u) => u.id === saved);
    return found || DEMO_USERS[0]; // default Mary Manager
  });

  const setUserById = (id: string) => {
    const found = DEMO_USERS.find((u) => u.id === id);
    if (found) {
      setCurrentUser(found);
      localStorage.setItem('timeguard_user_id', found.id);
    }
  };

  useEffect(() => {
    localStorage.setItem('timeguard_user_id', currentUser.id);
  }, [currentUser]);

  return (
    <AuthContext.Provider value={{ currentUser, setCurrentUser, setUserById }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return ctx;
};
