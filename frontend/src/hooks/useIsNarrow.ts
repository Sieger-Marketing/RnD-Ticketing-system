import { useEffect, useState } from "react";

/**
 * True on phone-width screens.
 *
 * Charts need this because some decisions cannot be made in CSS: how many axis
 * ticks fit, how tall a plot should be, whether a legend has room. Everything
 * that *can* be done with a breakpoint class is, and only these render-time
 * choices come through here.
 */
export function useIsNarrow(query = "(max-width: 639px)"): boolean {
  const [narrow, setNarrow] = useState(
    () => typeof window !== "undefined" && window.matchMedia(query).matches,
  );

  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = (event: MediaQueryListEvent) => setNarrow(event.matches);
    setNarrow(list.matches);
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);

  return narrow;
}
