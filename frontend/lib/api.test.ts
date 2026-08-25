import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError, exportCsvUrl, exportPdfUrl, fetchRankings } from "./api";

function stubFetch(impl: () => Promise<unknown>) {
  const fn = vi.fn(impl);
  vi.stubGlobal("fetch", fn);
  return fn;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("fetchRankings", () => {
  it("builds the query string with hackathon_id and top_n", async () => {
    const fetchMock = stubFetch(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ ranked: [] }),
      })
    );

    await fetchRankings("default", { topN: 5 });

    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/rankings?hackathon_id=default&top_n=5"),
      undefined
    );
  });

  it("omits shortlist params when not provided", async () => {
    const fetchMock = stubFetch(() =>
      Promise.resolve({ ok: true, status: 200, json: async () => ({}) })
    );

    await fetchRankings("demo-hack");

    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("hackathon_id=demo-hack");
    expect(url).not.toContain("top_n");
    expect(url).not.toContain("min_score");
  });
});

describe("error mapping", () => {
  it("surfaces the backend detail string with its status", async () => {
    stubFetch(() =>
      Promise.resolve({
        ok: false,
        status: 422,
        json: async () => ({
          detail: "Provide either top_n or min_score, not both.",
        }),
      })
    );

    await expect(fetchRankings("default")).rejects.toMatchObject({
      status: 422,
      message: "Provide either top_n or min_score, not both.",
    });
  });

  it("replaces opaque 429 bodies with a rate-limit explanation", async () => {
    stubFetch(() =>
      Promise.resolve({
        ok: false,
        status: 429,
        json: async () => ({ detail: "Error code: 429" }),
      })
    );

    await expect(fetchRankings("default")).rejects.toMatchObject({
      status: 429,
      message: expect.stringContaining("Rate limit"),
    });
  });

  it("maps network failures to a plain-English ApiError", async () => {
    stubFetch(() => Promise.reject(new Error("connection refused")));

    await expect(fetchRankings("default")).rejects.toBeInstanceOf(ApiError);
    await expect(fetchRankings("default")).rejects.toMatchObject({
      status: 0,
      message: "Network error — could not reach the backend.",
    });
  });

  it("falls back to a generic HTTP message when the body has no detail", async () => {
    stubFetch(() =>
      Promise.resolve({
        ok: false,
        status: 500,
        json: async () => ({}),
      })
    );

    await expect(fetchRankings("default")).rejects.toMatchObject({
      message: "Request failed (HTTP 500).",
    });
  });
});

describe("export URL builders", () => {
  it("encodes the hackathon id into the CSV URL", () => {
    expect(exportCsvUrl("sih 2026")).toBe(
      "http://localhost:8000/api/export/csv?hackathon_id=sih%202026"
    );
  });

  it("encodes the submission id into the PDF URL path", () => {
    expect(exportPdfUrl("abc/def")).toBe(
      "http://localhost:8000/api/export/submissions/abc%2Fdef/pdf"
    );
  });
});
