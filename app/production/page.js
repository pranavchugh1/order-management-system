'use client';
import { PageGate } from '@/components/WorkspaceShell';
import Production from '@/features/Production';
const App = () => <PageGate page="production"><Production/></PageGate>;
export default App;
