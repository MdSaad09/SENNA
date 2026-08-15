// The header strip's readouts: a dot and a word. `live` is the only state that gets the
// mint; everything else is furniture, because a header where four things glow tells the
// viewer nothing.

interface StatusChipProps {
  label: string;
  live?: boolean;
}

export default function StatusChip({ label, live = false }: StatusChipProps) {
  return (
    <span className="flex items-center gap-1.5 text-label uppercase">
      {live && <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-senna-accent" />}
      <span className={live ? "text-senna-accent" : "text-senna-faint"}>{label}</span>
    </span>
  );
}
