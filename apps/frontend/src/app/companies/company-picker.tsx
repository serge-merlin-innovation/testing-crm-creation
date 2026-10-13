"use client";

import { useState } from "react";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { fillTemplate } from "@/lib/compliance";
import type { MessageKey } from "@/lib/i18n/messages";
import type { CompanyRef } from "@/lib/records";
import { useApiData } from "@/lib/use-api";

export const NO_COMPANY = "none";

/** A company Select narrowed by a name search, so it reaches every company, not the first page. */
export function CompanyPicker({
  id,
  label,
  value,
  onChange,
  messages,
  exclude = [],
  current,
  allowNone = true,
  error,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  messages: Record<MessageKey, string>;
  exclude?: number[];
  current?: CompanyRef | null;
  allowNone?: boolean;
  error?: string;
}) {
  const [query, setQuery] = useState("");
  const found = useApiData<CompanyRef[]>(`/api/v1/companies/?limit=50&q=${encodeURIComponent(query.trim())}`);
  const options = [...(current ? [current] : []), ...(found.data ?? []).filter((company) => company.id !== current?.id)].filter(
    (company) => !exclude.includes(company.id),
  );

  return (
    <>
      <Field>
        <FieldLabel htmlFor={`${id}-find`}>{fillTemplate(messages["records.findCompany"], { field: label })}</FieldLabel>
        <Input id={`${id}-find`} value={query} onChange={(event) => setQuery(event.target.value)} />
      </Field>
      <Field>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {allowNone ? <SelectItem value={NO_COMPANY}>{messages["deals.none"]}</SelectItem> : null}
          {options.map((company) => (
            <SelectItem key={company.id} value={String(company.id)}>
              {company.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <FieldError>{error}</FieldError>
      </Field>
    </>
  );
}
