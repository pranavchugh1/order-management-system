import { api, errorText } from '@/lib/api';
// Each part is 128 KiB, safely below proxy request limits. Retries reuse the same part.
export const uploadPhoto = async (file, onProgress) => {
  if (!file || !['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) throw new Error('Choose a PNG, JPG or WebP image under 5 MB.');
  onProgress('Preparing upload…');
  const { data } = await api.post('/photos/uploads', { name: file.name, size: file.size, content_type: file.type });
  for (let index = 0; index < data.chunks; index++) {
    const chunk = file.slice(index * data.chunk_size, (index + 1) * data.chunk_size);
    let saved = false;
    for (let attempt = 0; attempt < 3 && !saved; attempt++) {
      onProgress(`Uploading part ${index+1} of ${data.chunks} · ${Math.round(index/data.chunks*100)}%${attempt ? ' · retrying' : ''}`);
      try { await api.put(`/photos/uploads/${data.id}/${index}`, chunk, { headers: { 'Content-Type': 'application/octet-stream' } }); saved = true; }
      catch (error) { if (attempt === 2 || (error.response && error.response.status < 500)) throw new Error(`Upload stopped at part ${index+1}. ${errorText(error)} Select the file again to restart.`); await new Promise(resolve => setTimeout(resolve, 500*(attempt+1))); }
    }
  }
  onProgress('100% uploaded · validating and saving…');
  for (let attempt = 0; attempt < 3; attempt++) {
    try { const result = await api.post(`/photos/uploads/${data.id}/complete`); onProgress('Photo saved'); return result.data.id; }
    catch (error) { if (attempt === 2 || (error.response && error.response.status < 500)) throw new Error(errorText(error)); }
  }
};
