"use client";

import Link from "next/link";
import { useState, type FormEvent } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldDescription, FieldError, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { fieldErrors, readDetail } from "@/lib/deals";
import type { Language, MessageKey } from "@/lib/i18n/messages";
import { companyHref, companyPayload, RECORD_LANGUAGES, type RegisterPrefill } from "@/lib/records";
import { sendJson, useApiData } from "@/lib/use-api";
import { InvestorProfilePanel } from "./investor-profile";

type Messages = Record<MessageKey, string>;
type Company = { id: number; name: string; type: string; country_id: number; enterprise_number: string | null };
type Option = { id: number; label: string; code: string };
type Duplicate = { id: number; name: string; reason: string };

const BUYER_TYPES = new Set(["strategic_buyer", "financial_investor"]);
const COMPANY_TYPES = ["target", "strategic_buyer", "financial_investor", "lender", "advisor", "other"];

export function CompaniesView({ messages }: { messages: Messages }) {
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const companies = useApiData<Company[]>(`/api/v1/companies/?q=${encodeURIComponent(search)}`);
  const countries = useApiData<Option[]>("/api/v1/picklists/?kind=country");
  const [name, setName] = useState("");
  const [type, setType] = useState("target");
  const [countryId, setCountryId] = useState("");
  const [number, setNumber] = useState("");
  const [address, setAddress] = useState("");
  const [register, setRegister] = useState<{ legalForm: string | null; naceCode: string | null }>({
    legalForm: null,
    naceCode: null,
  });
  const [lookupMissed, setLookupMissed] = useState(false);
  const [recordLanguage, setRecordLanguage] = useState<Language>("en");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  const [duplicates, setDuplicates] = useState<{ list: Duplicate[]; canConfirm: boolean } | null>(null);
  const [profileFor, setProfileFor] = useState<number | null>(null);

  const belgian = countries.data?.find((country) => String(country.id) === countryId)?.code === "BE";

  async function lookup() {
    setErrors({});
    setLookupMissed(false);
    const result = await sendJson("/api/v1/companies/lookup", "POST", { enterprise_number: number });
    if (result.status !== 200) {
      const inline = fieldErrors(result.body);
      setErrors({ enterprise_number: inline.enterprise_number ?? readDetail(result.body, messages["common.saveFailed"]) });
      return;
    }
    const prefill = result.body as RegisterPrefill;
    if (!prefill.available) {
      setLookupMissed(true);
      return;
    }
    setName(prefill.name ?? name);
    setAddress(prefill.address ?? "");
    setRegister({ legalForm: prefill.legal_form, naceCode: prefill.nace_code });
  }

  async function create(event: FormEvent<HTMLFormElement> | null, ignoreSimilar = false) {
    event?.preventDefault();
    setErrors({});
    setNotice("");
    const payload = companyPayload(
      { name, type, countryId, number, belgian, language: recordLanguage, address, ...register },
      ignoreSimilar,
    );
    const result = await sendJson("/api/v1/companies/", "POST", payload);
    if (result.status === 201) {
      setDuplicates(null);
      setName("");
      setNumber("");
      setAddress("");
      setRegister({ legalForm: null, naceCode: null });
      setNotice(messages["companies.created"]);
      await companies.reload();
      return;
    }
    if (result.status === 409) {
      const detail = (result.body as { detail?: { duplicates?: Duplicate[]; can_confirm?: boolean } }).detail;
      setDuplicates({ list: detail?.duplicates ?? [], canConfirm: Boolean(detail?.can_confirm) });
      return;
    }
    const inline = fieldErrors(result.body);
    setErrors(Object.keys(inline).length ? inline : { form: readDetail(result.body, messages["common.saveFailed"]) });
  }

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{messages["companies.title"]}</h1>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <form
            className="flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              setSearch(query);
            }}
          >
            <Input
              aria-label={messages["common.search"]}
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
            <Button type="submit" variant="outline">
              {messages["common.search"]}
            </Button>
          </form>
          {companies.failed ? (
            <Alert variant="destructive">
              <AlertDescription>{messages["common.loadFailed"]}</AlertDescription>
            </Alert>
          ) : null}
          <div className="overflow-x-auto" tabIndex={0}>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{messages["common.name"]}</TableHead>
                  <TableHead>{messages["companies.type"]}</TableHead>
                  <TableHead>{messages["companies.enterpriseNumber"]}</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {(companies.data ?? []).map((company) => (
                  <TableRow key={company.id}>
                    <TableCell>
                      <Button asChild variant="link">
                        <Link href={companyHref(company.id)}>{company.name}</Link>
                      </Button>
                    </TableCell>
                    <TableCell>{company.type}</TableCell>
                    <TableCell>{company.enterprise_number ?? ""}</TableCell>
                    <TableCell>
                      {BUYER_TYPES.has(company.type) ? (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setProfileFor(profileFor === company.id ? null : company.id)}
                        >
                          {messages["investor.open"]}
                        </Button>
                      ) : null}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
          {companies.data?.length === 0 ? <p>{messages["common.empty"]}</p> : null}
          {profileFor !== null ? <InvestorProfilePanel key={profileFor} companyId={profileFor} messages={messages} /> : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>{messages["companies.new"]}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={(event) => void create(event)}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="company-name">{messages["common.name"]}</FieldLabel>
                <Input id="company-name" value={name} onChange={(event) => setName(event.target.value)} />
                <FieldError>{errors.name}</FieldError>
              </Field>
              <Field>
                <FieldLabel htmlFor="company-type">{messages["companies.type"]}</FieldLabel>
                <Select value={type} onValueChange={setType}>
                  <SelectTrigger id="company-type">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {COMPANY_TYPES.map((value) => (
                      <SelectItem key={value} value={value}>
                        {value}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field>
                <FieldLabel htmlFor="company-country">{messages["companies.country"]}</FieldLabel>
                <Select value={countryId} onValueChange={setCountryId}>
                  <SelectTrigger id="company-country">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {(countries.data ?? []).map((country) => (
                      <SelectItem key={country.id} value={String(country.id)}>
                        {country.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <FieldError>{errors.country_id}</FieldError>
              </Field>
              <Field>
                <FieldLabel htmlFor="company-number">
                  {belgian ? messages["companies.enterpriseNumber"] : messages["companies.registryNumber"]}
                </FieldLabel>
                <div className="flex gap-2">
                  <Input id="company-number" value={number} onChange={(event) => setNumber(event.target.value)} />
                  {belgian ? (
                    <Button type="button" variant="outline" disabled={!number.trim()} onClick={() => void lookup()}>
                      {messages["companies.lookup"]}
                    </Button>
                  ) : null}
                </div>
                {lookupMissed ? <FieldDescription>{messages["companies.lookupUnavailable"]}</FieldDescription> : null}
                <FieldError>{errors.enterprise_number ?? errors.vat_or_registry_number}</FieldError>
              </Field>
              <Field>
                <FieldLabel htmlFor="company-address">{messages["companies.address"]}</FieldLabel>
                <Input id="company-address" value={address} onChange={(event) => setAddress(event.target.value)} />
                <FieldError>{errors.address}</FieldError>
              </Field>
              <Field>
                <FieldLabel htmlFor="company-language">{messages["records.language"]}</FieldLabel>
                <Select value={recordLanguage} onValueChange={(value) => setRecordLanguage(value as Language)}>
                  <SelectTrigger id="company-language">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {RECORD_LANGUAGES.map((value) => (
                      <SelectItem key={value} value={value}>
                        {messages[`records.language.${value}`]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              {errors.form ? (
                <Alert variant="destructive">
                  <AlertDescription>{errors.form}</AlertDescription>
                </Alert>
              ) : null}
              {duplicates ? (
                <Alert>
                  <AlertDescription>
                    {messages["companies.duplicates"]}
                    <ul className="flex flex-wrap gap-2">
                      {duplicates.list.map((item) => (
                        <li key={item.id}>
                          <Button asChild variant="link" size="sm">
                            <Link href={companyHref(item.id)}>{item.name}</Link>
                          </Button>
                        </li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              ) : null}
              <div className="flex gap-2">
                <Button type="submit">{messages["common.save"]}</Button>
                {duplicates?.canConfirm ? (
                  <Button type="button" variant="outline" onClick={() => void create(null, true)}>
                    {messages["companies.createAnyway"]}
                  </Button>
                ) : null}
              </div>
              {notice ? <p role="status">{notice}</p> : null}
            </FieldGroup>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
