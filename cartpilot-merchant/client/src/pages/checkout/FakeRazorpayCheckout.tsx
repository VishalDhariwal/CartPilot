import React, { useEffect, useState, useRef } from 'react';
import { useLocation } from 'wouter';
import { CheckCircle2, ShieldCheck, Lock, ArrowRight, Copy, Check, ExternalLink, RefreshCw, AlertCircle } from 'lucide-react';
import { motion } from 'framer-motion';

const API_BASE = import.meta.env.VITE_API_URL || '';

export default function RazorpayCheckoutPage() {
  const [, setLocation] = useLocation();

  const queryParams = new URLSearchParams(window.location.search);
  const cartIdParam = queryParams.get('cart_id') || '';
  const orderIdParam = queryParams.get('order_id') || '';
  const rawAmount = queryParams.get('amount') || '149900';

  let parsedPaise = parseInt(rawAmount, 10);
  if (isNaN(parsedPaise) || parsedPaise <= 0) parsedPaise = 149900;
  if (parsedPaise < 500) parsedPaise = parsedPaise * 100;
  const amountRupees = (parsedPaise / 100).toFixed(2);

  const [step, setStep] = useState<'ready' | 'loading' | 'success' | 'failed'>('loading');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [paymentId, setPaymentId] = useState<string>('');
  const [resolvedOrderId, setResolvedOrderId] = useState<string>(orderIdParam);
  const [resolvedKeyId, setResolvedKeyId] = useState<string>('');
  const [copied, setCopied] = useState(false);

  const paymentCompletedRef = useRef(false);

  const broadcastSuccess = (pId: string, cId: string, oId: string) => {
    const payload = {
      cart_id: cId,
      order_id: oId,
      payment_id: pId,
      amount_rupees: amountRupees,
      amount_paise: parsedPaise,
      status: 'succeeded',
      timestamp: Date.now(),
    };

    try {
      const bc = new BroadcastChannel('cartpilot_payment_events');
      bc.postMessage(payload);
      setTimeout(() => bc.close(), 1000);
    } catch {}

    try {
      localStorage.setItem('cartpilot_payment_completed', JSON.stringify(payload));
    } catch {}
  };

  // Initialize or fetch order
  useEffect(() => {
    let isCancelled = false;

    const initOrder = async () => {
      try {
        // 1. Fetch checkout config (key_id)
        const cfgRes = await fetch(`${API_BASE}/api/checkout/config`);
        const cfg = await cfgRes.json();
        const keyId = cfg.key_id;
        if (!keyId) {
          throw new Error('Razorpay Key ID is not configured on backend.');
        }
        if (!isCancelled) setResolvedKeyId(keyId);

        let activeOrderId = orderIdParam;

        // 2. If no order_id provided, create one via backend
        if (!activeOrderId && cartIdParam) {
          const ordRes = await fetch(`${API_BASE}/api/checkout/create-order`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ cart_id: cartIdParam }),
          });
          const ordData = await ordRes.json();
          if (!ordRes.ok) {
            throw new Error(ordData.detail || 'Could not create Razorpay order');
          }
          activeOrderId = ordData.razorpay_order_id;
          if (!isCancelled) setResolvedOrderId(activeOrderId);
        }

        if (!isCancelled) {
          setStep('ready');
          // Auto-trigger Razorpay modal
          triggerRazorpayModal(keyId, activeOrderId);
        }
      } catch (err: any) {
        if (!isCancelled) {
          setErrorMessage(err.message || 'Failed to initialize payment');
          setStep('failed');
        }
      }
    };

    initOrder();

    return () => {
      isCancelled = true;
    };
  }, [cartIdParam, orderIdParam]);

  const triggerRazorpayModal = (keyId?: string, orderId?: string) => {
    const kId = keyId || resolvedKeyId;
    const oId = orderId || resolvedOrderId;

    if (!kId) return;

    if (!(window as any).Razorpay) {
      setErrorMessage('Razorpay SDK is not loaded. Please refresh.');
      setStep('failed');
      return;
    }

    const options = {
      key: kId,
      amount: parsedPaise,
      currency: 'INR',
      name: 'CartPilot Store',
      description: `Cart ${cartIdParam ? cartIdParam.slice(-8) : 'Order'} Checkout`,
      order_id: oId || undefined,
      handler: async function (response: any) {
        if (paymentCompletedRef.current) return;
        paymentCompletedRef.current = true;

        const pid = response.razorpay_payment_id;
        const oid = response.razorpay_order_id || oId;
        const sig = response.razorpay_signature;

        try {
          // Verify cryptographic signature with backend
          const verifyRes = await fetch(`${API_BASE}/api/checkout/verify`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              cart_id: cartIdParam,
              razorpay_order_id: oid,
              razorpay_payment_id: pid,
              razorpay_signature: sig,
            }),
          });
          const verifyData = await verifyRes.json();
          if (!verifyRes.ok) {
            throw new Error(verifyData.detail || 'Payment signature verification failed.');
          }

          setPaymentId(pid);
          setStep('success');
          broadcastSuccess(pid, cartIdParam, oid);
        } catch (vErr: any) {
          setErrorMessage(vErr.message || 'Signature verification failed.');
          setStep('failed');
        }
      },
      prefill: {
        name: 'Shopper',
        email: 'shopper@cartpilot.demo',
        contact: '9999999999',
      },
      theme: {
        color: '#2a9a71',
      },
      modal: {
        ondismiss: function () {
          // Keep screen ready so user can click to pay again
          if (step !== 'success') {
            setStep('ready');
          }
        },
      },
    };

    const rzp = new (window as any).Razorpay(options);
    rzp.on('payment.failed', function (resp: any) {
      setErrorMessage(resp.error?.description || 'Payment was declined by gateway.');
      setStep('failed');
    });
    rzp.open();
  };

  const copyPaymentId = () => {
    navigator.clipboard.writeText(paymentId);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#0e1726] to-[#080d17] text-white flex flex-col justify-between font-sans selection:bg-[#2a9a71]/30">
      {/* Top Header */}
      <header className="border-b border-white/10 bg-[#0e1726]/80 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-3xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-[#2a9a71] flex items-center justify-center font-bold text-white text-sm shadow-md shadow-[#2a9a71]/30">
              CP
            </div>
            <div>
              <div className="font-bold text-sm tracking-tight text-white flex items-center gap-1.5">
                CartPilot Checkout
                <span className="text-[10px] uppercase font-semibold tracking-wider px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-300 border border-blue-500/30">
                  Razorpay Live Rails
                </span>
              </div>
              <p className="text-[11px] text-gray-400">Cryptographically Verified Gateway</p>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs text-gray-300 bg-white/5 border border-white/10 px-3 py-1.5 rounded-full">
            <Lock size={12} className="text-emerald-400" />
            <span className="font-mono text-emerald-400 font-semibold">256-Bit SSL</span>
          </div>
        </div>
      </header>

      {/* Main Container */}
      <main className="flex-1 flex items-center justify-center p-6">
        <div className="w-full max-w-lg">
          {step === 'success' ? (
            /* Success State */
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="bg-[#141e30] border border-emerald-500/30 rounded-2xl p-8 shadow-2xl relative overflow-hidden"
            >
              <div className="absolute -top-24 -right-24 w-48 h-48 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none" />

              <div className="text-center">
                <div className="w-16 h-16 bg-emerald-500/20 text-emerald-400 rounded-full flex items-center justify-center mx-auto mb-4 border border-emerald-500/30">
                  <CheckCircle2 size={36} />
                </div>
                <h1 className="text-2xl font-bold text-white mb-2">Payment Confirmed!</h1>
                <p className="text-gray-300 text-sm mb-6">
                  ₹{amountRupees} captured via Razorpay. Your order is settled and recorded in the cryptographic audit ledger.
                </p>

                {/* Receipt Card */}
                <div className="bg-[#0b121e] rounded-xl p-4 border border-white/10 text-left space-y-2.5 mb-6 text-xs font-mono">
                  <div className="flex justify-between items-center text-gray-400 pb-2 border-b border-white/10">
                    <span>Razorpay Payment ID</span>
                    <div className="flex items-center gap-1.5">
                      <span className="text-emerald-300 font-bold">{paymentId}</span>
                      <button
                        onClick={copyPaymentId}
                        className="text-gray-400 hover:text-white transition-colors"
                        title="Copy Payment ID"
                      >
                        {copied ? <Check size={13} className="text-emerald-400" /> : <Copy size={13} />}
                      </button>
                    </div>
                  </div>

                  {resolvedOrderId && (
                    <div className="flex justify-between items-center text-gray-400">
                      <span>Razorpay Order ID</span>
                      <span className="text-gray-200">{resolvedOrderId}</span>
                    </div>
                  )}

                  {cartIdParam && (
                    <div className="flex justify-between items-center text-gray-400">
                      <span>Cart Mandate</span>
                      <span className="text-gray-200">{cartIdParam}</span>
                    </div>
                  )}

                  <div className="flex justify-between items-center text-gray-400 pt-2 border-t border-white/10">
                    <span className="font-semibold text-white">Amount Captured</span>
                    <span className="text-emerald-400 font-bold text-sm">₹{amountRupees}</span>
                  </div>
                </div>

                <div className="space-y-3">
                  <button
                    onClick={() => {
                      if (window.opener) {
                        window.close();
                      } else {
                        setLocation('/buyer');
                      }
                    }}
                    className="w-full py-3 px-4 bg-[#2a9a71] hover:bg-[#23805e] text-white font-bold rounded-xl text-sm transition-all shadow-lg flex items-center justify-center gap-2 cursor-pointer"
                  >
                    <span>Return to Store</span>
                    <ArrowRight size={16} />
                  </button>
                </div>
              </div>
            </motion.div>
          ) : step === 'failed' ? (
            /* Failed State */
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="bg-[#141e30] border border-rose-500/30 rounded-2xl p-8 shadow-2xl text-center"
            >
              <div className="w-16 h-16 bg-rose-500/20 text-rose-400 rounded-full flex items-center justify-center mx-auto mb-4 border border-rose-500/30">
                <AlertCircle size={36} />
              </div>
              <h1 className="text-2xl font-bold text-white mb-2">Payment Incomplete</h1>
              <p className="text-gray-300 text-sm mb-6">{errorMessage || 'The payment was not completed or was cancelled.'}</p>

              <div className="space-y-3">
                <button
                  onClick={() => {
                    setStep('ready');
                    triggerRazorpayModal();
                  }}
                  className="w-full py-3 px-4 bg-[#2a9a71] hover:bg-[#23805e] text-white font-bold rounded-xl text-sm transition-all shadow-lg flex items-center justify-center gap-2 cursor-pointer"
                >
                  <RefreshCw size={16} />
                  <span>Retry Payment</span>
                </button>
                <button
                  onClick={() => setLocation('/buyer')}
                  className="w-full py-2 text-xs text-gray-400 hover:text-white"
                >
                  Back to Buyer Store
                </button>
              </div>
            </motion.div>
          ) : (
            /* Ready / Loading State */
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              className="bg-[#141e30] border border-white/10 rounded-2xl p-8 shadow-2xl relative overflow-hidden"
            >
              <div className="text-center mb-6">
                <h1 className="text-xl font-bold text-white mb-1">Razorpay Secure Checkout</h1>
                <p className="text-xs text-gray-400">
                  CartPilot autonomous settlement rails powered by Razorpay
                </p>
              </div>

              <div className="bg-[#0b121e] rounded-xl p-5 border border-white/10 mb-6">
                <div className="flex justify-between items-center mb-3">
                  <span className="text-gray-400 text-xs">Total Amount</span>
                  <span className="text-2xl font-extrabold text-white">₹{amountRupees}</span>
                </div>
                {resolvedOrderId && (
                  <div className="flex justify-between items-center text-xs text-gray-400 pt-2 border-t border-white/10 font-mono">
                    <span>Order Reference</span>
                    <span className="text-gray-200">{resolvedOrderId}</span>
                  </div>
                )}
                {cartIdParam && (
                  <div className="flex justify-between items-center text-xs text-gray-400 pt-1 font-mono">
                    <span>Cart ID</span>
                    <span className="text-gray-300">{cartIdParam}</span>
                  </div>
                )}
              </div>

              <button
                onClick={() => triggerRazorpayModal()}
                disabled={step === 'loading'}
                className="w-full py-3.5 px-4 bg-[#2a9a71] hover:bg-[#23805e] disabled:opacity-50 text-white font-bold rounded-xl text-sm transition-all shadow-lg flex items-center justify-center gap-2 cursor-pointer"
              >
                {step === 'loading' ? (
                  <>
                    <RefreshCw size={16} className="animate-spin" />
                    <span>Connecting to Razorpay...</span>
                  </>
                ) : (
                  <>
                    <ExternalLink size={16} />
                    <span>Open Razorpay Checkout (₹{amountRupees})</span>
                  </>
                )}
              </button>

              <div className="mt-4 flex items-center justify-center gap-2 text-[11px] text-gray-400">
                <ShieldCheck size={13} className="text-emerald-400" />
                <span>HMAC-SHA256 Cryptographically Verified</span>
              </div>
            </motion.div>
          )}
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-white/10 py-4 px-6 text-center text-xs text-gray-400">
        CartPilot Commerce Engine · Connected to Razorpay Gateway Test Rails
      </footer>
    </div>
  );
}
