import { describe, expect, it } from "vitest";
import { companyPayload, contactPayload, RECORD_LANGUAGES } from "@/lib/records";

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
    });
  });
});

it("offers the three record languages", () => {
  expect(RECORD_LANGUAGES).toEqual(["en", "fr", "nl"]);
});
