import { Suspense } from "react";

import { LiveScreen } from "@/components/live/LiveScreen";
import { LoadingState } from "@/components/States";

export default function LivePage() {
  // LiveScreen reads `?case=` via useSearchParams, which needs a Suspense
  // boundary so the rest of the route can still prerender.
  return (
    <Suspense fallback={<LoadingState rows={5} />}>
      <LiveScreen />
    </Suspense>
  );
}
