import { Holdings } from "./Holdings";
import { asArray } from "../utils/helpers";

export function Positions({ botState }) {
  // Distinct from Holdings: positions come from the live open position, not the
  // holdings list. openPosition is null when flat, so this shows its own empty state.
  return (
    <Holdings
      rows={asArray(botState?.openPosition)}
      title="Open Position"
      emptyTitle="No Open Position"
      emptyMessage="There is no open paper position right now."
    />
  );
}
