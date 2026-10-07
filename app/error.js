'use client';
const App = ({ reset }) => <div className="container py-16"><h1 className="text-xl font-semibold">This page couldn't load</h1><p className="mt-3 text-sm text-muted-foreground">Your saved records are safe. Try loading this page again.</p><button onClick={reset} className="mt-5 rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground">Try again</button></div>;
export default App;
