'use client';
import { PageGate } from '@/components/WorkspaceShell';
import MasterManager from '@/components/MasterManager';
const App = () => <PageGate page="parties"><MasterManager type="parties"/></PageGate>;
export default App;
