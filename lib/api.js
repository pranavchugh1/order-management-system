"use client";

import axios from 'axios';
export const api = axios.create({
  baseURL: '/api',
  timeout: 65000,
  withCredentials: true,
  xsrfCookieName: 'csrf_token',
  xsrfHeaderName: 'X-CSRF-Token',
  withXSRFToken: true
});
let refreshing;
api.interceptors.response.use(response => {
  if (typeof window !== 'undefined' && !['get', 'head'].includes(response.config?.method)) {
    if (/^\/(catalogues|parties)(\/|$)/.test(response.config?.url || '')) window.dispatchEvent(new Event('masters-changed'));
    if (['/auth/login', '/auth/logout'].includes(response.config?.url)) window.dispatchEvent(new Event('session-changed'));
  }
  return response;
}, async error => {
  const config = error.config;
  if (error.response?.status === 401 && config && !config._retried && !['/auth/login', '/auth/refresh'].includes(config.url)) {
    config._retried = true;
    try {
      if (!refreshing) refreshing = api.post('/auth/refresh').finally(() => {
        refreshing = null;
      });
      await refreshing;
      return api(config);
    } catch (_) {
      window.dispatchEvent(new Event('session-ended'));
    }
  }
  return Promise.reject(error);
});
export const errorText = e => typeof e.response?.data?.detail === 'string' ? e.response.data.detail : Array.isArray(e.response?.data?.detail) ? e.response.data.detail.map(d => `${d.loc?.slice(1).join(' / ')}: ${d.msg}`).join('; ') : e.message && !e.response ? e.message : 'Something went wrong. Please try again.';
export const number = n => Number(n || 0).toLocaleString('en-IN');
