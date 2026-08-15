// The numbers that belong beside the cars.
//
// Before this, the replay was 22 shapes moving round a loop with nothing to read: no
// order, no gaps, no tyre state. Every figure here is already in the frame the scene is
// drawing from (CarState: position, gap_ahead_s, compound, tyre_age, in_pit) — it was
// simply never rendered. Nothing is computed here that the server did not send.

import type { CarState } from "../api/types";
import { carLivery } from "../config/liveries";
import { COMPOUND_COLOURS } from "../config/palette";

interface TimingTowerProps {
  cars: CarState[];
  /** the car the dashboard is about; it gets the accent row */
  egoId: number;
  onSelect?: (id: number) => void;
  selectedId?: number | null;
}

function gapLabel(car: CarState): string {
  if (car.position === 1) return "leader";
  if (car.gap_ahead_s === null) return "—";
  return `+${car.gap_ahead_s.toFixed(1)}`;
}

export default function TimingTower({ cars, egoId, onSelect, selectedId }: TimingTowerProps) {
  const order = [...cars].sort((a, b) => a.position - b.position);

  return (
    <table data-testid="timing-tower" className="w-full border-collapse text-label">
      <thead>
        <tr className="text-micro uppercase text-senna-faint">
          <th scope="col" className="py-1 pl-2 text-left font-normal">
            Pos
          </th>
          <th scope="col" className="py-1 text-left font-normal">
            Car
          </th>
          <th scope="col" className="py-1 pr-2 text-right font-normal">
            Gap
          </th>
          <th scope="col" className="py-1 pr-2 text-right font-normal">
            Tyre
          </th>
        </tr>
      </thead>
      <tbody>
        {order.map((car) => {
          const livery = carLivery(car.id);
          const isEgo = car.id === egoId;
          const isSelected = car.id === selectedId;
          return (
            <tr
              key={car.id}
              data-car={car.id}
              onClick={onSelect === undefined ? undefined : () => onSelect(car.id)}
              className={`border-b border-senna-line/40 last:border-b-0 ${
                isEgo ? "bg-senna-accent/10" : isSelected ? "bg-senna-raised" : ""
              } ${onSelect === undefined ? "" : "cursor-pointer hover:bg-senna-raised"}`}
            >
              <td className="py-1 pl-2 text-senna-faint">{car.position}</td>
              <td className="py-1">
                <span className="flex items-center gap-1.5">
                  <span
                    aria-hidden
                    className="h-3 w-[3px] shrink-0"
                    style={{ backgroundColor: livery.colour }}
                  />
                  <span className={isEgo ? "text-senna-accent" : "text-senna-muted"}>
                    {livery.code}
                  </span>
                  {car.in_pit && <span className="text-micro uppercase text-senna-danger">pit</span>}
                </span>
              </td>
              <td className="py-1 pr-2 text-right text-senna-text">{gapLabel(car)}</td>
              <td className="py-1 pr-2 text-right">
                <span className="flex items-center justify-end gap-1.5">
                  <span className="text-senna-faint">{car.tyre_age}L</span>
                  <span
                    aria-hidden
                    title={car.compound}
                    className="h-2 w-2 shrink-0"
                    style={{ backgroundColor: COMPOUND_COLOURS[car.compound] ?? "transparent" }}
                  />
                </span>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
