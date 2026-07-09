import { useEffect, useState } from "react";
import { fetchLessonRecommendation } from "../api/client.js";

/**
 * LessonRecommendation.jsx
 *
 * Read-only view of GET /lesson-recommendation (lesson_recommender's
 * deterministic recommendation, unmodified). Fetches once on mount -
 * no polling, no auto-refresh, no mutations. Meant to be rendered at
 * the top of LearningDashboard.jsx.
 */
export default function LessonRecommendation() {
  const [recommendation, setRecommendation] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;

    setIsLoading(true);
    setError(null);

    fetchLessonRecommendation()
      .then((data) => {
        if (cancelled) return;
        setRecommendation(data.recommendation);
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

  return (
    <section>
      <h2 className="mb-2 font-display text-[11px] font-medium uppercase tracking-wider text-ink-muted">
        Lesson Recommendation
      </h2>

      {isLoading && <p className="text-sm text-ink-muted">Loading recommendation...</p>}

      {!isLoading && error && (
        <p className="text-sm text-red-400">Failed to load recommendation.</p>
      )}

      {!isLoading && !error && recommendation && (
        <ul className="space-y-1 text-sm text-ink">
          <li className="font-medium text-ink">{recommendation.title || "—"}</li>
          <li>{recommendation.reason || "—"}</li>
          <li>Difficulty: {recommendation.difficulty || "—"}</li>
          <li>Estimated duration: {recommendation.estimated_duration || "—"}</li>
          <li>
            Topics:{" "}
            {recommendation.topics?.length ? recommendation.topics.join(", ") : "—"}
          </li>
          <li>
            Recommended practice:{" "}
            {recommendation.recommended_practice?.length
              ? recommendation.recommended_practice.join("; ")
              : "—"}
          </li>
        </ul>
      )}
    </section>
  );
}
