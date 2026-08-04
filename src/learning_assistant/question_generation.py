from collections.abc import Sequence

from learning_assistant.ks_gateway import (
    KSGatewayClient,
    MultipleChoiceQuestion,
    parse_multiple_choice_question,
)


def build_multiple_choice_prompt(
    paragraph: str,
    question_number: int = 1,
    total_questions: int = 1,
    previous_questions: Sequence[str] = (),
) -> str:
    prompt_lines = [
        f"You are generating question {question_number} of {total_questions} from a single paragraph.",
        "Return ONLY JSON. Do not add markdown, code fences, commentary, or any other text.",
        'Use exactly this schema: {"question": str, "options": list[str], "correct_index": int}',
        "Rules:",
        "- Provide exactly 4 answer options.",
        "- Use a zero-based correct_index.",
        "- The correct answer must be supported by the paragraph.",
    ]

    if previous_questions:
        prompt_lines.append("Do not repeat these earlier question stems:")
        prompt_lines.extend(f"- {question}" for question in previous_questions)

    prompt_lines.extend([
        "",
        "Paragraph:",
        paragraph.strip(),
    ])
    return "\n".join(prompt_lines)


def generate_multiple_choice_questions(
    paragraph: str,
    count: int = 5,
    client: KSGatewayClient | None = None,
    model: str | None = None,
) -> list[MultipleChoiceQuestion]:
    if count < 1:
        raise ValueError("count must be at least 1")

    gateway_client = client or KSGatewayClient()
    own_client = client is None
    questions: list[MultipleChoiceQuestion] = []

    try:
        for question_number in range(1, count + 1):
            prompt = build_multiple_choice_prompt(
                paragraph=paragraph,
                question_number=question_number,
                total_questions=count,
                previous_questions=[question.question for question in questions],
            )
            ai_answer = gateway_client.infer(prompt=prompt, model=model)
            questions.append(parse_multiple_choice_question(ai_answer))
    finally:
        if own_client:
            gateway_client.close()

    return questions


def generate_multiple_choice_question(
    paragraph: str,
    client: KSGatewayClient | None = None,
    model: str | None = None,
) -> MultipleChoiceQuestion:
    return generate_multiple_choice_questions(
        paragraph=paragraph,
        count=1,
        client=client,
        model=model,
    )[0]
