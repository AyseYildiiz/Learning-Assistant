from learning_assistant.ks_gateway import (
    KSGatewayClient,
    MultipleChoiceQuestion,
    parse_multiple_choice_question,
)


def build_multiple_choice_prompt(paragraph: str) -> str:
    return (
        "You are generating exactly one multiple-choice question from a single paragraph.\n"
        "Return ONLY JSON. Do not add markdown, code fences, commentary, or any other text.\n"
        'Use exactly this schema: {"question": str, "options": list[str], "correct_index": int}\n'
        "Rules:\n"
        "- Provide exactly 4 answer options.\n"
        "- Use a zero-based correct_index.\n"
        "- The correct answer must be supported by the paragraph.\n"
        "\nParagraph:\n"
        f"{paragraph.strip()}"
    )


def generate_multiple_choice_question(
    paragraph: str,
    client: KSGatewayClient | None = None,
    model: str | None = None,
) -> MultipleChoiceQuestion:
    gateway_client = client or KSGatewayClient()
    prompt = build_multiple_choice_prompt(paragraph)
    ai_answer = gateway_client.infer(prompt=prompt, model=model)
    return parse_multiple_choice_question(ai_answer)
