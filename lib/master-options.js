import { api } from '@/lib/api';
// Native catalogue/party selectors need complete option sets. Transport is paged,
// compact, shared between concurrent consumers, and invalidated on writes/logout.
const cache = new Map();
if (typeof window !== 'undefined') {
  for (const event of ['masters-changed', 'session-ended', 'session-changed']) window.addEventListener(event, () => cache.clear());
}
export const getMasterOptions = type => {
  const existing = cache.get(type);
  if (existing && Date.now() - existing.time < 30000) return existing.promise;
  const promise = (async () => {
    let page = 1, result = [], pages = 1;
    do {
      const { data } = await api.get(`/${type}`, { params: { page, page_size: 200 } });
      result.push(...(data.items || [])); pages = data.pages; page++;
    } while (page <= pages);
    return result;
  })().catch(error => { cache.delete(type); throw error; });
  cache.set(type, { promise, time: Date.now() });
  return promise;
};
