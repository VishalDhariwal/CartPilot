import React, { createContext, useContext, useState } from 'react';

export type UserRole = 'buyer' | 'merchant';

export interface UserProfile {
  role: UserRole;
  name: string;
  email: string;
  storeName?: string;
  spendCapPaise?: number;
}

interface AuthContextType {
  user: UserProfile | null;
  login: (role: UserRole, profile?: Partial<UserProfile>) => void;
  signup: (role: UserRole, profile?: Partial<UserProfile>) => void;
  logout: () => void;
  isAuthenticated: boolean;
}

const STORAGE_KEY = 'cartpilot_auth_user';

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const login = (role: UserRole, profile?: Partial<UserProfile>) => {
    const newUser: UserProfile = {
      role,
      name: profile?.name || (role === 'merchant' ? 'Jamie Diaz (Store Owner)' : 'Alex Rivera (Shopper)'),
      email: profile?.email || `${role === 'merchant' ? 'jamie@northstar.supply' : 'alex@example.com'}`,
      storeName: profile?.storeName || 'Northstar Supply',
      spendCapPaise: profile?.spendCapPaise || 1000000,
    };
    setUser(newUser);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(newUser));
  };

  const signup = (role: UserRole, profile?: Partial<UserProfile>) => {
    login(role, profile);
  };

  const logout = () => {
    setUser(null);
    localStorage.removeItem(STORAGE_KEY);
  };

  return (
    <AuthContext.Provider value={{ user, login, signup, logout, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  );
}


export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
