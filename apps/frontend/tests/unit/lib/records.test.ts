import { describe, expect, it } from "vitest";
import {
  companyHref,
  companyPayload,
  contactPayload,
  employmentRows,
  financialPayload,
  groupIds,
  RECORD_LANGUAGES,
} from "@/lib/records";

describe("contactPayload", () => {
  it("sends language, salutation, opt-out and Do not contact with the contact", () => {
    expect(
      contactPayload(
        { first_name: "Ines", last_name: "Maes", email: "", phone: "", source: "Forum", function: "", salutation: " Madame " },
        { companyId: null, language: "fr", marketingOptOut: true, doNotContact: true },
      ),
    ).toEqual({
      first_name: "Ines",
      last_name: "Maes",
      email: null,
      phone: null,
      source: "Forum",
      function: null,
      company_id: null,
      language: "fr",
      marketing_opt_out: true,
      do_not_contact: true,
      salutation: "Madame",
    });
  });
});

describe("companyPayload", () => {
  it("puts the number in the field the country needs and sends the language", () => {
    expect(
      companyPayload({ name: "Acme", type: "target", countryId: "3", number: "0123", belgian: true, language: "nl" }, false),
    ).toEqual({
      name: "Acme",
      type: "target",
      country_id: 3,
      ignore_similar: false,
      enterprise_number: "0123",
      language: "nl",
      address: null,
      legal_form: null,
      nace_code: null,
    });
  });
});

it("offers the three record languages", () => {
  expect(RECORD_LANGUAGES).toEqual(["en", "fr", "nl"]);
});

describe("company pre-fill and links", () => {
  it("sends the register's address, legal form and NACE code", () => {
    expect(
      companyPayload(
        {
          name: "Acme",
          type: "target",
          countryId: "1",
          number: "0123",
          belgian: true,
          language: "en",
          address: " Rue Royale 1 ",
          legalForm: "SA",
          naceCode: "62010",
        },
        false,
      ),
    ).toMatchObject({ address: "Rue Royale 1", legal_form: "SA", nace_code: "62010" });
  });

  it("links a duplicate to its company page", () => {
    expect(companyHref(42)).toBe("/companies/42");
  });
});

describe("financialPayload", () => {
  it("leaves blank figures out and sends EUR without a rate", () => {
    expect(
      financialPayload({ revenue: "1200", ebitda: "", net_debt: " ", fte: "12", currency: "", eurRate: "0.9" }),
    ).toEqual({ revenue: "1200", fte: "12", currency: "EUR", eur_rate: null });
  });

  it("keeps a foreign currency with its EUR rate", () => {
    expect(
      financialPayload({ revenue: "2000", ebitda: "", net_debt: "", fte: "", currency: "usd", eurRate: "0.9" }),
    ).toEqual({ revenue: "2000", currency: "USD", eur_rate: "0.9" });
  });
});

describe("group and employment", () => {
  it("lists every company in the group tree", () => {
    expect(
      groupIds({ id: 1, name: "Top", children: [{ id: 2, name: "Mid", children: [{ id: 3, name: "Low", children: [] }] }] }),
    ).toEqual([1, 2, 3]);
  });

  it("puts the current role before the history", () => {
    const current = { company_id: 2, company_name: "Two", function: "CEO", start_date: "2026-10-10", end_date: null };
    const old = { company_id: 1, company_name: "One", function: "CFO", start_date: null, end_date: "2026-10-10" };
    expect(employmentRows(current, [old])).toEqual([current, old]);
    expect(employmentRows(null, [old])).toEqual([old]);
  });
});
