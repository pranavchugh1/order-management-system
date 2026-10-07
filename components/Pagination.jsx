'use client';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

export const Pagination = ({ page = 1, pages = 1, total = 0, onChange, busy, label = 'records' }) => (
  <div className="my-4 flex flex-col items-stretch justify-between gap-3 text-xs text-muted-foreground sm:flex-row sm:items-center">
    <span>{total} {label} - Page {page} of {pages}</span>
    <div className="flex gap-2">
      <Button className="flex-1 sm:flex-none" variant="outline" size="sm" disabled={busy || page <= 1} onClick={() => onChange(page - 1)} aria-label={`Previous ${label}`}>
        <ChevronLeft size={14}/>Previous
      </Button>
      <Button className="flex-1 sm:flex-none" variant="outline" size="sm" disabled={busy || page >= pages} onClick={() => onChange(page + 1)} aria-label={`Next ${label}`}>
        Next<ChevronRight size={14}/>
      </Button>
    </div>
  </div>
);
