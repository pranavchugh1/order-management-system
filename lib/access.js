"use client";

export const PAGE_OPTIONS = [{
  id: 'orders_all',
  label: 'All orders',
  path: '/'
}, {
  id: 'orders_pending',
  label: 'Pending orders',
  path: '/orders/pending'
}, {
  id: 'orders_completed',
  label: 'Completed orders',
  path: '/orders/completed'
}, {
  id: 'bulk',
  label: 'Bulk entry',
  path: '/bulk'
}, {
  id: 'pending_requirements',
  label: 'Pending requirements',
  path: '/pending'
}, {
  id: 'challans',
  label: 'Challans',
  path: '/challans'
}, {
  id: 'catalogues',
  label: 'Catalogues',
  path: '/catalogues'
}, {
  id: 'parties',
  label: 'Parties',
  path: '/parties'
}, {
  id: 'stock',
  label: 'Stock',
  path: '/stock'
}, {
  id: 'production',
  label: 'Production',
  path: '/production'
}, {
  id: 'bills',
  label: 'Bills & cash',
  path: '/bills'
}];
export const ORDER_PAGE_IDS = ['orders_all', 'orders_pending', 'orders_completed'];
export const canAccess = (user, page) => user?.role === 'admin' || user?.page_access?.includes(page);
export const canAccessAny = (user, pages) => user?.role === 'admin' || pages.some(page => user?.page_access?.includes(page));
export const firstAccessiblePath = user => PAGE_OPTIONS.find(page => canAccess(user, page.id))?.path || '/no-access';
