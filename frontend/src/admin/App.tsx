import { Approvals } from './pages/Approvals';
import { CaseDetail } from './pages/CaseDetail';
import { NavLink, Route, Routes } from 'react-router-dom';
import { Cases } from './pages/Cases';
import { Dashboard } from './pages/Dashboard';
import { Journey } from './pages/Journey';
import { Sessions } from './pages/Sessions';

export function App() {
  return (
    <div className="shell">
      <header className="topbar">
        <h1>智能服务观测台<span>ANKER · SMART CARE</span></h1>
        <nav className="nav">
          <NavLink to="/" end>经营面板</NavLink>
          <NavLink to="/sessions">会话</NavLink>
          <NavLink to="/approvals">售后审批</NavLink>
          <NavLink to="/cases">案例复盘</NavLink>
          <a href="/" title="回到客户端聊天">客户端 ↗</a>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/sessions/:id" element={<Journey />} />
          <Route path="/approvals" element={<Approvals />} />
          <Route path="/approvals/:id" element={<CaseDetail />} />
          <Route path="/cases" element={<Cases />} />
          <Route path="*" element={<p className="empty">没有这个页面。</p>} />
        </Routes>
      </main>
    </div>
  );
}
