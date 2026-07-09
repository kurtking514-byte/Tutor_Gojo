import { Sparkles } from "lucide-react";
import CodeBlock from "./CodeBlock.jsx";

/**
 * Splits raw message content into an ordered list of text/code segments
 * on ``` fences. This is the "markdown-ready" parsing layer - it's not a
 * full markdown renderer, but it's the seam where one (e.g. react-markdown)
 * would plug in later without changing how MessageBubble is used.
 */
function parseContent(content) {
  const segments = [];
  const fenceRegex = /```(\w*)\n?([\s\S]*?)```/g;
  let lastIndex = 0;
  let match;

  while ((match = fenceRegex.exec(content)) !== null) {
    if (match.index > lastIndex) {
      segments.push({ type: "text", value: content.slice(lastIndex, match.index) });
    }
    segments.push({ type: "code", language: match[1] || "text", value: match[2].trimEnd() });
    lastIndex = fenceRegex.lastIndex;
  }

  if (lastIndex < content.length) {
    segments.push({ type: "text", value: content.slice(lastIndex) });
  }

  return segments;
}

/** Minimal inline-bold support (**text**) without dangerouslySetInnerHTML. */
function renderInline(text, keyPrefix) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={`${keyPrefix}-${i}`} className="font-semibold text-ink">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return <span key={`${keyPrefix}-${i}`}>{part}</span>;
  });
}

/**
 * Groups the lines of a text segment (a segment is already fence-free,
 * since code blocks were stripped out by parseContent) into simple
 * block-level pieces: headings, unordered/ordered lists, and paragraphs.
 * Blank lines separate blocks, same as the old paragraph-only logic.
 */
function parseTextBlocks(value) {
  const lines = value.split("\n");
  const blocks = [];
  let paragraphLines = [];
  let i = 0;

  const flushParagraph = () => {
    if (paragraphLines.length) {
      blocks.push({ type: "p", lines: paragraphLines });
      paragraphLines = [];
    }
  };

  while (i < lines.length) {
    const trimmed = lines[i].trim();

    if (trimmed === "") {
      flushParagraph();
      i++;
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,3})\s+(.*)$/);
    if (headingMatch) {
      flushParagraph();
      blocks.push({ type: "h", level: headingMatch[1].length, text: headingMatch[2] });
      i++;
      continue;
    }

    if (/^[-*]\s+/.test(trimmed)) {
      flushParagraph();
      const items = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^[-*]\s+/, ""));
        i++;
      }
      blocks.push({ type: "ul", items });
      continue;
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      flushParagraph();
      const items = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
        i++;
      }
      blocks.push({ type: "ol", items });
      continue;
    }

    paragraphLines.push(lines[i]);
    i++;
  }
  flushParagraph();

  return blocks;
}

const HEADING_CLASSES = {
  1: "text-lg font-semibold text-ink",
  2: "text-base font-semibold text-ink",
  3: "text-[15px] font-semibold text-ink",
};

function TextBlock({ value }) {
  const blocks = parseTextBlocks(value);

  return (
    <>
      {blocks.map((block, i) => {
        if (block.type === "h") {
          const Tag = `h${block.level}`;
          return (
            <Tag key={i} className={`${HEADING_CLASSES[block.level]} [&:not(:last-child)]:mb-2`}>
              {renderInline(block.text, `h-${i}`)}
            </Tag>
          );
        }

        if (block.type === "ul") {
          return (
            <ul key={i} className="list-disc space-y-1 pl-5 leading-relaxed [&:not(:last-child)]:mb-3">
              {block.items.map((item, j) => (
                <li key={j}>{renderInline(item, `ul-${i}-${j}`)}</li>
              ))}
            </ul>
          );
        }

        if (block.type === "ol") {
          return (
            <ol key={i} className="list-decimal space-y-1 pl-5 leading-relaxed [&:not(:last-child)]:mb-3">
              {block.items.map((item, j) => (
                <li key={j}>{renderInline(item, `ol-${i}-${j}`)}</li>
              ))}
            </ol>
          );
        }

        return (
          <p key={i} className="leading-relaxed [&:not(:last-child)]:mb-3">
            {block.lines.map((line, j, arr) => (
              <span key={j}>
                {renderInline(line, `${i}-${j}`)}
                {j < arr.length - 1 && <br />}
              </span>
            ))}
          </p>
        );
      })}
    </>
  );
}

function formatTimestamp(timestamp) {
  if (!timestamp) return "";
  const date = typeof timestamp === "string" ? new Date(timestamp) : timestamp;
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export default function MessageBubble({ role, content, timestamp }) {
  const isUser = role === "user";
  const segments = parseContent(content);
  const time = formatTimestamp(timestamp);

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"} animate-fade-in-up`}>
      <div className="relative mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center">
        {!isUser && (
          <span className="absolute inset-0 animate-pulse-glow rounded-full bg-accent/40 blur-md" />
        )}
        <div
          className={`relative flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold ${
            isUser ? "bg-elevated text-ink-muted" : "bg-accent text-white shadow-glow"
          }`}
        >
          {isUser ? "You" : <Sparkles size={15} />}
        </div>
      </div>

      <div className={`flex max-w-[75%] flex-col ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-[15px] ${
            isUser
              ? "rounded-tr-sm bg-accent text-white"
              : "rounded-tl-sm border border-hairline bg-elevated text-ink"
          }`}
        >
          {segments.map((seg, i) =>
            seg.type === "code" ? (
              <CodeBlock key={i} language={seg.language} code={seg.value} />
            ) : (
              <TextBlock key={i} value={seg.value} />
            )
          )}
        </div>
        {time && <span className="mt-1 px-1 text-[11px] text-ink-muted">{time}</span>}
      </div>
    </div>
  );
}
