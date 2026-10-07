'use client';
import { PageGate } from '@/components/WorkspaceShell';
import OrderForm from '@/features/OrderForm';
const App = () => <PageGate orders><OrderForm/></PageGate>;
export default App;
