import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { ApiError, apiGet, apiPost } from "./client";
import { clearProvenance, provenanceLog } from "./provenance";

function stubFetch(status: number, body: unknown, headers: Record<string, string> = {}) {
  const stub = vi.fn(
    async (_input: RequestInfo | URL, _init?: RequestInit) =>
      new Response(JSON.stringify(body), {
        status,
        headers: { "content-type": "application/json", ...headers },
      }),
  );
  vi.stubGlobal("fetch", stub);
  return stub;
}

beforeEach(clearProvenance);

afterEach(() => {
  vi.unstubAllGlobals();
});

test("requests resolve against the default /api base (F-27)", async () => {
  const stub = stubFetch(200, []);
  await apiGet("/v1/circuits");
  expect(stub.mock.calls[0][0]).toBe("/api/v1/circuits");
});

test("a GET returns the parsed body", async () => {
  stubFetch(200, { run_id: 7, status: "complete" });
  await expect(apiGet("/v1/simulations/7")).resolves.toEqual({
    run_id: 7,
    status: "complete",
  });
});

test("every response lands in the provenance log with its ids (5.1 invariant 2)", async () => {
  stubFetch(
    200,
    { run_id: 7, model_version: "model-2026.07", env_config_hash: "abc123", status: "complete" },
    { "X-Model-Version": "model-2026.07" },
  );
  await apiGet("/v1/simulations/7");

  const entry = provenanceLog().at(-1);
  expect(entry).toMatchObject({
    method: "GET",
    path: "/v1/simulations/7",
    status: 200,
    xModelVersion: "model-2026.07",
    runId: 7,
    modelVersion: "model-2026.07",
    envConfigHash: "abc123",
  });
});

test("a missing X-Model-Version header records as null", async () => {
  stubFetch(200, [{ id: "bahrain_grand_prix" }]);
  await apiGet("/v1/circuits");
  expect(provenanceLog().at(-1)?.xModelVersion).toBeNull();
});

test("a POST sends the JSON body and records POST provenance", async () => {
  const stub = stubFetch(200, { run_id: 9 });
  const request = { circuit_id: "bahrain_grand_prix", grid_position: 8 };

  await expect(apiPost("/v1/simulations", request)).resolves.toEqual({ run_id: 9 });

  const [url, init] = stub.mock.calls[0];
  expect(url).toBe("/api/v1/simulations");
  expect(init?.method).toBe("POST");
  expect(JSON.parse(String(init?.body))).toEqual(request);
  expect(provenanceLog().at(-1)).toMatchObject({
    method: "POST",
    path: "/v1/simulations",
    status: 200,
  });
});

test("a non-ok response throws ApiError with the status and detail", async () => {
  stubFetch(422, { detail: "grid_position must be between 1 and 22" });

  const failure = await apiGet("/v1/simulations").then(
    () => null,
    (thrown: unknown) => thrown,
  );
  expect(failure).toBeInstanceOf(ApiError);
  expect((failure as ApiError).status).toBe(422);
  expect(String((failure as ApiError).message)).toContain("grid_position");

  // failures are traced too — an error the overlay cannot attribute is a black box
  expect(provenanceLog().at(-1)).toMatchObject({
    method: "GET",
    path: "/v1/simulations",
    status: 422,
  });
});
