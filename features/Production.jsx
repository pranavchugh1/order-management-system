"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { useEffect, useMemo, useState } from 'react';
import { ArrowRightLeft, Camera, Image, Plus, RefreshCw, Search, Upload, X } from 'lucide-react';
import { api, errorText, number } from '@/lib/api';
import { formatDate } from '@/lib/dates';
import { useAuth } from '@/context/AuthContext';
import { Button, PageTitle } from '@/components/WorkspacePrimitives';
import { Pagination } from '@/components/Pagination';
import { getMasterOptions } from '@/lib/master-options';
import { uploadPhoto } from '@/lib/upload-photo';
const emptyForm = {
  catalogue_id: '',
  volume_id: '',
  design_no: '',
  total_pieces: 0,
  note: '',
  photo_data_url: null
};
const emptyIssue = {
  from_stage: 'Unissued',
  to_stage: 'Stitching',
  custom_stage: '',
  pieces: 0,
  note: ''
};
export default function Production() {
  const {
    user
  } = useAuth();
  const [catalogues, setCatalogues] = useState([]);
  const [data, setData] = useState({
    batches: [],
    urgent: [],
    stages: [],
    summary: []
  });
  const [query, setQuery] = useState('');
  const [page, setPage] = useState(1), [urgentPage, setUrgentPage] = useState(1);
  const [uploading, setUploading] = useState(false), [uploadProgress, setUploadProgress] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setBusy] = useState(false);
  const busy = saving || uploading;
  const [error, setError] = useState('');
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState(emptyForm);
  const [issue, setIssue] = useState(null);
  const [detail, setDetail] = useState(null);
  const [edit, setEdit] = useState(null);
  const [editError, setEditError] = useState('');
  const [urgent, setUrgent] = useState({
    text: '',
    party_name: '',
    needed_by: '',
    priority: 'Urgent'
  });
  const selectedCatalogue = catalogues.find(c => c.id === form.catalogue_id);
  const selectedVolume = selectedCatalogue?.volumes?.find(v => v.id === form.volume_id);
  const batches = data.batches || [];
  const totals = data.totals || { produced: 0, unissued: 0, in_process: 0, packing: 0 };
  const editStageTotal = useMemo(() => (edit?.form.stage_balances || []).reduce((sum, row) => sum + Number(row.pieces || 0), 0), [edit]);
  const editProductionTotal = Number(edit?.form.total_pieces || 0);
  const editStageDelta = editProductionTotal - editStageTotal;
  const load = async () => {
    setLoading(true);
    setError('');
    try {
      const [production, cats] = await Promise.all([api.get('/production', { params: { q: query, page, urgent_page: urgentPage } }), getMasterOptions('catalogues')]);
      setData(production.data);
      setCatalogues(cats);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { const timer = setTimeout(load, 200); return () => clearTimeout(timer); }, [query, page, urgentPage]);
  const setCatalogue = id => setForm({
    ...form,
    catalogue_id: id,
    volume_id: ''
  });
  const readPhoto = async file => {
    if (!file) return;
    setUploading(true); setError('');
    try { const photo_id = await uploadPhoto(file, setUploadProgress); setForm(old => ({ ...old, photo_id, photo_data_url: null })); }
    catch (e) { setError(e.message); setUploadProgress('Upload failed. Select the file to retry.'); }
    finally { setUploading(false); }
  };
  const addProduction = async e => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.post('/production/batches', {
        ...form,
        total_pieces: Number(form.total_pieces),
        photo_data_url: form.photo_data_url || null
      });
      setForm(emptyForm);
      setShowAdd(false);
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const openIssue = batch => setIssue({
    batch,
    form: {
      ...emptyIssue,
      from_stage: batch.stage_balances?.find(row => row.pieces > 0)?.stage || 'Unissued'
    }
  });
  const submitIssue = async e => {
    e.preventDefault();
    const payload = {
      from_stage: issue.form.from_stage,
      to_stage: issue.form.to_stage === '__custom__' ? issue.form.custom_stage : issue.form.to_stage,
      pieces: Number(issue.form.pieces),
      note: issue.form.note || '',
      version: issue.batch.version
    };
    setBusy(true);
    setError('');
    try {
      await api.post(`/production/batches/${issue.batch.id}/issue`, payload);
      setIssue(null);
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const openEdit = batch => {
    setEditError('');
    setEdit({
      batch,
      form: {
        design_no: batch.design_no,
        total_pieces: batch.total_pieces,
        note: batch.note || '',
        keep_photo: true,
        photo_data_url: null,
        stage_balances: (batch.stage_balances || []).map(row => ({
          ...row
        }))
      }
    });
  };
  const setEditStage = (index, change) => {
    setEditError('');
    setEdit(old => ({
      ...old,
      form: {
        ...old.form,
        stage_balances: old.form.stage_balances.map((row, i) => i === index ? {
          ...row,
          ...change
        } : row)
      }
    }));
  };
  const addEditStage = () => {
    setEditError('');
    setEdit(old => ({
      ...old,
      form: {
        ...old.form,
        stage_balances: [...old.form.stage_balances, {
          stage: '',
          pieces: 0
        }]
      }
    }));
  };
  const removeEditStage = index => {
    setEditError('');
    setEdit(old => ({
      ...old,
      form: {
        ...old.form,
        stage_balances: old.form.stage_balances.filter((_, i) => i !== index)
      }
    }));
  };
  const readEditPhoto = async file => {
    if (!file) return;
    setUploading(true); setEditError('');
    try { const photo_id = await uploadPhoto(file, setUploadProgress); setEdit(old => ({ ...old, form: { ...old.form, photo_id, photo_data_url: null, keep_photo: true } })); }
    catch (e) { setEditError(e.message); setUploadProgress('Upload failed. Select the file to retry.'); }
    finally { setUploading(false); }
  };
  const saveProductionEdit = async e => {
    e.preventDefault();
    const totalPieces = Number(edit.form.total_pieces || 0);
    const stageRows = edit.form.stage_balances.map(row => ({
      stage: row.stage.trim(),
      pieces: Number(row.pieces || 0)
    }));
    const stageTotal = stageRows.reduce((sum, row) => sum + row.pieces, 0);
    const normalizedStages = stageRows.map(row => row.stage.toLowerCase());
    if (stageRows.some(row => !row.stage)) {
      setEditError('Every stage needs a name before saving.');
      return;
    }
    if (new Set(normalizedStages).size !== normalizedStages.length) {
      setEditError('Stage names must be unique. Merge duplicate stages before saving.');
      return;
    }
    if (stageTotal !== totalPieces) {
      setEditError(`Stage pieces must total exactly the production total. Current stage total is ${number(stageTotal)} and production total is ${number(totalPieces)}.`);
      return;
    }
    const payload = {
      ...edit.form,
      total_pieces: Number(edit.form.total_pieces),
      version: edit.batch.version,
      stage_balances: edit.form.stage_balances.map(row => ({
        stage: row.stage,
        pieces: Number(row.pieces || 0)
      }))
    };
    setBusy(true);
    setError('');
    setEditError('');
    try {
      await api.put(`/production/batches/${edit.batch.id}`, payload);
      setEdit(null);
      await load();
    } catch (e) {
      setEditError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const addUrgent = async e => {
    e.preventDefault();
    setBusy(true);
    setError('');
    try {
      await api.post('/production/urgent', urgent);
      setUrgent({
        text: '',
        party_name: '',
        needed_by: '',
        priority: 'Urgent'
      });
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const fulfillUrgent = async id => {
    setBusy(true);
    setError('');
    try {
      await api.delete(`/production/urgent/${id}`);
      await load();
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  const openDetail = async batch => {
    setBusy(true);
    setError('');
    try {
      const r = await api.get(`/production/batches/${batch.id}`);
      setDetail(r.data);
    } catch (e) {
      setError(errorText(e));
    } finally {
      setBusy(false);
    }
  };
  return <div className={workspaceClasses("page")}><PageTitle eyebrow="WORKSPACE / PRODUCTION" title="Production" description="Design-wise production entries, photos, and stage issue tracking." action={<div className={workspaceClasses("page-actions")}><Button variant="outline" onClick={load} disabled={loading || busy} data-testid="refresh-production-button"><RefreshCw size={16} />Refresh</Button><Button onClick={() => setShowAdd(true)} data-testid="open-add-production-button"><Plus size={16} />New production</Button></div>} />
    {error && <div className={workspaceClasses("error-banner")} role="alert" data-testid="production-error">{error}</div>}
    {loading ? <div className={workspaceClasses("loading")} data-testid="production-loading">Loading production...</div> : <>
      <div className={workspaceClasses("summary-grid stock-summary")}>{[['produced', 'Produced pieces'], ['unissued', 'Unissued pieces'], ['in_process', 'Issued pieces'], ['packing', 'Packing pieces']].map(([key, label]) => <div className={workspaceClasses("summary-stat")} key={key}><span>{label}</span><strong>{number(totals[key])}</strong></div>)}</div>
      <div className={workspaceClasses("toolbar")}><div className={workspaceClasses("search")}><Search size={17} /><input value={query} onChange={e => { setQuery(e.target.value); setPage(1); }} placeholder="Search design, catalogue, or volume" data-testid="production-search-input" /></div></div>
      <section className={workspaceClasses("urgent-panel")}><div className={workspaceClasses("list-head")}><h2>Urgent requirements</h2><span>{data.urgent_pagination?.total || 0} open</span></div><form className={workspaceClasses("urgent-form")} onSubmit={addUrgent}><input required maxLength={300} placeholder="What is needed?" value={urgent.text} onChange={e => setUrgent({
            ...urgent,
            text: e.target.value
          })} data-testid="urgent-text-input" /><input maxLength={120} placeholder="Party" value={urgent.party_name} onChange={e => setUrgent({
            ...urgent,
            party_name: e.target.value
          })} data-testid="urgent-party-input" /><input maxLength={40} placeholder="Needed by" value={urgent.needed_by} onChange={e => setUrgent({
            ...urgent,
            needed_by: e.target.value
          })} data-testid="urgent-needed-by-input" /><Button type="submit" disabled={busy || !urgent.text.trim()}><Plus size={15} />Add</Button></form>{!data.urgent.length ? <div className={workspaceClasses("empty compact")}><h3>No urgent requirements</h3></div> : <div className={workspaceClasses("urgent-list")}>{data.urgent.map(item => <div key={item.id} className={workspaceClasses("urgent-item")} data-testid={`urgent-${item.id}`}><div><strong>{item.text}</strong><span>{[item.party_name, item.needed_by, item.priority].filter(Boolean).join(' / ')}</span></div><Button variant="outline" onClick={() => fulfillUrgent(item.id)} disabled={busy}>Fulfilled</Button></div>)}</div>}<Pagination {...data.urgent_pagination} onChange={setUrgentPage} busy={loading} label="urgent requirements"/></section>
      <section className={workspaceClasses("stock-batches")}><div className={workspaceClasses("list-head")}><h2>Production entries</h2><span>{batches.length} shown</span></div>{!batches.length ? <div className={workspaceClasses("empty compact")}><h3>No production entries</h3></div> : <div className={workspaceClasses("batch-grid")}>{batches.map(batch => <article className={workspaceClasses("batch-card")} key={batch.id} data-testid={`production-batch-${batch.id}`}>
        <div className={workspaceClasses("batch-head")}><div><span className={workspaceClasses("parcel-kicker")}>{batch.catalogue_name} / {batch.volume_name}</span><h3>{batch.design_no}</h3><p>{formatDate(batch.created_at)} / {number(batch.total_pieces)} pieces</p></div>{batch.has_photo && <button className={workspaceClasses("icon-button")} title="View photo" onClick={() => openDetail(batch)}><Image size={17} /></button>}</div>
        <div className={workspaceClasses("stage-strip")}>{(batch.stage_balances || []).filter(row => row.pieces !== 0).map(row => <span key={row.stage}>{row.stage}<b>{number(row.pieces)}</b></span>)}</div>
        <div className={workspaceClasses("batch-actions")}><Button variant="outline" onClick={() => openDetail(batch)} disabled={busy}>Details</Button>{user.role === 'admin' && <Button variant="outline" onClick={() => openEdit(batch)} disabled={busy}>Edit</Button>}<Button onClick={() => openIssue(batch)} disabled={busy || !batch.stage_balances?.some(row => row.pieces > 0)}><ArrowRightLeft size={15} />Issue pieces</Button></div>
      </article>)}</div>}<Pagination {...data} onChange={setPage} busy={loading} label="production entries"/></section>
    </>}
    {showAdd && <div className={workspaceClasses("modal-scrim")} role="dialog" aria-modal="true" onClick={e => {
      if (e.target === e.currentTarget && !busy) setShowAdd(false);
    }}><form className={workspaceClasses("modal-card stock-modal")} onSubmit={addProduction}>
      <header className={workspaceClasses("modal-head")}><h2>New production</h2><button type="button" className={workspaceClasses("icon-button")} onClick={() => setShowAdd(false)}><X size={16} /></button></header>
      <div className={workspaceClasses("modal-body stock-form-grid")}>
        {uploadProgress && <div role="status" aria-live="polite" className="col-span-full rounded-lg bg-secondary p-3 text-xs text-primary">{uploadProgress}</div>}
        {error && <div role="alert" className="col-span-full rounded-lg bg-red-50 p-3 text-xs text-red-700">{error}</div>}
        <label>Catalogue<select required value={form.catalogue_id} onChange={e => setCatalogue(e.target.value)} data-testid="production-catalogue-select"><option value="">Select catalogue</option>{catalogues.map(c => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
        <label>Volume<select required value={form.volume_id} disabled={!form.catalogue_id} onChange={e => setForm({
              ...form,
              volume_id: e.target.value
            })} data-testid="production-volume-select"><option value="">Select volume</option>{(selectedCatalogue?.volumes || []).map(v => <option key={v.id} value={v.id}>{v.name}</option>)}</select></label>
        <label>Design no<input required maxLength={80} value={form.design_no} onChange={e => setForm({
              ...form,
              design_no: e.target.value
            })} data-testid="production-design-input" /></label>
        <label>Total pieces produced<input required type="number" min="1" max="10000000" value={form.total_pieces} onChange={e => setForm({
              ...form,
              total_pieces: e.target.value
            })} data-testid="production-total-pieces-input" /></label>
        <label>Photo upload<span className={workspaceClasses("file-control")}><Upload size={15} /><input type="file" disabled={busy} accept="image/png,image/jpeg,image/webp" onChange={e => readPhoto(e.target.files?.[0])} data-testid="production-photo-input" /></span></label>
        <label>Camera capture<span className={workspaceClasses("file-control")}><Camera size={15} /><input type="file" disabled={busy} accept="image/png,image/jpeg,image/webp" capture="environment" onChange={e => readPhoto(e.target.files?.[0])} data-testid="production-camera-input" /></span></label>
        <label className={workspaceClasses("span-2")}>Note<input maxLength={300} value={form.note} onChange={e => setForm({
              ...form,
              note: e.target.value
            })} data-testid="production-note-input" /></label>
        {selectedVolume && <div className={workspaceClasses("notice span-2")}>Selected volume has {selectedVolume.pieces_per_set} pieces per set. Produced pieces start in Unissued, then can be issued to Stitching, Folding, Packing, or a custom issue space.</div>}
      </div>
      <footer className={workspaceClasses("modal-foot")}><Button variant="outline" type="button" onClick={() => setShowAdd(false)} disabled={busy}>Cancel</Button><Button type="submit" disabled={busy}>Create</Button></footer>
    </form></div>}
    {issue && <div className={workspaceClasses("modal-scrim")} role="dialog" aria-modal="true" onClick={e => {
      if (e.target === e.currentTarget && !busy) setIssue(null);
    }}><form className={workspaceClasses("modal-card")} onSubmit={submitIssue}>
      <header className={workspaceClasses("modal-head")}><h2>Issue pieces</h2><button type="button" className={workspaceClasses("icon-button")} onClick={() => setIssue(null)}><X size={16} /></button></header>
      <div className={workspaceClasses("modal-body")}>
        <div className={workspaceClasses("notice")}>{issue.batch.design_no} / {issue.batch.catalogue_name} / {issue.batch.volume_name}</div>
        <label>From<select value={issue.form.from_stage} onChange={e => setIssue({
              ...issue,
              form: {
                ...issue.form,
                from_stage: e.target.value
              }
            })} data-testid="issue-from-stage">{(issue.batch.stage_balances || []).filter(row => row.pieces > 0).map(row => <option key={row.stage} value={row.stage}>{row.stage} ({number(row.pieces)})</option>)}</select></label>
        <label>To<select value={issue.form.to_stage} onChange={e => setIssue({
              ...issue,
              form: {
                ...issue.form,
                to_stage: e.target.value
              }
            })} data-testid="issue-to-stage">{[...(data.stages || []), '__custom__'].map(stage => <option key={stage} value={stage}>{stage === '__custom__' ? 'Custom stage' : stage}</option>)}</select></label>
        {issue.form.to_stage === '__custom__' && <label>Custom stage<input required maxLength={40} value={issue.form.custom_stage} onChange={e => setIssue({
              ...issue,
              form: {
                ...issue.form,
                custom_stage: e.target.value
              }
            })} data-testid="issue-custom-stage" /></label>}
        <label>Pieces<input required type="number" min="1" max="10000000" value={issue.form.pieces} onChange={e => setIssue({
              ...issue,
              form: {
                ...issue.form,
                pieces: e.target.value
              }
            })} data-testid="issue-pieces-input" /></label>
        <label>Note<input maxLength={300} value={issue.form.note} onChange={e => setIssue({
              ...issue,
              form: {
                ...issue.form,
                note: e.target.value
              }
            })} data-testid="issue-note-input" /></label>
      </div>
      <footer className={workspaceClasses("modal-foot")}><Button variant="outline" type="button" onClick={() => setIssue(null)} disabled={busy}>Cancel</Button><Button type="submit" disabled={busy || !Number(issue.form.pieces)}>Issue</Button></footer>
    </form></div>}
    {detail && <div className={workspaceClasses("modal-scrim")} role="dialog" aria-modal="true" onClick={e => {
      if (e.target === e.currentTarget) setDetail(null);
    }}><div className={workspaceClasses("modal-card stock-modal")}>
      <header className={workspaceClasses("modal-head")}><h2>{detail.batch.design_no}</h2><button className={workspaceClasses("icon-button")} onClick={() => setDetail(null)}><X size={16} /></button></header>
      <div className={workspaceClasses("modal-body")}>{(detail.batch.photo_url || detail.batch.photo_data_url) && <img className={workspaceClasses("design-photo")} src={detail.batch.photo_url || detail.batch.photo_data_url} alt={detail.batch.design_no} />}<div className={workspaceClasses("stage-strip")}>{detail.batch.stage_balances.filter(row => row.pieces !== 0).map(row => <span key={row.stage}>{row.stage}<b>{number(row.pieces)}</b></span>)}</div><div className={workspaceClasses("movement-list")}>{detail.movements.map(m => <div key={m.id}><strong>{m.from_stage} to {m.to_stage}</strong><span>{number(m.pieces)} pieces / {formatDate(m.created_at)}{m.note ? ` / ${m.note}` : ''}</span></div>)}</div></div>
    </div></div>}
    {edit && <div className={workspaceClasses("modal-scrim")} role="dialog" aria-modal="true" onClick={e => {
      if (e.target === e.currentTarget && !busy) setEdit(null);
    }}><form className={workspaceClasses("modal-card stock-modal")} onSubmit={saveProductionEdit}>
      <header className={workspaceClasses("modal-head")}><h2>Edit production</h2><button type="button" className={workspaceClasses("icon-button")} onClick={() => setEdit(null)}><X size={16} /></button></header>
      <div className={workspaceClasses("modal-body stock-form-grid")}>
        {uploadProgress && <div role="status" aria-live="polite" className="col-span-full rounded-lg bg-secondary p-3 text-xs text-primary">{uploadProgress}</div>}
        {error && <div role="alert" className="col-span-full rounded-lg bg-red-50 p-3 text-xs text-red-700">{error}</div>}
        <label>Design no<input required maxLength={80} value={edit.form.design_no} onChange={e => setEdit({
              ...edit,
              form: {
                ...edit.form,
                design_no: e.target.value
              }
            })} data-testid="edit-production-design-input" /></label>
        <label>Total pieces<input required type="number" min="1" max="10000000" value={edit.form.total_pieces} onChange={e => setEdit({
              ...edit,
              form: {
                ...edit.form,
                total_pieces: e.target.value
              }
            })} data-testid="edit-production-total-input" /></label>
        <label className={workspaceClasses("span-2")}>Note<input maxLength={300} value={edit.form.note} onChange={e => setEdit({
              ...edit,
              form: {
                ...edit.form,
                note: e.target.value
              }
            })} data-testid="edit-production-note-input" /></label>
        {editError && <div className={workspaceClasses("modal-alert span-2")} role="alert" data-testid="edit-production-error">{editError}</div>}
        <label>Replace photo<span className={workspaceClasses("file-control")}><Upload size={15} /><input type="file" disabled={busy} accept="image/png,image/jpeg,image/webp" onChange={e => readEditPhoto(e.target.files?.[0])} data-testid="edit-production-photo-input" /></span></label>
        <label>Camera capture<span className={workspaceClasses("file-control")}><Camera size={15} /><input type="file" disabled={busy} accept="image/png,image/jpeg,image/webp" capture="environment" onChange={e => readEditPhoto(e.target.files?.[0])} data-testid="edit-production-camera-input" /></span></label>
        <label className={workspaceClasses("access-check")}><input type="checkbox" checked={!edit.form.keep_photo} onChange={e => setEdit({
              ...edit,
              form: {
                ...edit.form,
                keep_photo: !e.target.checked,
                photo_id: e.target.checked ? null : edit.form.photo_id,
                photo_data_url: e.target.checked ? null : edit.form.photo_data_url
              }
            })} />Remove existing photo</label>
        <div className={workspaceClasses("span-2 edit-stage-list")}><div className={workspaceClasses("list-head")}><h2>Stage balances</h2><Button type="button" variant="outline" onClick={addEditStage}><Plus size={14} />Stage</Button></div>{edit.form.stage_balances.map((row, index) => <div className={workspaceClasses("edit-stage-row")} key={index}><input required maxLength={40} placeholder="Stage" value={row.stage} onChange={e => setEditStage(index, {
                stage: e.target.value
              })} /><input required type="number" min="0" max="10000000" value={row.pieces} onChange={e => setEditStage(index, {
                pieces: e.target.value
              })} /><button type="button" className={workspaceClasses("icon-button danger-icon")} onClick={() => removeEditStage(index)} disabled={edit.form.stage_balances.length <= 1}><X size={15} /></button></div>)}<div className={workspaceClasses(`stage-total ${editStageDelta === 0 ? 'ok' : 'bad'}`)}><span>Stage total: {number(editStageTotal)}</span><span>{editStageDelta === 0 ? 'Matches production total' : `${number(Math.abs(editStageDelta))} ${editStageDelta > 0 ? 'pieces short' : 'pieces over'}`}</span></div></div>
      </div>
      <footer className={workspaceClasses("modal-foot")}><Button variant="outline" type="button" onClick={() => setEdit(null)} disabled={busy}>Cancel</Button><Button type="submit" disabled={busy}>Save changes</Button></footer>
    </form></div>}
  </div>;
}
