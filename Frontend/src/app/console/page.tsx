import { Suspense } from "react";

import { ConsoleScreen } from "@/components/console/ConsoleScreen";
import { LoadingState } from "@/components/States";

export default function ConsolePage() {
  // ConsoleScreen reads `?case=` via useSearchParams, which needs a Suspense
  // boundary so the rest of the route can still prerender.
  return (
    <Suspense fallback={<LoadingState rows={5} />}>
      <ConsoleScreen />
    </Suspense>
  );
}
