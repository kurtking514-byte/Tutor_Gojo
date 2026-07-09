import { useEffect, useState } from "react";
import { fetchMemory } from "../api/client.js";
import LessonRecommendation from "./LessonRecommendation.jsx";

// Best-effort "pick a readable label out of this row" helper, since each
// memory category comes back with different field names (name/topic/
// description/summary/...). Falls back to a compact JSON dump so nothing
// silently disappears if a shape doesn't match what's expected here.
function describeItem(item, preferredFields) {
  if (item == null) return "—";
  if (typeof item === "string") return item;
  for (const field of preferredFields) {
    if (item[field]) return item[field];
  }
  return JSON.stringify(item);
}

// Declarative list of every section the dashboard renders. `key` maps
// directly to a field on the object returned by GET /memory (i.e.
// memory_service.get_memory_context()'s shape) - nothing here reshapes
// or recomputes that data, it only decides which field of each row to
// show as the line of text.
const LIST_SECTIONS = [
  {
    key: "topic_mastery",
    title: "Topic Mastery",
    describe: (row) => {
      const topic = describeItem(row, ["topic"]);
      const mastery = typeof row?.mastery_level === "number" ? ` — mastery ${row.mastery_level}` : "";
      return `${topic}${mastery}`;
    },
  },
  {
    key: "strengths",
    title: "Strengths",
    describe: (row) => describeItem(row, ["name"]),
  },
  {
    key: "misconceptions",
    title: "Misconceptions",
    describe: (row) => {
      const name = describeItem(row, ["name"]);
      const status = row?.status ? ` (${row.status})` : "";
      return `${name}${status}`;
    },
  },
  {
    key: "learning_preferences",
    title: "Learning Preferences",
    describe: (row) => describeItem(row, ["preference_value", "preference_key"]),
  },
  {
    key: "coding_style_traits",
    title: "Coding Style",
    describe: (row) => describeItem(row, ["trait_value", "trait_key"]),
  },
  {
    key: "mistake_patterns",
    title: "Mistake Patterns",
    describe: (row) => describeItem(row, ["description"]),
  },
  {
    key: "recent_journal_entries",
    title: "Recent Journal Entries",
    describe: (row) => describeItem(row, ["summary"]),
  },
  {
    key: "active_projects",
    title: "Projects",
    describe: (row) => {
      const name = describeItem(row, ["name"]);
      const status = row?.status ? ` (${row.status})` : "";
      return `${name}${status}`;
    },
  },
  {
    key: "assessments",
    title: "Assessments",
    describe: (row) => describeItem(row, ["question"]),
  },
  {
    key: "recent_motivational_signals",
    title: "Motivational Signals",
    describe: (row) => describeItem(row, ["pattern_description"]),
  },
  {
    key: "recent_milestones",
    title: "Milestones",
    describe: (row) => describeItem(row, ["title"]),
  },
  {
    key: "open_curiosity_backlog",
    title: "Curiosity Backlog",
    describe: (row) => describeItem(row, ["question"]),
  },
];

function SectionHeading({ children }) {
  return (
    <h2 className="mb-2 font-display text-[11px] font-medium uppercase tracking-wider text-ink-muted">
      {children}
    </h2>
  );
}

function ListSection({ title, items }) {
  const rows = Array.isArray(items) ? items : [];
  return (
    <section>
      <SectionHeading>{title}</SectionHeading>
      {rows.length === 0 ? (
        <p className="text-sm text-ink-muted">No data yet.</p>
      ) : (
        <ul className="space-y-1">
          {rows.map((row, i) => (
            <li key={i} className="text-sm text-ink">
              {row.text}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function StudentProfileSection({ profile }) {
  return (
    <section>
      <SectionHeading>Student Profile</SectionHeading>
      {!profile ? (
        <p className="text-sm text-ink-muted">No data yet.</p>
      ) : (
        <ul className="space-y-1 text-sm text-ink">
          <li>Goals: {profile.goals || "—"}</li>
          <li>Background: {profile.background || "—"}</li>
          <li>Time horizon: {profile.time_horizon || "—"}</li>
          <li>
            Preferred languages:{" "}
            {profile.preferred_languages?.length ? profile.preferred_languages.join(", ") : "—"}
          </li>
          <li>
            Domain interests:{" "}
            {profile.domain_interests?.length ? profile.domain_interests.join(", ") : "—"}
          </li>
        </ul>
      )}
    </section>
  );
}

/**
 * LearningDashboard.jsx
 *
 * Read-only view of the student's educational memory, fetched from
 * GET /memory (memory_service.get_memory_context(), unmodified). This
 * component only fetches and displays - no editing, no mutations, no
 * POST requests. Not wired into App.jsx or Sidebar navigation yet.
 */
export default function LearningDashboard() {
  const [memory, setMemory] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    setIsLoading(true);
    setError(null);

    fetchMemory()
      .then((data) => {
        if (cancelled) return;
        setMemory(data.memory);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err);
      })
      .finally(() => {
        if (cancelled) return;
        setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (isLoading) {
    return (
      <div className="p-6">
        <p className="text-sm text-ink-muted">Loading...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <p className="text-sm text-red-400">Failed to load memory.</p>
      </div>
    );
  }

  return (
    <div className="scrollbar-thin mx-auto max-w-3xl space-y-6 overflow-y-auto px-4 py-6 sm:px-6">
      <h1 className="font-display text-base font-semibold text-ink">Learning Memory</h1>

      <LessonRecommendation />

      <StudentProfileSection profile={memory?.student_profile} />

      {LIST_SECTIONS.map(({ key, title, describe }) => {
        const rawItems = memory?.[key] ?? [];
        const items = rawItems.map((row) => ({ text: describe(row) }));
        return <ListSection key={key} title={title} items={items} />;
      })}
    </div>
  );
}
