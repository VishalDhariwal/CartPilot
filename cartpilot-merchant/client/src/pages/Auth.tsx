import React, { useState } from 'react';
import { useLocation } from 'wouter';
import { useAuth } from '../contexts/AuthContext';
import { ShoppingCart, ShoppingBag, Store, ArrowRight, User } from 'lucide-react';
import { toast } from 'sonner';

export default function Auth() {
  const { login } = useAuth();
  const [, setLocation] = useLocation();
  const [name, setName] = useState('');

  const handleLogin = (role: 'buyer' | 'merchant') => {
    const trimmedName = name.trim();
    const profile = {
      name: trimmedName || (role === 'merchant' ? 'Jamie Diaz' : 'Alex Rivera'),
      email: role === 'merchant' ? 'merchant@cartpilot.io' : 'buyer@cartpilot.io',
      storeName: 'Northstar Supply',
      spendCapPaise: 1000000,
    };

    login(role, profile);
    toast.success(`Logged in as ${profile.name}`);
    if (role === 'merchant') {
      setLocation('/merchant');
    } else {
      setLocation('/buyer');
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-center items-center bg-[#f8f8fb] px-4">
      {/* Brand Header */}
      <div className="flex items-center gap-2.5 mb-6">
        <div className="w-10 h-10 rounded-xl bg-[#115e59] flex items-center justify-center text-white shadow-md shadow-[#115e59]/20">
          <ShoppingCart size={20} strokeWidth={2.4} />
        </div>
        <span className="font-display text-2xl font-bold tracking-tight text-ink">
          CartPilot<span className="text-[#115e59]">.</span>
        </span>
      </div>

      <div className="w-full max-w-sm bg-white border border-[#ebeaf0] rounded-2xl shadow-lg p-6 sm:p-8">
        <div className="mb-6">
          <label className="block text-xs font-bold text-ink mb-2">Your Name</label>
          <div className="relative">
            <User size={16} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
            <input
              type="text"
              placeholder="Enter your name (optional)"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full h-11 pl-10 pr-4 bg-[#fbfafc] border border-[#ebeaf0] rounded-xl text-sm text-ink outline-none focus:border-[#115e59] focus:ring-1 focus:ring-[#115e59] transition-all"
            />
          </div>
        </div>

        <div className="space-y-3">
          <button
            type="button"
            onClick={() => handleLogin('buyer')}
            className="w-full h-12 bg-[#115e59] hover:bg-[#0e4f4b] text-white font-bold text-sm rounded-xl shadow-md transition-all flex items-center justify-between px-4 cursor-pointer"
          >
            <div className="flex items-center gap-2.5">
              <ShoppingBag size={18} />
              <span>Login as Buyer</span>
            </div>
            <ArrowRight size={16} />
          </button>

          <button
            type="button"
            onClick={() => handleLogin('merchant')}
            className="w-full h-12 bg-[#6366f1] hover:bg-[#4f46e5] text-white font-bold text-sm rounded-xl shadow-md transition-all flex items-center justify-between px-4 cursor-pointer"
          >
            <div className="flex items-center gap-2.5">
              <Store size={18} />
              <span>Login as Merchant</span>
            </div>
            <ArrowRight size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
