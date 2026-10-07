"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { useEffect, useRef, useState } from 'react';
import { ChevronDown, Download } from 'lucide-react';
import { toast } from 'sonner';
import { api, errorText } from '@/lib/api';
import { canAccess } from '@/lib/access';
import { useAuth } from '@/context/AuthContext';
import { formatDate, todayISO } from '@/lib/dates';
import { Button } from './WorkspacePrimitives';
const REPORTS = [{
  id: 'pending-requirements',
  label: 'Pending requirements',
  hint: 'Catalogue & volume totals',
  access: 'pending_requirements'
}, {
  id: 'pending-orders',
  label: 'Pending orders (party-wise)',
  hint: 'Every open parcel, grouped by party',
  access: 'orders_pending'
}, {
  id: 'completed-orders',
  label: 'Completed orders (party-wise)',
  hint: 'Dispatched orders with challans',
  access: 'orders_completed'
}];
export const ExportButton = ({
  testId = 'export-excel-button'
}) => {
  const {
    user
  } = useAuth();
  const [busy, setBusy] = useState(''),
    [open, setOpen] = useState(false),
    ref = useRef(null);
  const reports = REPORTS.filter(report => canAccess(user, report.access));
  useEffect(() => {
    if (!open) return;
    const close = e => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    };
    const escape = e => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', escape);
    };
  }, [open]);
  const download = async report => {
    setOpen(false);
    setBusy(report.id);
    try {
      const response = await api.get(`/exports/${report.id}.xlsx`, {
        responseType: 'blob'
      });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = `Aditya-Prints-${report.label.replace(/[^\w]+/g, '-')}-${formatDate(todayISO())}.xlsx`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      toast.success(`${report.label} downloaded`);
    } catch (e) {
      if (e.response?.data instanceof Blob) {
        try {
          e.response.data = JSON.parse(await e.response.data.text());
        } catch (_) {}
      }
      toast.error(errorText(e));
    } finally {
      setBusy('');
    }
  };
  if (!reports.length) return null;
  return <div className={workspaceClasses("export-dropdown")} ref={ref}>
    <Button variant="outline" onClick={() => setOpen(v => !v)} disabled={!!busy} data-testid={testId} aria-haspopup="menu" aria-expanded={open}>
      <Download size={16} />{busy ? 'Generating…' : 'Export Excel'}<ChevronDown size={14} />
    </Button>
    {open && <div className={workspaceClasses("export-menu")} role="menu" data-testid={`${testId}-menu`}>{reports.map(r => <button key={r.id} role="menuitem" className={workspaceClasses("export-menu-item")} onClick={() => download(r)} data-testid={`export-option-${r.id}`}><strong>{r.label}</strong><span>{r.hint}</span></button>)}</div>}
  </div>;
};
