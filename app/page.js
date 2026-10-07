'use client';
import Orders from '@/features/Orders';
import { PageGate } from '@/components/WorkspaceShell';
const App = () => <PageGate page="orders_all"><Orders /></PageGate>;
export default App;
