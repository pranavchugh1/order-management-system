'use client';
import { PageGate } from '@/components/WorkspaceShell';
import BulkOrders from '@/features/BulkOrders';
const App = () => <PageGate page="bulk"><BulkOrders/></PageGate>;
export default App;
