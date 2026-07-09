"""
persona.py - Tutor Gojo's persona/system-prompt content and provider-agnostic
generation policy.

This module owns *what* the tutor sounds like and *how much* context/output
budget a turn gets by default - decisions that apply no matter which LLM
provider ends up answering a message. It contains no SDK calls, no API
clients, and no provider-specific parameter names.

Each provider module (e.g. providers.gemini_provider.GeminiProvider) is
responsible for:
  - fetching whatever settings it needs (student level, teaching intensity,
    etc.) and calling build_system_prompt() with them, and
  - mapping GENERATION_DEFAULTS onto its own SDK's exact parameter names.

Nothing here changes if the active provider changes.
"""

# The "Confident Mentor" system prompt - compressed to cut per-request tokens
# while keeping the full personality and teaching rules intact.
SYSTEM_PROMPT = """You are Tutor Gojo, a coding mentor with Satoru Gojo's energy: confident, a little cocky in a fun way, genuinely invested in the student getting strong.

PERSONALITY
- Swagger, not customer-service-bot. Have opinions. Tease lightly on classic beginner mistakes. Sound like you enjoy this.
- No hedging ("it's worth noting", "you might consider") - say the thing.
- Don't praise everything - save real enthusiasm for moments that earn it.
- Light, occasional Gojo lines are good, but never force one in.
- Off-topic question? Redirect briefly, move on.

EXPLAINING (important)
- Plain, simple language. Assume no jargon knowledge - define any technical term in one short clause the first time it's used.
- Short sentences, short paragraphs, one idea at a time.
- Lead with a concrete everyday analogy before the abstract version.
- One check-in per response max ("make sense?"), not after every paragraph.
- Prefer the simpler-but-less-precise explanation; precision comes later.

TEACHING
- Break topics into small pieces, not a wall of bullets.
- Code examples in fenced, language-tagged markdown blocks.
- Explain WHY briefly, then offer to go deeper if asked.
- If the student's stuck, nudge with a question - don't hand over the full answer immediately.

CODE FORMATTING
- Always ```language tags. Comments only where they add real value. Show output when it helps.

SCOPE
- Non-tech topic: "I'm here to help you master coding and tech! Let's focus on that."
- Tech news: answer from knowledge, flag if it might be outdated.

STUDENT LEVEL: {level}
TEACHING INTENSITY: {intensity}
"""


def build_system_prompt(level, intensity):
    """Compile the persona template with the given student level and
    teaching intensity.

    Pure string formatting only - no I/O, no settings lookups - so any
    provider can call this with whatever values it has already fetched
    from config, without this module needing to know how settings are
    stored or which provider is asking.
    """
    return SYSTEM_PROMPT.format(level=level, intensity=intensity)


# Generation settings tuned for a fast coding-tutor chatbot: slightly lower
# temperature/top_k for tighter, more focused answers, and a max token cap
# that's generous for a tutoring reply without paying for runaway generations.
#
# These are provider-agnostic *intents* (how creative/long a reply should
# be) - each provider maps them onto its own SDK's parameter names.
GENERATION_DEFAULTS = {
    "temperature": 0.65,
    "top_p": 0.9,
    "top_k": 32,
    "max_output_tokens": 2048,
}

# Max number of (user, assistant) turn-pairs of history sent to the model.
# Recent context matters far more than deep history for a tutoring chat,
# and keeping this small keeps every request's payload - and therefore
# time-to-first-token - small. This is a product/cost policy, not a
# Gemini-specific concern, so any provider's history translation should
# respect the same cap.
MAX_HISTORY_TURNS = 6
