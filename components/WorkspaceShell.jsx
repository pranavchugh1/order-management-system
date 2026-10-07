'use client';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { ClipboardList, Clock3, CheckCheck, ListPlus, ChartNoAxesCombined, Truck, Package, Factory, BookOpen, Users, ShieldCheck, ReceiptText, LogOut, Menu, X, ChevronRight, ChevronsUpDown, Layers3, CircleHelp } from 'lucide-react';
import { useAuth } from '@/context/AuthContext';
import { canAccess, canAccessAny, firstAccessiblePath, ORDER_PAGE_IDS } from '@/lib/access';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { errorText } from '@/lib/api';
const groups = [
  { title: 'WORKSPACE', items: [['/', 'All orders', ClipboardList, 'orders_all'], ['/orders/pending', 'Pending orders', Clock3, 'orders_pending'], ['/orders/completed', 'Completed orders', CheckCheck, 'orders_completed'], ['/bulk', 'Bulk entry', ListPlus, 'bulk'], ['/pending', 'Requirements', ChartNoAxesCombined, 'pending_requirements'], ['/challans', 'Challans', Truck, 'challans']] },
  { title: 'FACTORY', items: [['/stock', 'Stock inventory', Package, 'stock'], ['/production', 'Production', Factory, 'production'], ['/bills', 'Bills & cash', ReceiptText, 'bills']] },
  { title: 'MANAGEMENT', items: [['/catalogues', 'Catalogues', BookOpen, 'catalogues'], ['/parties', 'Parties', Users, 'parties'], ['/users', 'Team access', ShieldCheck, 'admin']] },
];
export const PageGate = ({ page, orders, children }) => {
  const { user } = useAuth();
  const allowed = orders ? canAccessAny(user, ORDER_PAGE_IDS) : page === 'admin' ? user?.role === 'admin' : canAccess(user, page);
  if (!allowed) return <div className="container py-16"><ShieldCheck className="mb-4 text-muted-foreground"/><h1 className="text-xl font-semibold">This page isn't assigned to you</h1><p className="mt-2 text-sm text-muted-foreground">Ask your administrator to update your page access.</p><Link href={firstAccessiblePath(user)} className="mt-6 inline-block text-sm text-primary">Back to your workspace</Link></div>;
  return children;
};
export const WorkspaceShell = ({ children }) => {
  const { user, checking, logout } = useAuth();
  const pathname = usePathname(), router = useRouter();
  const [open, setOpen] = useState(false), [busy, setBusy] = useState(false);
  useEffect(() => { if (!checking && !user && pathname !== '/login') router.replace('/login'); if (!checking && user && pathname === '/login') router.replace(firstAccessiblePath(user)); }, [checking, user, pathname, router]);
  useEffect(() => setOpen(false), [pathname]);
  if (pathname === '/login') return children;
  if (checking || !user) return <div className="flex min-h-screen items-center justify-center gap-3 bg-background text-sm text-muted-foreground"><Layers3 size={20} className="animate-pulse text-primary"/>Opening your workspace…</div>;
  const label = groups.flatMap(g => g.items).find(i => i[0] === pathname)?.[1] || 'Order details';
  const signOut = async () => { setBusy(true); try { await logout(); } catch (e) { toast.error(errorText(e)); } finally { setBusy(false); } };
  return <div className="min-h-screen bg-background text-foreground">
    {open && <button aria-label="Close navigation" className="fixed inset-0 z-30 bg-foreground/30 lg:hidden" onClick={() => setOpen(false)}/>}
    <aside className={`fixed inset-y-0 left-0 z-40 flex w-[236px] flex-col border-r border-border bg-sidebar transition-transform lg:translate-x-0 ${open ? 'translate-x-0' : '-translate-x-full'}`}>
      <Link href={firstAccessiblePath(user)} className="flex h-[82px] items-center gap-3 px-6"><span className="flex size-10 items-center justify-center rounded-xl bg-primary text-primary-foreground"><Layers3 size={23}/></span><span><strong className="block text-[17px] font-semibold tracking-tight">aditya prints<span className="text-primary">.</span></strong><span className="mt-0.5 block text-[9px] font-semibold tracking-[0.21em] text-muted-foreground">FACTORY WORKSPACE</span></span></Link>
      <div className="mx-4 mb-3 flex items-center gap-2 rounded-lg border border-border bg-card/60 p-3"><span className="flex size-7 items-center justify-center rounded-md bg-secondary text-primary"><Factory size={15}/></span><span className="flex-1 text-xs font-medium">Main workspace<small className="block text-[10px] font-normal text-muted-foreground">Aditya Prints</small></span><ChevronsUpDown size={13} className="text-muted-foreground"/></div>
      <nav className="flex-1 overflow-y-auto px-3 py-1">{groups.map(g => { const items = g.items.filter(i => i[3] === 'admin' ? user?.role === 'admin' : canAccess(user, i[3])); return items.length ? <div key={g.title} className="mb-4"><p className="px-3 pb-2 pt-2 text-[9px] font-semibold tracking-[0.15em] text-muted-foreground/75">{g.title}</p>{items.map(([href, title, Icon]) => <Link key={href} href={href} data-testid={`nav-${title.toLowerCase().replaceAll(' ', '-')}`} aria-current={pathname === href ? 'page' : undefined} className={`my-0.5 flex items-center gap-3 rounded-lg px-3 py-2.5 text-[12px] font-medium transition-colors ${pathname === href ? 'bg-secondary text-primary' : 'text-muted-foreground hover:bg-muted hover:text-foreground'}`}><Icon size={17} strokeWidth={1.7}/><span className="flex-1">{title}</span>{pathname === href && <span className="size-1.5 rounded-full bg-primary"/>}</Link>)}</div> : null; })}</nav>
      <div className="m-4 rounded-lg border border-border p-3"><div className="flex items-center gap-2 text-[11px] font-medium"><span className="size-1.5 rounded-full bg-emerald-500"/>One workspace. Every detail.</div><p className="mt-1.5 text-[10px] leading-relaxed text-muted-foreground">From the first order to the final balance.</p></div>
      <div className="flex items-center gap-2.5 border-t px-4 py-4"><span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-secondary text-xs font-semibold text-primary">{user?.name?.slice(0, 2).toUpperCase()}</span><div className="min-w-0 flex-1"><p className="truncate text-xs font-semibold" data-testid="signed-in-user">{user?.name}</p><p className="text-[10px] capitalize text-muted-foreground">{user?.role === 'admin' ? 'Administrator' : 'Team member'}</p></div><button title="Sign out" aria-label="Sign out" disabled={busy} onClick={signOut} data-testid="logout-button" className="rounded-md p-2 text-muted-foreground hover:bg-muted"><LogOut size={16}/></button></div>
    </aside>
    <main className="min-w-0 lg:ml-[236px]"><header className="flex h-[65px] items-center justify-between gap-4 border-b border-border bg-card px-5 md:px-8"><div className="flex items-center gap-3 text-xs"><button onClick={() => setOpen(!open)} className="lg:hidden" aria-label="Open navigation"><Menu size={20}/></button><span className="hidden text-muted-foreground sm:inline">Workspace</span><ChevronRight size={13} className="hidden text-muted-foreground sm:block"/><span className="font-medium">{label}</span></div><div className="flex items-center gap-3"><span className="hidden rounded-md border border-border px-2.5 py-1 text-[10px] text-muted-foreground sm:block">Factory operations</span><span className="flex size-7 items-center justify-center rounded-full bg-secondary text-[10px] font-semibold text-primary">AP</span></div></header>
      <div className="min-w-0 overflow-x-clip [&_*]:min-w-0 [&_label]:block [&_label]:space-y-1.5 [&_label]:text-xs [&_label]:font-medium [&_input:not([type=checkbox])]:w-full [&_input:not([type=checkbox])]:rounded-md [&_input:not([type=checkbox])]:border [&_input:not([type=checkbox])]:border-input [&_input:not([type=checkbox])]:bg-card [&_input:not([type=checkbox])]:px-3 [&_input:not([type=checkbox])]:py-2.5 [&_input:not([type=checkbox])]:text-sm [&_select]:w-full [&_select]:rounded-md [&_select]:border [&_select]:border-input [&_select]:bg-card [&_select]:px-3 [&_select]:py-2.5 [&_select]:text-sm [&_textarea]:w-full [&_textarea]:rounded-md [&_textarea]:border [&_textarea]:border-input [&_textarea]:bg-card [&_textarea]:p-3 [&_textarea]:text-sm [&_input:focus]:outline-none [&_input:focus]:ring-2 [&_input:focus]:ring-ring/20 [&_select:focus]:outline-none [&_select:focus]:ring-2 [&_select:focus]:ring-ring/20 [&_textarea:focus]:outline-none [&_textarea:focus]:ring-2 [&_textarea:focus]:ring-ring/20">{children}</div>
    </main>
  </div>;
};
