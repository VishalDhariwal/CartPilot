import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Route, Switch, useLocation } from "wouter";
import ErrorBoundary from "./components/ErrorBoundary";
import { ThemeProvider } from "./contexts/ThemeContext";
import { AuthProvider, useAuth } from "./contexts/AuthContext";
import Auth from "./pages/Auth";
import BuyerApp from "./pages/buyer/BuyerApp";
import Home from "./pages/Home";
import FakeRazorpayCheckout from "./pages/checkout/FakeRazorpayCheckout";
import { useEffect } from "react";

function ProtectedRouter() {
  const { user, isAuthenticated } = useAuth();
  const [location, setLocation] = useLocation();

  useEffect(() => {
    const isPublicPaymentRoute = location.startsWith("/pay") || location.startsWith("/checkout/pay");
    if (!isAuthenticated && location !== "/auth" && !isPublicPaymentRoute) {
      setLocation("/auth");
    } else if (isAuthenticated && location === "/") {
      if (user?.role === "merchant") {
        setLocation("/merchant");
      } else {
        setLocation("/buyer");
      }
    }
  }, [isAuthenticated, location, user]);

  return (
    <Switch>
      <Route path="/auth" component={Auth} />
      <Route path="/buyer" component={BuyerApp} />
      <Route path="/merchant" component={Home} />
      <Route path="/merchant/*" component={Home} />
      <Route path="/pay" component={FakeRazorpayCheckout} />
      <Route path="/checkout/pay" component={FakeRazorpayCheckout} />
      <Route path="/" component={isAuthenticated ? (user?.role === "merchant" ? Home : BuyerApp) : Auth} />
      <Route path="*" component={isAuthenticated ? (user?.role === "merchant" ? Home : BuyerApp) : Auth} />
    </Switch>
  );
}

function App() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <ThemeProvider defaultTheme="light">
          <TooltipProvider>
            <Toaster />
            <ProtectedRouter />
          </TooltipProvider>
        </ThemeProvider>
      </AuthProvider>
    </ErrorBoundary>
  );
}

export default App;
