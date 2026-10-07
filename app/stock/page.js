'use client';
import { PageGate } from '@/components/WorkspaceShell';
import Stock from '@/features/Stock';
const App = () => <PageGate page="stock"><Stock/></PageGate>;
export default App;
