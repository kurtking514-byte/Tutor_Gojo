import { useMemo, useState } from "react";
import { Check, Copy } from "lucide-react";
import hljs from "highlight.js/lib/core";
import javascript from "highlight.js/lib/languages/javascript";
import typescript from "highlight.js/lib/languages/typescript";
import python from "highlight.js/lib/languages/python";
import bash from "highlight.js/lib/languages/bash";
import json from "highlight.js/lib/languages/json";
import css from "highlight.js/lib/languages/css";
import xml from "highlight.js/lib/languages/xml";
import sql from "highlight.js/lib/languages/sql";
// Dark theme that matches the existing #100F1C code block background.
import "highlight.js/styles/atom-one-dark.css";

// Only registering the languages Tutor Gojo actually needs to keep
// this lightweight - highlight.js/lib/core ships with zero languages
// built in, so nothing unused gets bundled.
hljs.registerLanguage("javascript", javascript);
hljs.registerLanguage("js", javascript);
hljs.registerLanguage("jsx", javascript);
hljs.registerLanguage("typescript", typescript);
hljs.registerLanguage("ts", typescript);
hljs.registerLanguage("tsx", typescript);
hljs.registerLanguage("python", python);
hljs.registerLanguage("py", python);
hljs.registerLanguage("bash", bash);
hljs.registerLanguage("sh", bash);
hljs.registerLanguage("shell", bash);
hljs.registerLanguage("json", json);
hljs.registerLanguage("css", css);
hljs.registerLanguage("html", xml);
hljs.registerLanguage("xml", xml);
hljs.registerLanguage("sql", sql);

/**
 * Renders a fenced code block with a language label, copy button, and
 * syntax highlighting via highlight.js. The `language` prop comes from
 * the ```lang fence parsed upstream in MessageBubble.jsx and is used
 * directly when highlight.js recognizes it; otherwise falls back to
 * highlight.js's own auto-detection, and finally to plain text if
 * highlighting fails for any reason.
 */
export default function CodeBlock({ language = "text", code = "" }) {
  const [copied, setCopied] = useState(false);

  const highlightedHtml = useMemo(() => {
    const lang = (language || "").toLowerCase().trim();
    try {
      if (lang && lang !== "text" && hljs.getLanguage(lang)) {
        return hljs.highlight(code, { language: lang }).value;
      }
      return hljs.highlightAuto(code).value;
    } catch {
      return null;
    }
  }, [code, language]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API can fail silently (e.g. insecure context) - no-op.
    }
  };

  return (
    <div className="my-3 overflow-hidden rounded-lg border border-hairline bg-[#100F1C]">
      <div className="flex items-center justify-between border-b border-hairline px-3 py-1.5">
        <span className="font-mono text-xs text-ink-muted">{language}</span>
        <button
          onClick={handleCopy}
          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-ink-muted transition-colors hover:bg-elevated hover:text-ink"
        >
          {copied ? (
            <>
              <Check size={13} className="text-accent-soft" />
              Copied
            </>
          ) : (
            <>
              <Copy size={13} />
              Copy
            </>
          )}
        </button>
      </div>

      <pre className="scrollbar-thin overflow-x-auto px-4 py-3">
        {highlightedHtml != null ? (
          <code
            className="hljs !bg-transparent font-mono text-[13px] leading-relaxed"
            dangerouslySetInnerHTML={{ __html: highlightedHtml }}
          />
        ) : (
          <code className="font-mono text-[13px] leading-relaxed text-ink">{code}</code>
        )}
      </pre>
    </div>
  );
}
