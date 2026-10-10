"use client";

import { useState } from "react";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DECLINE_LABEL, type DeclineReason } from "@/lib/buyers";
import { readDetail } from "@/lib/deals";
import type { MessageKey } from "@/lib/i18n/messages";
import { sendJson, useApiData } from "@/lib/use-api";
import { CompanyPicker } from "./company-picker";

type Messages = Record<MessageKey, string>;
type Option = { id: number; label: string };
type Profile = {
  sector_ids: number[];
  country_ids: number[];
  ticket_min: string | null;
  ticket_max: string | null;
  ev_ebitda_min: string | null;
  ev_ebitda_max: string | null;
  stake: "majority" | "minority" | "both" | null;
  outdated: boolean;
  portfolio: { id: number; name: string }[];
  declines: { mandate_id: number; code_name: string; reason: DeclineReason; declined_at: string }[];
  standstill_end: string | null;
  non_solicit_end: string | null;
};

const NUMBERS = [
  ["ticket_min", "investor.ticketMin"],
  ["ticket_max", "investor.ticketMax"],
  ["ev_ebitda_min", "investor.evEbitdaMin"],
  ["ev_ebitda_max", "investor.evEbitdaMax"],
] as const;
const STAKES = ["majority", "minority", "both"] as const;

function Choices({
  label,
  options,
  chosen,
  onChange,
}: {
  label: string;
  options: Option[];
  chosen: number[];
  onChange: (ids: number[]) => void;
}) {
  return (
    <fieldset className="flex flex-col gap-1">
      <legend>{label}</legend>
      <div className="flex flex-wrap gap-3">
        {options.map((option) => (
          <label key={option.id} className="flex items-center gap-1">
            <Checkbox
              checked={chosen.includes(option.id)}
              onCheckedChange={(checked) =>
                onChange(checked ? [...chosen, option.id] : chosen.filter((id) => id !== option.id))
              }
            />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function ProfileForm({ companyId, profile, messages, onSaved }: { companyId: number; profile: Profile; messages: Messages; onSaved: () => Promise<void> }) {
  const sectors = useApiData<Option[]>("/api/v1/picklists/?kind=sector");
  const countries = useApiData<Option[]>("/api/v1/picklists/?kind=country");
  const [sectorIds, setSectorIds] = useState(profile.sector_ids);
  const [countryIds, setCountryIds] = useState(profile.country_ids);
  const [numbers, setNumbers] = useState<Record<string, string>>(
    Object.fromEntries(NUMBERS.map(([key]) => [key, profile[key] ?? ""])),
  );
  const [stake, setStake] = useState<string>(profile.stake ?? "");
  const [error, setError] = useState("");

  async function save() {
    setError("");
    const response = await sendJson(`/api/v1/companies/${companyId}/investor-profile`, "PUT", {
      sector_ids: sectorIds,
      country_ids: countryIds,
      ...Object.fromEntries(Object.entries(numbers).map(([key, value]) => [key, value || null])),
      stake: stake || null,
    });
    if (response.status !== 200) {
      setError(readDetail(response.body, messages["common.saveFailed"]));
      return;
    }
    await onSaved();
  }

  return (
    <FieldGroup>
      <Choices label={messages["investor.sectors"]} options={sectors.data ?? []} chosen={sectorIds} onChange={setSectorIds} />
      <Choices
        label={messages["investor.geographies"]}
        options={countries.data ?? []}
        chosen={countryIds}
        onChange={setCountryIds}
      />
      <div className="grid gap-2 md:grid-cols-4">
        {NUMBERS.map(([key, label]) => (
          <Field key={key}>
            <FieldLabel htmlFor={`investor-${companyId}-${key}`}>{messages[label]}</FieldLabel>
            <Input
              id={`investor-${companyId}-${key}`}
              inputMode="decimal"
              value={numbers[key]}
              onChange={(event) => setNumbers({ ...numbers, [key]: event.target.value })}
            />
          </Field>
        ))}
      </div>
      <Field>
        <FieldLabel htmlFor={`investor-${companyId}-stake`}>{messages["investor.stake"]}</FieldLabel>
        <Select value={stake} onValueChange={setStake}>
          <SelectTrigger id={`investor-${companyId}-stake`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STAKES.map((value) => (
              <SelectItem key={value} value={value}>
                {messages[`investor.stake.${value}`]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      {error ? (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      ) : null}
      <div>
        <Button type="button" onClick={() => void save()}>
          {messages["common.save"]}
        </Button>
      </div>
    </FieldGroup>
  );
}

function LinkPortfolio({ companyId, messages, onLinked }: { companyId: number; messages: Messages; onLinked: () => Promise<void> }) {
  const [chosen, setChosen] = useState("");
  const [error, setError] = useState("");

  async function link() {
    setError("");
    const response = await sendJson(`/api/v1/companies/${companyId}/portfolio`, "POST", { company_id: Number(chosen) });
    if (response.status !== 200) {
      setError(readDetail(response.body, messages["common.saveFailed"]));
      return;
    }
    setChosen("");
    await onLinked();
  }

  return (
    <FieldGroup className="sm:flex-row sm:items-end">
      <CompanyPicker
        id={`portfolio-${companyId}`}
        label={messages["investor.linkPortfolio"]}
        value={chosen}
        onChange={setChosen}
        messages={messages}
        exclude={[companyId]}
        allowNone={false}
        error={error}
      />
      <Button type="button" variant="outline" disabled={!chosen} onClick={() => void link()}>
        {messages["investor.link"]}
      </Button>
    </FieldGroup>
  );
}

export function InvestorProfilePanel({ companyId, messages }: { companyId: number; messages: Messages }) {
  const profile = useApiData<Profile>(`/api/v1/companies/${companyId}/investor-profile`);
  const data = profile.data;
  if (!data) return null;
  return (
    <section className="flex flex-col gap-3" aria-label={messages["investor.title"]}>
      <h3>{messages["investor.title"]}</h3>
      {data.outdated ? (
        <Alert>
          <AlertDescription>{messages["investor.outdated"]}</AlertDescription>
        </Alert>
      ) : null}
      <ProfileForm companyId={companyId} profile={data} messages={messages} onSaved={profile.reload} />
      {data.portfolio.length ? (
        <div>
          <h4>{messages["investor.portfolio"]}</h4>
          <div className="flex flex-wrap gap-2">
            {data.portfolio.map((entity) => (
              <Badge key={entity.id} variant="outline">
                {entity.name}
              </Badge>
            ))}
          </div>
        </div>
      ) : null}
      <LinkPortfolio companyId={companyId} messages={messages} onLinked={profile.reload} />
      {data.declines.length ? (
        <div>
          <h4>{messages["investor.declines"]}</h4>
          <ul>
            {data.declines.map((decline) => (
              <li key={decline.mandate_id}>
                {decline.code_name}: {messages[DECLINE_LABEL[decline.reason]]}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {data.standstill_end || data.non_solicit_end ? (
        <div>
          <h4>{messages["investor.restrictions"]}</h4>
          {data.standstill_end ? (
            <p>
              {messages["buyers.nda.standstill"]}: {data.standstill_end}
            </p>
          ) : null}
          {data.non_solicit_end ? (
            <p>
              {messages["buyers.nda.nonSolicit"]}: {data.non_solicit_end}
            </p>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
