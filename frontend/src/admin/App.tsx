/** 观测台按使用者分入口：坐席工作台 / 运营看板 / 研发诊断；会话与案件详情是共享页面。 */
import { Navigate, NavLink, Route, Routes } from 'react-router-dom';
import { Board } from './pages/Board';
import { CaseDetail } from './pages/CaseDetail';
import { Desk } from './pages/Desk';
import { Journey } from './pages/Journey';
import { Lab } from './pages/Lab';
import { Sessions } from './pages/Sessions';

export function App() {
  return (
    <div className="shell">
      <header className="topbar">
        <h1>智能服务观测台<span>ANKER · SMART CARE</span></h1>
        <nav className="nav">
          <NavLink to="/desk">工作台</NavLink>
          <NavLink to="/board">看板</NavLink>
          <NavLink to="/sessions">会话</NavLink>
          <NavLink to="/lab">诊断</NavLink>
          <a href="/" title="回到客户端聊天">客户端 ↗</a>
        </nav>
      </header>
      <main>
        <Routes>
          <Route path="/" element={<Navigate to="/desk" replace />} />
          <Route path="/desk" element={<Desk />} />
          <Route path="/desk/:id" element={<CaseDetail />} />
          <Route path="/board" element={<Board />} />
          <Route path="/sessions" element={<Sessions />} />
          <Route path="/sessions/:id" element={<Journey />} />
          <Route path="/lab" element={<Lab />} />
          <Route path="*" element={<p className="empty">没有这个页面。</p>} />
        </Routes>
      </main>
    </div>
  );
}
