'use client';
import { PageGate } from '@/components/WorkspaceShell';
import Orders from '@/features/Orders';
const App = () => <PageGate page="orders_completed"><Orders status="completed"/></PageGate>;
export default App;
