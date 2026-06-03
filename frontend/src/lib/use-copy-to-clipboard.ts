import { useCallback, useRef, useState } from "react";

/**
 * Copies text to the clipboard and tracks a brief "copied" state.
 * Returns [copied, copy] where `copied` is true for `resetMs` after a successful copy.
 */
export function useCopyToClipboard(resetMs = 2000): [boolean, (text: string) => void] {
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout>>();

  const copy = useCallback(
    (text: string) => {
      void navigator.clipboard.writeText(text).then(
        () => {
          setCopied(true);
          clearTimeout(timer.current);
          timer.current = setTimeout(() => setCopied(false), resetMs);
        },
        () => { /* permission denied or insecure context */ },
      );
    },
    [resetMs],
  );

  return [copied, copy];
}
