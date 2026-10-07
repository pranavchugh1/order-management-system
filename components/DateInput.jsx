"use client";

import { workspaceClasses } from "@/lib/workspace-styles";
import { useEffect, useState } from 'react';
import { formatDate, parseDate, validDate } from '@/lib/dates';
export const DateInput = ({
  value,
  onChange,
  testId
}) => {
  const [text, setText] = useState(value ? formatDate(value) : '');
  useEffect(() => {
    if (value) setText(formatDate(value));
  }, [value]);
  const invalid = !validDate(value);
  return <div className={workspaceClasses("date-field")}>
    <input type="text" inputMode="numeric" placeholder="dd-mm-yyyy" maxLength={10} value={text} aria-invalid={invalid} aria-describedby={invalid ? `${testId}-error` : undefined} data-testid={testId} onChange={e => {
      setText(e.target.value);
      onChange(parseDate(e.target.value));
    }} />
    {invalid && <span className={workspaceClasses("field-error")} id={`${testId}-error`} role="alert" data-testid={`${testId}-error`}>Enter a valid date, dd-mm-yyyy, not in the future.</span>}
  </div>;
};
