import { useState } from 'react';
import { useLocation } from 'wouter';
import { useAuth, UserRole } from '../contexts/AuthContext';
import { ShoppingBag, Store, ArrowRight, ShieldCheck, Zap, Lock, Mail, User, ShoppingCart } from 'lucide-react';
import { toast } from 'sonner';

export default function Auth() {
  const { login } = useAuth();
  const [, setLocation] = useLocation();

  const [selectedRole, setSelectedRole] = useState<UserRole>('buyer');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [storeName, setStoreName] = useState('Northstar Supply');
  const [merchantKey, setMerchantKey] = useState('');
  const [spendCap, setSpendCap] = useState('10000');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (selectedRole === 'merchant') {
      login('merchant', {
        name: name || 'Store Manager',
        email: email || 'merchant@cartpilot.io',
        storeName: storeName || 'Northstar Supply',
      });
      toast.success('Signed in to Merchant Control Room');
      setLocation('/merchant');
    } else {
      login('buyer', {
        name: name || 'Shopper',
        email: email || 'buyer@cartpilot.io',
        spendCapPaise: (parseInt(spendCap, 10) || 10000) * 100,
      });
      toast.success('Welcome to CartPilot Shopping!');
      setLocation('/buyer');
    }
  };

  const handleQuickDemo = (role: UserRole) => {
    if (role === 'merchant') {
      login('merchant', {
        name: 'Jamie Diaz',
        email: 'jamie@northstar.supply',
        storeName: 'Northstar Supply',
      });
      toast.success('Logged in as Merchant');
      setLocation('/merchant');
    } else {
      login('buyer', {
        name: 'Alex Rivera',
        email: 'alex@example.com',
        spendCapPaise: 1000000,
      });
      toast.success('Logged in as Buyer');
      setLocation('/buyer');
    }
  };

  return (
    <div className="min-h-screen flex flex-col justify-center items-center bg-[#f8f8fb] px-4 py-12">
      {/* Brand Header */}
      <div className="flex items-center gap-3 mb-8">
        <div className="logo-mark" style={{ background: "#115e59", color: "#ffffff", borderRadius: "9px" }}>
          <ShoppingCart size={18} strokeWidth={2.4} color="#ffffff" />
        </div>
        <span className="font-display text-2xl font-bold tracking-tight text-ink">
          cartpilot<span className="text-[#115e59]">.</span>
        </span>
      </div>

      <div className="w-full max-w-[520px] bg-white border border-[#ebeaf0] rounded-2xl shadow-xl p-8 sm:p-10">
        <div className="text-center mb-8">
          <div className="eyebrow text-violet mb-2">Role-Based Access Control</div>
          <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
            Sign in to CartPilot
          </h1>
          <p className="text-sm text-muted mt-2">
            Select your account type to access the customized autonomous interface.
          </p>
        </div>

        {/* Role Selector Tabs */}
        <div className="grid grid-cols-2 gap-3 p-1 bg-[#f4f3f8] rounded-xl mb-7">
          <button
            type="button"
            onClick={() => setSelectedRole('buyer')}
            className={`flex items-center justify-center gap-2 py-3 px-4 rounded-lg font-bold text-xs transition-all ${
              selectedRole === 'buyer'
                ? 'bg-white text-violet shadow-sm'
                : 'text-muted hover:text-ink'
            }`}
          >
            <ShoppingBag size={16} />
            <span>Buyer (Shopper)</span>
          </button>
          <button
            type="button"
            onClick={() => setSelectedRole('merchant')}
            className={`flex items-center justify-center gap-2 py-3 px-4 rounded-lg font-bold text-xs transition-all ${
              selectedRole === 'merchant'
                ? 'bg-white text-violet shadow-sm'
                : 'text-muted hover:text-ink'
            }`}
          >
            <Store size={16} />
            <span>Merchant (Store)</span>
          </button>
        </div>

        {/* Role Description Banner */}
        <div className={`p-4 rounded-xl mb-6 border text-xs flex items-start gap-3 ${
          selectedRole === 'merchant'
            ? 'bg-[#faf8ff] border-[#e7e0ff] text-[#5c42bc]'
            : 'bg-[#f0fbf6] border-[#d7f1e2] text-[#247e5d]'
        }`}>
          {selectedRole === 'merchant' ? (
            <>
              <ShieldCheck size={18} className="shrink-0 mt-0.5" />
              <div>
                <strong className="block font-bold mb-1">Merchant Intelligence Portal</strong>
                Manage AI merchandisers, inspect live environmental senses, execute pricing experiments, and configure policy guardrails.
              </div>
            </>
          ) : (
            <>
              <Zap size={18} className="shrink-0 mt-0.5" />
              <div>
                <strong className="block font-bold mb-1">Conversational AI Storefront</strong>
                Shop naturally via the LangGraph AI shopping associate, with live receipts, spend cap validation, and complementary recommendations.
              </div>
            </>
          )}
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs font-bold text-ink mb-1.5">Your Full Name</label>
            <div className="relative">
              <User size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
              <input
                type="text"
                placeholder={selectedRole === 'merchant' ? 'e.g. Jamie Diaz' : 'e.g. Alex Rivera'}
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full h-11 pl-10 pr-4 bg-[#fbfafc] border border-[#ebeaf0] rounded-lg text-sm text-ink outline-none focus:border-violet focus:ring-1 focus:ring-violet transition-all"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-bold text-ink mb-1.5">Email Address</label>
            <div className="relative">
              <Mail size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
              <input
                type="email"
                placeholder={selectedRole === 'merchant' ? 'merchant@store.com' : 'buyer@example.com'}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full h-11 pl-10 pr-4 bg-[#fbfafc] border border-[#ebeaf0] rounded-lg text-sm text-ink outline-none focus:border-violet focus:ring-1 focus:ring-violet transition-all"
              />
            </div>
          </div>

          {selectedRole === 'merchant' ? (
            <>
              <div>
                <label className="block text-xs font-bold text-ink mb-1.5">Store / Brand Name</label>
                <div className="relative">
                  <Store size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
                  <input
                    type="text"
                    placeholder="e.g. Northstar Supply"
                    value={storeName}
                    onChange={(e) => setStoreName(e.target.value)}
                    className="w-full h-11 pl-10 pr-4 bg-[#fbfafc] border border-[#ebeaf0] rounded-lg text-sm text-ink outline-none focus:border-violet focus:ring-1 focus:ring-violet transition-all"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-bold text-ink mb-1.5">
                  Merchant Access Key <span className="text-muted font-normal">(Optional for Demo)</span>
                </label>
                <div className="relative">
                  <Lock size={15} className="absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />
                  <input
                    type="password"
                    placeholder="Leave empty or enter CARTPILOT_KEY"
                    value={merchantKey}
                    onChange={(e) => setMerchantKey(e.target.value)}
                    className="w-full h-11 pl-10 pr-4 bg-[#fbfafc] border border-[#ebeaf0] rounded-lg text-sm text-ink outline-none focus:border-violet focus:ring-1 focus:ring-violet transition-all"
                  />
                </div>
              </div>
            </>
          ) : (
            <div>
              <label className="block text-xs font-bold text-ink mb-1.5">
                Initial Spend Cap (₹) <span className="text-muted font-normal">(Auto-approval Guardrail)</span>
              </label>
              <div className="relative">
                <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-sm font-bold text-muted">₹</span>
                <input
                  type="number"
                  placeholder="10000"
                  value={spendCap}
                  onChange={(e) => setSpendCap(e.target.value)}
                  className="w-full h-11 pl-10 pr-4 bg-[#fbfafc] border border-[#ebeaf0] rounded-lg text-sm text-ink outline-none focus:border-violet focus:ring-1 focus:ring-violet transition-all"
                />
              </div>
            </div>
          )}

          <button
            type="submit"
            className="w-full h-11 bg-violet text-white font-bold text-sm rounded-lg shadow-md hover:bg-[#6849d8] transition-all flex items-center justify-center gap-2 mt-6"
          >
            <span>Access {selectedRole === 'merchant' ? 'Merchant Dashboard' : 'Shopping Assistant'}</span>
            <ArrowRight size={16} />
          </button>
        </form>

        {/* Quick Demo Switches */}
        <div className="mt-8 pt-6 border-t border-[#ebeaf0] text-center">
          <div className="text-xs text-muted mb-3">Or continue with 1-click demo profiles:</div>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => handleQuickDemo('buyer')}
              className="flex-1 py-2 px-3 border border-[#ebeaf0] rounded-lg text-xs font-semibold text-ink hover:bg-[#faf9fd] transition-all"
            >
              Demo Buyer
            </button>
            <button
              type="button"
              onClick={() => handleQuickDemo('merchant')}
              className="flex-1 py-2 px-3 border border-[#ebeaf0] rounded-lg text-xs font-semibold text-ink hover:bg-[#faf9fd] transition-all"
            >
              Demo Merchant
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
