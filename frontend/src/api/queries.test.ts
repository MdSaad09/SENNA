import { afterEach, expect, test, vi } from "vitest";

import { FRAMES_PAGE_SIZE } from "../config/constants";
import { fetchAllFrames } from "./queries";

// minimal frames: the loop only cares about page lengths and lap numbers
const frame = (lap: number) => ({ lap, cars: [], agent: {}, events: [] });

function stubFrames(totalLaps: number) {
  const stub = vi.fn(async (input: RequestInfo | URL) => {
    const params = new URL(String(input), "http://stub").searchParams;
    const fromLap = Number(params.get("from_lap"));
    const toLap = Number(params.get("to_lap"));
    const page = [];
    for (let lap = fromLap; lap <= Math.min(toLap, totalLaps); lap++) page.push(frame(lap));
    return new Response(JSON.stringify(page), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", stub);
  return stub;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("a short race is one page and the loop stops on it", async () => {
  const stub = stubFrames(57);
  const frames = await fetchAllFrames(7);
  expect(frames).toHaveLength(57);
  expect(stub).toHaveBeenCalledTimes(1);
  expect(String(stub.mock.calls[0][0])).toContain("from_lap=1&to_lap=100");
});

test("a race longer than a page walks sequential pages to the end", async () => {
  const stub = stubFrames(FRAMES_PAGE_SIZE + 50);
  const frames = await fetchAllFrames(7);
  expect(frames).toHaveLength(FRAMES_PAGE_SIZE + 50);
  expect(frames[0].lap).toBe(1);
  expect(frames[frames.length - 1].lap).toBe(FRAMES_PAGE_SIZE + 50);
  expect(stub).toHaveBeenCalledTimes(2);
  expect(String(stub.mock.calls[1][0])).toContain(`from_lap=${FRAMES_PAGE_SIZE + 1}`);
});

test("an exactly-page-size race costs one extra empty request, then stops", async () => {
  const stub = stubFrames(FRAMES_PAGE_SIZE);
  const frames = await fetchAllFrames(7);
  expect(frames).toHaveLength(FRAMES_PAGE_SIZE);
  expect(stub).toHaveBeenCalledTimes(2);
});
