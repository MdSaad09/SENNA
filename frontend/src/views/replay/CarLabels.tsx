// The four DOM labels the budget allows (F-28): podium plus the selected car,
// decided by the pure labelledCars selector the property tests pin. Positions are
// written imperatively each frame so React never renders at frame rate; drei's
// Html reprojects itself from the parent group's world matrix.

import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { useRef } from "react";
import type { Group } from "three";

import type { CarState } from "../../api/types";
import { EGO_CAR_ID, LABEL_HEIGHT_M } from "../../config/constants";
import { carLivery } from "../../config/liveries";
import { labelledCars } from "../../lib/labels";

interface CarLabelsProps {
  cars: CarState[];
  selectedCarId?: number | null;
  // the caller may hand the decided list so scene sprites and DOM labels agree;
  // View 6's baseline pane also clears the badge — its car 0 replays the real
  // strategy and must never read "agent" (F-24 honesty)
  labelledIds?: number[];
  egoBadge?: string | null;
  positionOf?: (carId: number) => [number, number, number];
}

export default function CarLabels({
  cars,
  selectedCarId = null,
  labelledIds,
  egoBadge = "agent",
  positionOf,
}: CarLabelsProps) {
  const slots = useRef(new Map<number, Group>());
  const shown = labelledIds ?? labelledCars(cars, selectedCarId);

  useFrame(() => {
    if (positionOf === undefined) return;
    for (const [carId, group] of slots.current) {
      const [x, y, z] = positionOf(carId);
      group.position.set(x, y, z + LABEL_HEIGHT_M);
    }
  });

  return (
    <>
      {shown.map((carId) => {
        const car = cars.find((entry) => entry.id === carId);
        const livery = carLivery(carId);
        return (
          <group
            key={carId}
            ref={(group) => {
              if (group === null) slots.current.delete(carId);
              else slots.current.set(carId, group);
            }}
          >
            <Html center zIndexRange={[10, 0]}>
              <div
                className="pointer-events-none whitespace-nowrap rounded px-1.5 py-0.5 font-mono text-xs"
                style={{ backgroundColor: "#171717e6", color: livery.colour }}
              >
                {livery.code}
                {car !== undefined && ` P${car.position}`}
                {carId === EGO_CAR_ID && egoBadge !== null && ` ${egoBadge}`}
              </div>
            </Html>
          </group>
        );
      })}
    </>
  );
}
