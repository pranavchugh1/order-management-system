'use client';
import { PageGate } from '@/components/WorkspaceShell';
import Pending from '@/features/Pending';
const App = () => <PageGate page="pending_requirements"><Pending/></PageGate>;
export default App;
