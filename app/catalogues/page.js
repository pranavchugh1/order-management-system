'use client';
import { PageGate } from '@/components/WorkspaceShell';
import MasterManager from '@/components/MasterManager';
const App = () => <PageGate page="catalogues"><MasterManager type="catalogues"/></PageGate>;
export default App;
