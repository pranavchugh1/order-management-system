'use client';
import { PageGate } from '@/components/WorkspaceShell';
import Bills from '@/features/Bills';
const App = () => <PageGate page="bills"><Bills/></PageGate>;
export default App;
