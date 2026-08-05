from collections.abc import Sequence

from learning_assistant.ks_gateway import (
    FillBlankQuestion,
    KSGatewayClient,
    MultipleChoiceQuestion,
    parse_fill_blank_question,
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
        "-Do not generate more or fewer than given number of questions.",
        "- Provide exactly 4 answer options.",
        "- Use a zero-based correct_index.",
        "- The correct answer must be supported by the paragraph.",
    ]

    if previous_questions:
        prompt_lines.append("Do not repeat these earlier question stems:")
        prompt_lines.extend(f"- {question}" for question in previous_questions)

    prompt_lines.extend(
        [
            "",
            "Paragraph:",
            paragraph.strip(),
        ]
    )
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
            last_error: ValueError | None = None
            for attempt in range(2):
                ai_answer = gateway_client.infer(prompt=prompt, model=model)
                try:
                    questions.append(parse_multiple_choice_question(ai_answer))
                    break
                except ValueError as error:
                    last_error = error
                    if attempt == 0:
                        prompt = (
                            f"{prompt}\n\nYour previous response was invalid. "
                            "Return only valid JSON matching the required schema."
                        )
            else:
                raise ValueError(
                    f"Could not generate valid JSON for question {question_number}."
                ) from last_error
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


def build_fill_blank_prompt(
    paragraph: str,
    question_number: int = 1,
    total_questions: int = 1,
    previous_questions: Sequence[str] = (),
) -> str:
    prompt_lines = [
        f"You are generating fill-in-the-blank question {question_number} of {total_questions} from a single paragraph.",
        "Return ONLY JSON. Do not add markdown, code fences, commentary, or any other text.",
        'Use exactly this schema: {"question": str, "answer": str}',
        "Rules:",
        "- Do not generate more or fewer than the given number of questions.",
        '- The "question" field must be a sentence from or based on the paragraph with one key word or short phrase replaced by a blank written as "_____".',
        '- The "answer" field must be the exact word or short phrase that fills the blank.',
        "- The answer must be short (ideally 1-3 words) and must be directly supported by the paragraph.",
    ]

    if previous_questions:
        prompt_lines.append("Do not repeat these earlier question stems:")
        prompt_lines.extend(f"- {question}" for question in previous_questions)

    prompt_lines.extend(
        [
            "",
            "Paragraph:",
            paragraph.strip(),
        ]
    )
    return "\n".join(prompt_lines)


def generate_fill_blank_questions(
    paragraph: str,
    count: int = 5,
    client: KSGatewayClient | None = None,
    model: str | None = None,
) -> list[FillBlankQuestion]:
    if count < 1:
        raise ValueError("count must be at least 1")

    gateway_client = client or KSGatewayClient()
    own_client = client is None
    questions: list[FillBlankQuestion] = []

    try:
        for question_number in range(1, count + 1):
            prompt = build_fill_blank_prompt(
                paragraph=paragraph,
                question_number=question_number,
                total_questions=count,
                previous_questions=[question.question for question in questions],
            )
            last_error: ValueError | None = None
            for attempt in range(2):
                ai_answer = gateway_client.infer(prompt=prompt, model=model)
                try:
                    questions.append(parse_fill_blank_question(ai_answer))
                    break
                except ValueError as error:
                    last_error = error
                    if attempt == 0:
                        prompt = (
                            f"{prompt}\n\nYour previous response was invalid. "
                            "Return only valid JSON matching the required schema."
                        )
            else:
                raise ValueError(
                    f"Could not generate valid JSON for question {question_number}."
                ) from last_error
    finally:
        if own_client:
            gateway_client.close()

    return questions
