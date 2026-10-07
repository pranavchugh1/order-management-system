"use client";

// Keep API/storage dates ISO; format all user-visible dates explicitly.
export const formatDate = value => {
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? `${match[3]}-${match[2]}-${match[1]}` : '—';
};
export const todayISO = () => {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
};
export const parseDate = value => {
  const match = value.match(/^(\d{2})-(\d{2})-(\d{4})$/);
  if (!match) return '';
  const [, day, month, year] = match;
  if (Number(year) < 1) return '';
  const iso = `${year}-${month}-${day}`;
  const date = new Date(`${iso}T12:00:00Z`);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === iso ? iso : '';
};
export const validDate = value => /^\d{4}-\d{2}-\d{2}$/.test(value || '') && parseDate(formatDate(value)) === value && value <= todayISO();
