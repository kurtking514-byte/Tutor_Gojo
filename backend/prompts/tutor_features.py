"""
tutor_features.py - product-level features built on top of the generic
gemini_client send/generate interface: quiz generation and code explanation.

These are provider-agnostic: each function only constructs a prompt string
and (for quiz generation) parses the response - it never talks to an SDK
directly. They call into gemini_client's public functions, which today
forward to GeminiProvider but could forward to a routed provider in the
future without either function below changing.
"""

import gemini_client


def generate_quiz(topic, difficulty="medium"):
    """Generate a quiz question on a specific topic.

    Returns a dict with: question, options, correct, explanation
    """
    prompt = f"""Generate a {difficulty} difficulty quiz question about {topic}.
    Format your response EXACTLY like this:

    QUESTION: [the question text]
    A) [option A]
    B) [option B]
    C) [option C]
    D) [option D]
    CORRECT: [A/B/C/D]
    EXPLANATION: [why this is the correct answer]
    """

    response = gemini_client.generate_content(prompt)
    text = response.text

    # Parse the response
    result = {"question": "", "options": {}, "correct": "", "explanation": ""}

    for line in text.strip().split("\n"):
        if line.startswith("QUESTION:"):
            result["question"] = line.replace("QUESTION:", "").strip()
        elif line.startswith("A)"):
            result["options"]["A"] = line.replace("A)", "").strip()
        elif line.startswith("B)"):
            result["options"]["B"] = line.replace("B)", "").strip()
        elif line.startswith("C)"):
            result["options"]["C"] = line.replace("C)", "").strip()
        elif line.startswith("D)"):
            result["options"]["D"] = line.replace("D)", "").strip()
        elif line.startswith("CORRECT:"):
            result["correct"] = line.replace("CORRECT:", "").strip()
        elif line.startswith("EXPLANATION:"):
            result["explanation"] = line.replace("EXPLANATION:", "").strip()

    return result


def explain_code(code, language="python"):
    """Ask Gojo to explain a piece of code."""
    prompt = f"""Explain this {language} code line by line. Be patient and thorough:

```{language}
{code}
```

Explain what each part does and why it's written this way."""

    return gemini_client.send_message(prompt)
