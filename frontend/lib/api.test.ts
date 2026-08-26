import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  exportCsvUrl,
  exportPdfUrl,
  fetchRankings,
  generatePendingFeedback,
  uploadSubmission,
} from "./api";

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

  it("carries an explicit top_n cutoff into the CSV URL", () => {
    expect(exportCsvUrl("default", { topN: 3 })).toBe(
      "http://localhost:8000/api/export/csv?hackathon_id=default&top_n=3"
    );
  });

  it("carries min_score into the CSV URL when given", () => {
    expect(exportCsvUrl("default", { minScore: 7.5 })).toBe(
      "http://localhost:8000/api/export/csv?hackathon_id=default&min_score=7.5"
    );
  });

  it("encodes the submission id into the PDF URL path", () => {
    expect(exportPdfUrl("abc/def")).toBe(
      "http://localhost:8000/api/export/submissions/abc%2Fdef/pdf?hackathon_id=default"
    );
  });

  it("carries hackathon_id and top_n into the PDF URL", () => {
    expect(exportPdfUrl("abc", { hackathonId: "sih", topN: 3 })).toBe(
      "http://localhost:8000/api/export/submissions/abc/pdf?hackathon_id=sih&top_n=3"
    );
  });
});

describe("uploadSubmission", () => {
  const FILE = new File(["pdf-bytes"], "proposal.pdf", {
    type: "application/pdf",
  });

  it("posts multipart form data including team_email", async () => {
    const fetchMock = stubFetch(() =>
      Promise.resolve({
        ok: true,
        status: 201,
        json: async () => ({ id: "sub-1", team_name: "Team Alpha" }),
      })
    );

    await uploadSubmission("Team Alpha", "team@example.com", FILE);

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://localhost:8000/api/submissions");
    expect(init.method).toBe("POST");
    const body = init.body as FormData;
    expect(body.get("team_name")).toBe("Team Alpha");
    expect(body.get("team_email")).toBe("team@example.com");
    expect(body.get("file")).toBeTruthy();
    // No replace flag unless explicitly requested.
    expect(body.get("replace_existing")).toBeNull();
  });

  it("appends replace_existing when a replacement was confirmed", async () => {
    const fetchMock = stubFetch(() =>
      Promise.resolve({
        ok: true,
        status: 201,
        json: async () => ({ id: "sub-2", team_name: "Team Alpha" }),
      })
    );

    await uploadSubmission("Team Alpha", "team@example.com", FILE, {
      replaceExisting: true,
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect((init.body as FormData).get("replace_existing")).toBe("true");
  });

  it("surfaces the backend 409 detail for the replace-confirm flow", async () => {
    stubFetch(() =>
      Promise.resolve({
        ok: false,
        status: 409,
        json: async () => ({
          detail: "Team 'X' already has an active submission.",
        }),
      })
    );

    await expect(
      uploadSubmission("X", "x@example.com", FILE)
    ).rejects.toMatchObject({
      status: 409,
      message: "Team 'X' already has an active submission.",
    });
  });

  it("maps network failures to the friendly message", async () => {
    stubFetch(() => Promise.reject(new Error("connection refused")));

    await expect(
      uploadSubmission("X", "x@example.com", FILE)
    ).rejects.toMatchObject({
      status: 0,
      message: "Network error — could not reach the backend.",
    });
  });
});

describe("generatePendingFeedback", () => {
  it("POSTs limit, hackathon_id, and top_n to the pending endpoint", async () => {
    const fetchMock = stubFetch(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          generated: 0,
          failed: 0,
          remaining: 0,
          results: [],
        }),
      })
    );

    await generatePendingFeedback(5, { hackathonId: "sih", topN: 3 });

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(
      "http://localhost:8000/api/submissions/feedback-pending?limit=5&hackathon_id=sih&top_n=3"
    );
    expect(init.method).toBe("POST");
  });

  it("falls back to the default hackathon and cutoff", async () => {
    const fetchMock = stubFetch(() =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({
          generated: 0,
          failed: 0,
          remaining: 0,
          results: [],
        }),
      })
    );

    await generatePendingFeedback(10);

    const [url] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("limit=10");
    expect(url).toContain("hackathon_id=default");
    expect(url).toContain("top_n=5");
  });
});
