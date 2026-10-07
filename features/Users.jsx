"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { useCallback, useEffect, useMemo, useState } from 'react';
import { KeyRound, Pencil, Plus, ShieldCheck, UserRound } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { api, errorText } from '@/lib/api';
import { PAGE_OPTIONS } from '@/lib/access';
import { useAuth } from '@/context/AuthContext';
import { Button, PageTitle } from '@/components/WorkspacePrimitives';
import { toast } from 'sonner';
import { Pagination } from '@/components/Pagination';
const emptyForm = {
  name: '',
  email: '',
  password: '',
  page_access: []
};
function AccessChecks({
  value,
  onChange,
  disabled = false,
  prefix
}) {
  const toggle = page => {
    const next = value.includes(page) ? value.filter(item => item !== page) : [...value, page];
    onChange(next);
  };
  return <div className={workspaceClasses("access-grid")}>
    {PAGE_OPTIONS.map(page => <label className={workspaceClasses("access-check")} key={page.id}>
      <input type="checkbox" checked={value.includes(page.id)} disabled={disabled} onChange={() => toggle(page.id)} data-testid={`${prefix}-${page.id}`} />
      <span>{page.label}</span>
    </label>)}
  </div>;
}
export default function Users() {
  const {
    user
  } = useAuth();
  const [users, setUsers] = useState([]);
  const [page, setPage] = useState(1), [pagination, setPagination] = useState({}), [counts, setCounts] = useState({ total: 0, active: 0, disabled: 0 });
  const [form, setForm] = useState(emptyForm);
  const [filter, setFilter] = useState('active');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [reset, setReset] = useState(null);
  const [edit, setEdit] = useState(null);
  const [password, setPassword] = useState('');
  const load = useCallback(() => api.get('/auth/users', { params: { page, status: filter } }).then(r => { setUsers(r.data.items || []); setPagination(r.data); setCounts(r.data.summary || {}); }), [page, filter]);
  useEffect(() => {
    load().catch(e => setError(errorText(e)));
  }, [load]);
  const visibleUsers = users;
  const create = async e => {
    e.preventDefault();
    if (!form.page_access.length) {
      setError('Select at least one page for this member.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await api.post('/auth/users', form);
      setForm(emptyForm);
      await load();
      toast.success('Team member added');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const openEdit = u => setEdit({
    id: u.id,
    role: u.role,
    name: u.name,
    email: u.email,
    active: u.active,
    page_access: u.page_access || []
  });
  const saveEdit = async e => {
    e.preventDefault();
    if (edit.role !== 'admin' && !edit.page_access.length) {
      setError('Select at least one page before saving access.');
      return;
    }
    const payload = {
      name: edit.name,
      email: edit.email
    };
    if (edit.role !== 'admin') {
      payload.active = edit.active;
      payload.page_access = edit.page_access;
    }
    setBusy(true);
    setError('');
    try {
      await api.patch(`/auth/users/${edit.id}`, payload);
      setEdit(null);
      await load();
      toast.success('Team member updated');
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const toggle = async u => {
    if (!window.confirm(`${u.active ? 'Disable' : 'Enable'} access for ${u.name}?`)) return;
    setBusy(true);
    setError('');
    try {
      await api.patch(`/auth/users/${u.id}`, {
        active: !u.active
      });
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const resetPassword = async e => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.put(`/auth/users/${reset.id}/password`, {
        password
      });
      const self = reset.id === user.id;
      setReset(null);
      setPassword('');
      toast.success('Password updated. Existing sessions have ended.');
      if (self) window.dispatchEvent(new Event('session-ended'));
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return <div className={workspaceClasses("page")}><PageTitle eyebrow="WORKSPACE / ACCESS" title="Team access" description="Active users, page permissions, profile details, and password resets." />
    {error && <div className={workspaceClasses("error-banner")} role="alert" data-testid="users-error">{error}</div>}
    <div className={workspaceClasses("summary-grid team-summary")}>{[['active', 'Active users'], ['disabled', 'Disabled users'], ['total', 'Total users']].map(([key, label]) => <div className={workspaceClasses("summary-stat")} key={key}><span>{label}</span><strong>{counts[key]}</strong></div>)}</div>
    <section className={workspaceClasses("team-create")}><h2>Add a team member</h2><form className={workspaceClasses("team-form team-form-access")} onSubmit={create}>
      <label>Name<input required maxLength={100} value={form.name} onChange={e => setForm({
            ...form,
            name: e.target.value
          })} data-testid="user-name-input" /></label>
      <label>Email<input required type="email" maxLength={254} value={form.email} onChange={e => setForm({
            ...form,
            email: e.target.value
          })} data-testid="user-email-input" /></label>
      <label>Password<input required type="password" autoComplete="new-password" minLength={12} maxLength={72} placeholder="At least 12 characters" value={form.password} onChange={e => setForm({
            ...form,
            password: e.target.value
          })} data-testid="user-password-input" /></label>
      <div className={workspaceClasses("team-access-picker")}><span>Page access</span><AccessChecks value={form.page_access} onChange={pages => setForm({
            ...form,
            page_access: pages
          })} prefix="new-user-access" /></div>
      <Button disabled={busy || !form.page_access.length} type="submit" data-testid="create-user-button"><Plus size={16} />Add member</Button>
    </form></section>
    <div className={workspaceClasses("team-filter")} role="tablist" aria-label="Team filter">{[['active', 'Active'], ['all', 'All'], ['disabled', 'Disabled']].map(([key, label]) => <button key={key} className={workspaceClasses(filter === key ? 'active' : '')} onClick={() => { setFilter(key); setPage(1); }} type="button">{label}</button>)}</div>
    <section className={workspaceClasses("team-list")}>{visibleUsers.map(u => <div className={workspaceClasses("team-member team-member-access")} key={u.id} data-testid={`user-${u.id}`}>
      <div className={workspaceClasses("team-avatar")}>{u.role === 'admin' ? <ShieldCheck size={21} /> : <UserRound size={21} />}</div>
      <div className={workspaceClasses("team-identity")}><strong>{u.name}</strong><span>{u.email}</span></div>
      <span className={workspaceClasses(`status ${u.active ? 'sent' : ''}`)} data-testid={`user-status-${u.id}`}>{u.active ? u.role === 'admin' ? 'Administrator' : 'Active' : 'Disabled'}</span>
      <div className={workspaceClasses("team-actions")}>
        <button className={workspaceClasses("icon-button")} title="Edit details" onClick={() => {
            openEdit(u);
            setError('');
          }} data-testid={`edit-user-${u.id}`}><Pencil size={17} /></button>
        <button className={workspaceClasses("icon-button")} title="Reset password" onClick={() => {
            setReset(u);
            setPassword('');
            setError('');
          }} data-testid={`reset-user-password-${u.id}`}><KeyRound size={17} /></button>
        {u.role !== 'admin' && <Button variant="outline" disabled={busy} onClick={() => toggle(u)} data-testid={`toggle-user-${u.id}`}>{u.active ? 'Disable' : 'Enable'}</Button>}
      </div>
      <div className={workspaceClasses("member-access")}><AccessChecks value={u.page_access || []} disabled prefix={`user-access-readonly-${u.id}`} /></div>
    </div>)}<Pagination {...pagination} onChange={setPage} busy={busy} label="team members"/></section>
    <Dialog open={!!edit} onOpenChange={() => {
      setEdit(null);
      setError('');
    }}><DialogContent data-testid="edit-user-modal"><DialogHeader><DialogTitle>Edit member</DialogTitle></DialogHeader>{edit && <form onSubmit={saveEdit}><label>Name<input required maxLength={100} value={edit.name} onChange={e => setEdit({
              ...edit,
              name: e.target.value
            })} data-testid="edit-user-name-input" /></label><label>Email<input required type="email" maxLength={254} value={edit.email} onChange={e => setEdit({
              ...edit,
              email: e.target.value
            })} data-testid="edit-user-email-input" /></label>{edit.role !== 'admin' && <label className={workspaceClasses("access-check edit-active-check")}><input type="checkbox" checked={edit.active} onChange={e => setEdit({
              ...edit,
              active: e.target.checked
            })} data-testid="edit-user-active-input" /><span>Active user</span></label>}{edit.role !== 'admin' && <div className={workspaceClasses("team-access-picker")}><span>Page access</span><AccessChecks value={edit.page_access} onChange={pages => setEdit({
              ...edit,
              page_access: pages
            })} prefix="edit-user-access" /></div>}{error && <div className={workspaceClasses("error-banner")} role="alert" data-testid="edit-user-error">{error}</div>}<Button type="submit" disabled={busy || edit.role !== 'admin' && !edit.page_access.length} data-testid="edit-user-submit-button">Save details</Button></form>}</DialogContent></Dialog>
    <Dialog open={!!reset} onOpenChange={() => {
      setReset(null);
      setError('');
    }}><DialogContent data-testid="reset-password-modal"><DialogHeader><DialogTitle>Reset password - {reset?.name}</DialogTitle></DialogHeader><form onSubmit={resetPassword}><label>New password<input required autoComplete="new-password" type="password" minLength={12} maxLength={72} value={password} onChange={e => setPassword(e.target.value)} data-testid="reset-password-input" /></label>{error && <div className={workspaceClasses("error-banner")} role="alert" data-testid="reset-password-error">{error}</div>}<Button type="submit" disabled={busy} data-testid="reset-password-submit-button">Reset password</Button></form></DialogContent></Dialog>
  </div>;
}
