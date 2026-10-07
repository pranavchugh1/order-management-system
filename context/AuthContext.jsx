"use client";

import { createContext, useContext, useEffect, useState } from 'react';
import { api } from '@/lib/api';
const AuthContext = createContext(null);
export function AuthProvider({
  children
}) {
  const [user, setUser] = useState(null);
  const [checking, setChecking] = useState(true);
  useEffect(() => {
    api.get('/auth/me').then(r => setUser(r.data)).catch(() => setUser(null)).finally(() => setChecking(false));
    const expired = () => setUser(null);
    window.addEventListener('session-ended', expired);
    return () => window.removeEventListener('session-ended', expired);
  }, []);
  const login = async (email, password) => {
    const r = await api.post('/auth/login', {
      email,
      password
    });
    setUser(r.data);
  };
  const logout = async () => {
    await api.post('/auth/logout');
    sessionStorage.removeItem(`bulk-draft-${user?.id}`);
    setUser(null);
  };
  return <AuthContext.Provider value={{
    user,
    checking,
    login,
    logout
  }}>{children}</AuthContext.Provider>;
}
export const useAuth = () => useContext(AuthContext);
