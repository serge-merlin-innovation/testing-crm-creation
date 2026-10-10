"use client";

import { useState, type FormEvent } from "react";
import Link from "next/link";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { readDetail } from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import { canSearch, searchQuery, splitName, type Criteria } from "@/lib/search";
import { sendJson, useApiData } from "@/lib/use-api";
import { apiFetch } from "@/services/api";

type Messages = Record<MessageKey, string>;
type Holder = { user_id: number; name: string; strength: number };
type Results = {
  companies: { id: number; name: string; type: string }[];
  contacts: { id: number; first_name: string; last_name: string; email: string | null; relationship_holders: Holder[] }[];
  deals: { id: number; code_name: string; stage: string }[];
};
type SavedFilter = { id: number; name: string; owner_name: string; shared: boolean; criteria: Criteria };
type Option = { id: number; label: string };

const COMPANY_TYPES = ["target", "strategic_buyer", "financial_investor", "lender", "advisor", "other"];
const ANY = "any";

export function SearchView({ messages }: { messages: Messages }) {
  const [text, setText] = useState("");
  const [companyType, setCompanyType] = useState(ANY);
  const [countryId, setCountryId] = useState(ANY);
  const [evMin, setEvMin] = useState("");
  const [evMax, setEvMax] = useState("");
  const [filterId, setFilterId] = useState<number | null>(null);
  const [results, setResults] = useState<Results | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filterName, setFilterName] = useState("");
  const [share, setShare] = useState(false);
  const [strength, setStrength] = useState<Record<number, string>>({});
  const filters = useApiData<SavedFilter[]>("/api/v1/saved-filters/");
  const countries = useApiData<Option[]>("/api/v1/picklists/?kind=country");

  const criteria: Criteria = {
    q: text,
    company_types: companyType === ANY ? [] : [companyType],
    country_ids: countryId === ANY ? [] : [Number(countryId)],
    ev_min: evMin || null,
    ev_max: evMax || null,
  };

  async function run(using: Criteria, savedId: number | null) {
    setError("");
    if (!canSearch(using, savedId)) {
      setResults(null);
      setError(messages["search.hint"]);
      return;
    }
    const response = await apiFetch(`/api/v1/search/?${searchQuery(using, savedId)}`).catch(() => null);
    if (!response?.ok) {
      setResults(null);
      setError(messages["common.loadFailed"]);
      return;
    }
    setResults((await response.json()) as Results);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice("");
    await run(criteria, filterId);
  }

  async function saveFilter() {
    const result = await sendJson("/api/v1/saved-filters/", "POST", {
      name: filterName,
      criteria: { ...criteria, q: text || null },
      shared: share,
    });
    if (result.status === 201) {
      setNotice(messages["search.filterSaved"]);
      setFilterName("");
      await filters.reload();
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  async function toggleShare(saved: SavedFilter) {
    await sendJson(`/api/v1/saved-filters/${saved.id}/shared`, "PUT", { shared: !saved.shared });
    await filters.reload();
  }

  async function createContact() {
    const result = await sendJson("/api/v1/contacts/", "POST", { ...splitName(text), source: "Search" });
    if (result.status === 201) {
      setNotice(messages["contacts.created"]);
      await run(criteria, filterId);
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  async function createCompany() {
    const country = countryId === ANY ? null : Number(countryId);
    const result = await sendJson("/api/v1/companies/", "POST", {
      name: text.trim(),
      type: companyType === ANY ? "target" : companyType,
      country_id: country,
    });
    if (result.status === 201) {
      setNotice(messages["companies.created"]);
      await run(criteria, filterId);
      return;
    }
    setError(readDetail(result.body, messages["common.saveFailed"]));
  }

  async function addMe(contactId: number) {
    const result = await sendJson(`/api/v1/contacts/${contactId}/relationship-holders/me`, "PUT", {
      strength: Number(strength[contactId] ?? "2"),
    });
    if (result.status === 200) {
      setNotice(messages["search.relationshipSaved"]);
      await run(criteria, filterId);
    }
  }

  const empty = results && !results.companies.length && !results.contacts.length && !results.deals.length;

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardHeader>
          <CardTitle>
            <h1>{messages["search.title"]}</h1>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={(event) => void submit(event)}>
            <FieldGroup>
              <Field>
                <FieldLabel htmlFor="search-text">{messages["common.search"]}</FieldLabel>
                <Input id="search-text" value={text} onChange={(event) => setText(event.target.value)} />
              </Field>
              <div className="grid gap-4 md:grid-cols-4">
                <Field>
                  <FieldLabel htmlFor="search-type">{messages["search.companyType"]}</FieldLabel>
                  <Select value={companyType} onValueChange={setCompanyType}>
                    <SelectTrigger id="search-type">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ANY}>{messages["search.any"]}</SelectItem>
                      {COMPANY_TYPES.map((value) => (
                        <SelectItem key={value} value={value}>
                          {value}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <Field>
                  <FieldLabel htmlFor="search-country">{messages["companies.country"]}</FieldLabel>
                  <Select value={countryId} onValueChange={setCountryId}>
                    <SelectTrigger id="search-country">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ANY}>{messages["search.any"]}</SelectItem>
                      {(countries.data ?? []).map((country) => (
                        <SelectItem key={country.id} value={String(country.id)}>
                          {country.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Field>
                <Field>
                  <FieldLabel htmlFor="search-ev-min">{messages["search.evMin"]}</FieldLabel>
                  <Input id="search-ev-min" inputMode="numeric" value={evMin} onChange={(e) => setEvMin(e.target.value)} />
                </Field>
                <Field>
                  <FieldLabel htmlFor="search-ev-max">{messages["search.evMax"]}</FieldLabel>
                  <Input id="search-ev-max" inputMode="numeric" value={evMax} onChange={(e) => setEvMax(e.target.value)} />
                </Field>
              </div>
              <Button type="submit">{messages["common.search"]}</Button>
            </FieldGroup>
          </form>
        </CardContent>
      </Card>

      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      {notice ? <p role="status">{notice}</p> : null}

      {empty ? (
        <Card>
          <CardContent className="flex flex-wrap items-center gap-2">
            <p>{messages["search.noResults"]}</p>
            <Button variant="outline" onClick={() => void createContact()}>
              {messages["search.createContact"]}
            </Button>
            <Button variant="outline" onClick={() => void createCompany()} disabled={countryId === ANY}>
              {messages["search.createCompany"]}
            </Button>
          </CardContent>
        </Card>
      ) : null}

      {results && !empty ? (
        <div className="grid gap-4 md:grid-cols-3">
          <Card>
            <CardHeader>
              <CardTitle>
                <h2>{messages["search.companies"]}</h2>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul aria-label={messages["search.companies"]} className="flex flex-col gap-2">
                {results.companies.map((company) => (
                  <li key={company.id}>
                    {company.name} <Badge variant="secondary">{company.type}</Badge>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>
                <h2>{messages["search.contacts"]}</h2>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul aria-label={messages["search.contacts"]} className="flex flex-col gap-4">
                {results.contacts.map((contact) => (
                  <li key={contact.id} className="flex flex-col gap-2">
                    <span>
                      {contact.first_name} {contact.last_name}
                    </span>
                    {contact.relationship_holders.length ? (
                      <span>
                        {messages["search.knownBy"]}:{" "}
                        {contact.relationship_holders.map((holder) => (
                          <Badge key={holder.user_id} variant="outline">
                            {holder.name} ({holder.strength}/3)
                          </Badge>
                        ))}
                      </span>
                    ) : null}
                    <div className="flex gap-2">
                      <Select
                        value={strength[contact.id] ?? "2"}
                        onValueChange={(value) => setStrength((current) => ({ ...current, [contact.id]: value }))}
                      >
                        <SelectTrigger aria-label={`${messages["search.myStrength"]} ${contact.last_name}`}>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="1">{messages["search.strength1"]}</SelectItem>
                          <SelectItem value="2">{messages["search.strength2"]}</SelectItem>
                          <SelectItem value="3">{messages["search.strength3"]}</SelectItem>
                        </SelectContent>
                      </Select>
                      <Button size="sm" variant="outline" onClick={() => void addMe(contact.id)}>
                        {messages["search.addMe"]}
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>
                <h2>{messages["search.deals"]}</h2>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <ul aria-label={messages["search.deals"]} className="flex flex-col gap-2">
                {results.deals.map((deal) => (
                  <li key={deal.id}>
                    <Button asChild variant="link">
                      <Link href={`/deals/${deal.id}`}>{deal.code_name}</Link>
                    </Button>
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>
            <h2>{messages["search.savedFilters"]}</h2>
          </CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <ul className="flex flex-col gap-2">
            {(filters.data ?? []).map((saved) => (
              <li key={saved.id} className="flex flex-wrap items-center gap-2">
                <span>{saved.name}</span>
                <Badge variant="secondary">{saved.owner_name}</Badge>
                {saved.shared ? <Badge>{messages["search.shared"]}</Badge> : null}
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    setFilterId(saved.id);
                    void run({}, saved.id);
                  }}
                >
                  {messages["search.apply"]} {saved.name}
                </Button>
                <Button size="sm" variant="ghost" onClick={() => void toggleShare(saved)}>
                  {messages["search.share"]}
                </Button>
              </li>
            ))}
          </ul>
          <div className="flex flex-wrap items-end gap-2">
            <Field>
              <FieldLabel htmlFor="filter-name">{messages["search.filterName"]}</FieldLabel>
              <Input id="filter-name" value={filterName} onChange={(event) => setFilterName(event.target.value)} />
            </Field>
            <div className="flex items-center gap-2">
              <Checkbox id="filter-share" checked={share} onCheckedChange={(value) => setShare(value === true)} />
              <Label htmlFor="filter-share">{messages["search.share"]}</Label>
            </div>
            <Button onClick={() => void saveFilter()} disabled={!filterName.trim()}>
              {messages["search.saveFilter"]}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
