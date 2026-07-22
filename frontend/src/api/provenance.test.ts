import { beforeEach, expect, test } from "vitest";

import { PROVENANCE_LOG_CAP } from "../config/constants";
import {
  clearProvenance,
  provenanceLog,
  recordProvenance,
  subscribeProvenance,
} from "./provenance";

function entryFor(path: string) {
  return { method: "GET", path, status: 200, xModelVersion: null };
}

beforeEach(clearProvenance);

test("trace ids increase monotonically", () => {
  for (let i = 0; i < 5; i++) {
    recordProvenance(entryFor(`/p${i}`));
  }
  const ids = provenanceLog().map((entry) => entry.traceId);
  expect(ids).toHaveLength(5);
  for (let i = 1; i < ids.length; i++) {
    expect(ids[i]).toBeGreaterThan(ids[i - 1]);
  }
});

test("the ring keeps only the newest PROVENANCE_LOG_CAP entries", () => {
  const recorded = PROVENANCE_LOG_CAP + 5;
  for (let i = 0; i < recorded; i++) {
    recordProvenance(entryFor(`/p${i}`));
  }
  const log = provenanceLog();
  expect(log).toHaveLength(PROVENANCE_LOG_CAP);
  // the five oldest fell off the front; the newest is still the last
  expect(log[0].path).toBe("/p5");
  expect(log[log.length - 1].path).toBe(`/p${recorded - 1}`);
});

test("subscribers hear every record until they unsubscribe", () => {
  let heard = 0;
  const unsubscribe = subscribeProvenance(() => {
    heard += 1;
  });

  recordProvenance(entryFor("/p0"));
  recordProvenance(entryFor("/p1"));
  expect(heard).toBe(2);

  unsubscribe();
  recordProvenance(entryFor("/p2"));
  expect(heard).toBe(2);
});

test("clearing empties the log", () => {
  recordProvenance(entryFor("/p0"));
  clearProvenance();
  expect(provenanceLog()).toHaveLength(0);
});
