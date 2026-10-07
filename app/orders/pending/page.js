'use client';
import { PageGate } from '@/components/WorkspaceShell';
import Orders from '@/features/Orders';
const App = () => <PageGate page="orders_pending"><Orders status="pending"/></PageGate>;
export default App;
