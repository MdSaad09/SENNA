import { expect, test } from "vitest";

import { EGO_CAR_ID, MAX_HTML_LABELS } from "../config/constants";
import { mulberry32 } from "../test/prng";
import { egoOnlyLabels, labelledCars } from "./labels";

interface GridCar {
  id: number;
  position: number;
}

function shuffledGrid(size: number, rng: () => number): GridCar[] {
  const ranks = Array.from({ length: size }, (_, i) => i + 1);
  for (let i = ranks.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [ranks[i], ranks[j]] = [ranks[j], ranks[i]];
  }
  return ranks.map((position, id) => ({ id, position }));
}

const podiumIds = (cars: GridCar[]) =>
  cars.filter((car) => car.position <= 3).map((car) => car.id);

const ABSENT_ID = 999;
const BASE_SEED = 9_100;
const TRIALS_PER_SIZE = 20;

// Seeded property loop over every grid size 1..22 (era-2024 grids have 20 cars,
// nothing may assume 22): the F-28 label budget holds for any selection state.

test("the label list never exceeds the budget and always contains the podium", () => {
  for (let size = 1; size <= 22; size++) {
    for (let trial = 0; trial < TRIALS_PER_SIZE; trial++) {
      const seed = BASE_SEED + size * 100 + trial;
      const rng = mulberry32(seed);
      const label = `seed ${seed}`;
      const cars = shuffledGrid(size, rng);
      const podium = podiumIds(cars);

      const selections: (number | null)[] = [
        null,
        ABSENT_ID,
        podium[Math.floor(rng() * podium.length)],
        cars[Math.floor(rng() * size)].id,
      ];
      for (const selected of selections) {
        const shown = labelledCars(cars, selected);
        expect(shown.length, label).toBeLessThanOrEqual(MAX_HTML_LABELS);
        expect(new Set(shown).size, label).toBe(shown.length);
        for (const id of podium) {
          expect(shown, `${label} selected ${selected}`).toContain(id);
        }
      }
    }
  }
});

test("a podium selection folds into the three podium labels", () => {
  for (let size = 3; size <= 22; size++) {
    const seed = BASE_SEED + size;
    const rng = mulberry32(seed);
    const cars = shuffledGrid(size, rng);
    const podium = podiumIds(cars);
    const selected = podium[Math.floor(rng() * 3)];

    const shown = labelledCars(cars, selected);
    expect(shown, `seed ${seed}`).toHaveLength(3);
    expect(shown, `seed ${seed}`).toContain(selected);
  }
});

test("a midfield selection adds exactly one label beyond the podium", () => {
  for (let size = 4; size <= 22; size++) {
    const seed = BASE_SEED + 50_000 + size;
    const rng = mulberry32(seed);
    const cars = shuffledGrid(size, rng);
    const midfield = cars.filter((car) => car.position > 3);
    const selected = midfield[Math.floor(rng() * midfield.length)].id;

    const shown = labelledCars(cars, selected);
    expect(shown, `seed ${seed}`).toHaveLength(4);
    expect(shown, `seed ${seed}`).toContain(selected);
  }
});

test("no selection, or an id not in the grid, shows just the podium", () => {
  for (const size of [1, 2, 3, 12, 22]) {
    const cars = shuffledGrid(size, mulberry32(BASE_SEED + 90_000 + size));
    expect(labelledCars(cars, null), `size ${size}`).toHaveLength(Math.min(3, size));
    expect(labelledCars(cars, ABSENT_ID), `size ${size}`).toHaveLength(Math.min(3, size));
  }
});

// F13: each counterfactual pane DOM-labels only the ego (plan, View 6 labels)

test("egoOnlyLabels labels exactly the ego, whatever else is selected", () => {
  for (const size of [20, 22]) {
    const cars = shuffledGrid(size, mulberry32(BASE_SEED + 70_000 + size));
    expect(egoOnlyLabels(cars, null), `size ${size}`).toEqual([EGO_CAR_ID]);
    // a selection must not widen the pane's list past the ego
    expect(egoOnlyLabels(cars, 5), `size ${size}`).toEqual([EGO_CAR_ID]);
  }
});

test("two panes of ego-only labels fit the F-28 budget together", () => {
  const cars = shuffledGrid(20, mulberry32(BASE_SEED + 80_000));
  expect(2 * egoOnlyLabels(cars, null).length).toBeLessThanOrEqual(MAX_HTML_LABELS);
});
