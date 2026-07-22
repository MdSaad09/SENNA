import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";

import { lapFrames22 } from "../../test/apiFixtures";
import CarLabels from "./CarLabels";

// drei's Html renders as a plain div here, so counting labels is counting divs
vi.mock("@react-three/fiber", async () => (await import("../../test/mockR3F")).fiberMock());
vi.mock("@react-three/drei", async () => (await import("../../test/mockR3F")).dreiMock());

afterEach(cleanup);

const cars = lapFrames22[0].cars;
const idAtPosition = (rank: number) => cars.find((car) => car.position === rank)!.id;

test("a midfield selection shows the podium plus the chosen car", () => {
  render(<CarLabels cars={cars} selectedCarId={idAtPosition(10)} />);
  expect(screen.getAllByTestId("html-label")).toHaveLength(4);
});

test("a podium selection folds into three labels", () => {
  render(<CarLabels cars={cars} selectedCarId={idAtPosition(2)} />);
  expect(screen.getAllByTestId("html-label")).toHaveLength(3);
});

test("no selection shows the podium alone", () => {
  render(<CarLabels cars={cars} selectedCarId={null} />);
  expect(screen.getAllByTestId("html-label")).toHaveLength(3);
});
