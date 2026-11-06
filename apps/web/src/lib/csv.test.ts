import { describe, expect, it } from "vitest";

import { duplicateColumns, formatBytes, MAX_UPLOAD_BYTES, validateCsvFile } from "@/lib/csv";

describe("validateCsvFile", () => {
  it("accepts a CSV within the limit", () => {
    expect(validateCsvFile({ name: "Leads.CSV", size: 1024 })).toBeNull();
  });

  it("rejects other file types", () => {
    expect(validateCsvFile({ name: "leads.xlsx", size: 1024 })).toMatch(/\.csv/);
  });

  it("rejects empty files", () => {
    expect(validateCsvFile({ name: "leads.csv", size: 0 })).toMatch(/empty/);
  });

  it("rejects files over the limit and says how big they are", () => {
    expect(validateCsvFile({ name: "leads.csv", size: MAX_UPLOAD_BYTES + 1 })).toMatch(/4\.0 MB/);
  });
});

describe("formatBytes", () => {
  it("picks a readable unit", () => {
    expect(formatBytes(900)).toBe("900 B");
    expect(formatBytes(12_000)).toBe("12 KB");
    expect(formatBytes(4_000_000)).toBe("4.0 MB");
  });
});

describe("duplicateColumns", () => {
  it("finds columns mapped twice", () => {
    expect(duplicateColumns({ business_name: "A", website: "A", email: "B" })).toEqual(["A"]);
  });

  it("ignores unmapped fields", () => {
    expect(duplicateColumns({ business_name: "A", website: "" })).toEqual([]);
  });
});
