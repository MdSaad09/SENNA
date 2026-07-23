// The F-28 label budget as a pure decision: DOM labels go to the podium plus the
// selected car, nobody else. Everyone outside this list gets instanced sprite text.

export function labelledCars(
  cars: { id: number; position: number }[],
  selectedId: number | null,
): number[] {
  const shown = cars.filter((car) => car.position <= 3).map((car) => car.id);
  if (selectedId !== null && !shown.includes(selectedId)) {
    if (cars.some((car) => car.id === selectedId)) shown.push(selectedId);
  }
  return shown;
}
