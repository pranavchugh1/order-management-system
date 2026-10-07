'use client';
import { PageGate } from '@/components/WorkspaceShell';
import OrderDetails from '@/features/OrderDetails';
const App = () => <PageGate orders><OrderDetails/></PageGate>;
export default App;
