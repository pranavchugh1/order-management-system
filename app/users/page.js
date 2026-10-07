'use client';
import { PageGate } from '@/components/WorkspaceShell';
import Users from '@/features/Users';
const App = () => <PageGate page="admin"><Users/></PageGate>;
export default App;
