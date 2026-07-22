import { useUiStore } from "../stores/uiStore";

export default function QualityToggle() {
  const bloomEnabled = useUiStore((state) => state.bloomEnabled);
  const bloomReason = useUiStore((state) => state.bloomReason);
  const setBloom = useUiStore((state) => state.setBloom);
  const on = bloomEnabled === true;

  return (
    <button
      type="button"
      onClick={() => setBloom(!on)}
      title={bloomReason || "decided when the first canvas reports its GPU"}
      className={`rounded-full border px-3 py-1 text-xs ${
        on ? "border-emerald-500 text-emerald-400" : "border-neutral-700 text-neutral-400"
      }`}
    >
      bloom {on ? "on" : "off"}
    </button>
  );
}
