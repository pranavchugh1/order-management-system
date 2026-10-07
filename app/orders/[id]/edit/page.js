'use client';
import { PageGate } from '@/components/WorkspaceShell';
import OrderForm from '@/features/OrderForm';
const App = () => <PageGate orders><OrderForm existing/></PageGate>;
export default App;
