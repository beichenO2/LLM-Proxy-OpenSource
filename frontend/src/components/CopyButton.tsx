import { useCopyToClipboard } from "../lib/use-copy-to-clipboard";

/**
 * Small inline button that copies `text` to the clipboard
 * and shows a brief check-mark confirmation.
 */
export default function CopyButton({ text }: { text: string }) {
  const [copied, copy] = useCopyToClipboard();
  return (
    <button
      type="button"
      onClick={() => copy(text)}
      title="复制到剪贴板"
      className="ml-1.5 inline-flex shrink-0 items-center rounded p-0.5 text-neutral-400 transition-colors hover:text-neutral-600"
    >
      {copied ? (
        <svg className="h-3.5 w-3.5 text-emerald-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
        </svg>
      )}
      <span className="sr-only">{copied ? "已复制" : "复制"}</span>
    </button>
  );
}
