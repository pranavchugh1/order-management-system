"use client";

import { useEffect, useState } from 'react';
import { api, errorText } from '@/lib/api';
import { getMasterOptions } from '@/lib/master-options';
export const useMasters = () => {
  const [catalogues, setCatalogues] = useState([]),
    [parties, setParties] = useState([]);
  const [loading, setLoading] = useState(true),
    [error, setError] = useState('');
  useEffect(() => {
    let active = true;
    Promise.all([getMasterOptions('catalogues'), getMasterOptions('parties')]).then(([c, p]) => {
      if (active) {
        setCatalogues(c);
        setParties(p);
      }
    }).catch(e => {
      if (active) setError(errorText(e));
    }).finally(() => {
      if (active) setLoading(false);
    });
    return () => {
      active = false;
    };
  }, []);
  return {
    catalogues,
    parties,
    loading,
    error,
    setParties
  };
};
