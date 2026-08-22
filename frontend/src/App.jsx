import { BrowserRouter, Routes, Route, Link, useLocation } from 'react-router-dom';
import { ShoppingCart, Activity } from 'lucide-react';
import Chat from './pages/Chat';
import Dashboard from './pages/Dashboard';

function Navbar() {
  const location = useLocation();

  return (
    <nav className="navbar">
      <Link to="/" className="navbar-brand">
        <div className="navbar-brand-icon">
          <ShoppingCart size={18} color="white" />
        </div>
        CartPilot
      </Link>
      <div className="nav-links">
        <Link to="/" className={location.pathname === '/' ? 'active' : ''}>
          Buyer Chat
        </Link>
        <Link to="/audit" className={location.pathname === '/audit' ? 'active' : ''}>
          <Activity size={14} style={{ display: 'inline', marginRight: 4, verticalAlign: 'middle' }} />
          Audit Trail
        </Link>
      </div>
    </nav>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <div className="container">
        <Routes>
          <Route path="/" element={<Chat />} />
          <Route path="/audit" element={<Dashboard />} />
        </Routes>
      </div>
    </BrowserRouter>
  );
}

export default App;
