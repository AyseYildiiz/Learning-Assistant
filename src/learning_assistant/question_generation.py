from collections.abc import Sequence

from learning_assistant.i18n import DEFAULT_LANGUAGE, GATEWAY_LANGUAGE_CODES, translate
from learning_assistant.ks_gateway import (
    FillBlankQuestion,
    KSGatewayClient,
    LearningPath,
    MultipleChoiceQuestion,
    parse_fill_blank_question,
    parse_learning_path,
    parse_multiple_choice_question,
)

_LANGUAGE_RESPONSE_INSTRUCTIONS = {
    "en": "Respond in English.",
    "tr": "Respond in Turkish (Türkçe).",
}


def _language_instruction(language: str | None) -> str | None:
    if not language:
        return None
    return _LANGUAGE_RESPONSE_INSTRUCTIONS.get(language)


def _gateway_language(language: str | None) -> str | None:
    if not language:
        return None
    return GATEWAY_LANGUAGE_CODES.get(language)


def _select_source_text(
    paragraph: str,
    sources: Sequence[tuple[str, str]] | None,
    index: int,
) -> str:
    # Round-robins across sources so every uploaded PDF gets covered instead
    # of the model only drawing from the first section of the combined text.
    if not sources:
        return paragraph
    return sources[index % len(sources)][1]


def build_multiple_choice_prompt(
    paragraph: str,
    question_number: int = 1,
    total_questions: int = 1,
    previous_questions: Sequence[str] = (),
    language: str | None = None,
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

    instruction = _language_instruction(language)
    if instruction:
        prompt_lines.append(f"- {instruction}")

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
    language: str | None = None,
    sources: Sequence[tuple[str, str]] | None = None,
) -> list[MultipleChoiceQuestion]:
    if count < 1:
        raise ValueError("count must be at least 1")

    gateway_client = client or KSGatewayClient()
    own_client = client is None
    questions: list[MultipleChoiceQuestion] = []

    try:
        for question_number in range(1, count + 1):
            prompt = build_multiple_choice_prompt(
                paragraph=_select_source_text(paragraph, sources, question_number - 1),
                question_number=question_number,
                total_questions=count,
                previous_questions=[question.question for question in questions],
                language=language,
            )
            last_error: ValueError | None = None
            for attempt in range(2):
                ai_answer = gateway_client.infer(
                    prompt=prompt, model=model, language=_gateway_language(language)
                )
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
                    translate(
                        language or DEFAULT_LANGUAGE,
                        "error_could_not_generate_questions",
                        number=question_number,
                    )
                ) from last_error
    finally:
        if own_client:
            gateway_client.close()

    return questions


def generate_multiple_choice_question(
    paragraph: str,
    client: KSGatewayClient | None = None,
    model: str | None = None,
    language: str | None = None,
) -> MultipleChoiceQuestion:
    return generate_multiple_choice_questions(
        paragraph=paragraph,
        count=1,
        client=client,
        model=model,
        language=language,
    )[0]


def build_fill_blank_prompt(
    paragraph: str,
    question_number: int = 1,
    total_questions: int = 1,
    previous_questions: Sequence[str] = (),
    language: str | None = None,
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

    instruction = _language_instruction(language)
    if instruction:
        prompt_lines.append(f"- {instruction}")

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
    language: str | None = None,
    sources: Sequence[tuple[str, str]] | None = None,
) -> list[FillBlankQuestion]:
    if count < 1:
        raise ValueError("count must be at least 1")

    gateway_client = client or KSGatewayClient()
    own_client = client is None
    questions: list[FillBlankQuestion] = []

    try:
        for question_number in range(1, count + 1):
            prompt = build_fill_blank_prompt(
                paragraph=_select_source_text(paragraph, sources, question_number - 1),
                question_number=question_number,
                total_questions=count,
                previous_questions=[question.question for question in questions],
                language=language,
            )
            last_error: ValueError | None = None
            for attempt in range(2):
                ai_answer = gateway_client.infer(
                    prompt=prompt, model=model, language=_gateway_language(language)
                )
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
                    translate(
                        language or DEFAULT_LANGUAGE,
                        "error_could_not_generate_questions",
                        number=question_number,
                    )
                ) from last_error
    finally:
        if own_client:
            gateway_client.close()

    return questions


def build_learning_path_prompt(paragraph: str, language: str | None = None) -> str:
    prompt_lines = [
        "You are a research-savvy learning coach with access to web search.",
        "Read the study material below, identify its key topics, and search "
        "the web for reputable external resources (official documentation, "
        "well-known courses, articles, videos, or books) that help a learner "
        "go deeper on each topic.",
        "Return ONLY JSON. Do not add markdown, code fences, commentary, or any other text.",
        "Use exactly this schema: "
        '{"overview": str, "steps": [{"topic": str, "summary": str, '
        '"resources": [{"title": str, "url": str or null, "description": str}]}]}',
        "Rules:",
        "- Produce between 3 and 6 steps, ordered from foundational to advanced.",
        "- Each step must include 1 to 3 resources.",
        '- Only set "url" when you are confident the resource is real and '
        'relevant; otherwise set "url" to null and use "description" to '
        "explain what to search for instead.",
        "- Keep the overview to 2-3 sentences.",
    ]

    if "--- Source:" in paragraph:
        prompt_lines.append(
            "- The study material below contains multiple sources, each "
            'marked by a "--- Source: <filename> ---" header. Make sure the '
            "overview and steps cover topics from ALL of these sources, not "
            "just the first one."
        )

    instruction = _language_instruction(language)
    if instruction:
        prompt_lines.append(f"- {instruction}")

    prompt_lines.extend(
        [
            "",
            "Study material:",
            paragraph.strip(),
        ]
    )
    return "\n".join(prompt_lines)


def generate_learning_path(
    paragraph: str,
    client: KSGatewayClient | None = None,
    model: str | None = None,
    language: str | None = None,
) -> LearningPath:
    gateway_client = client or KSGatewayClient()
    own_client = client is None

    try:
        prompt = build_learning_path_prompt(paragraph, language=language)
        last_error: ValueError | None = None
        for attempt in range(2):
            ai_answer = gateway_client.infer(
                prompt=prompt, model=model, language=_gateway_language(language)
            )
            try:
                return parse_learning_path(ai_answer)
            except ValueError as error:
                last_error = error
                if attempt == 0:
                    prompt = (
                        f"{prompt}\n\nYour previous response was invalid. "
                        "Return only valid JSON matching the required schema."
                    )
        raise ValueError(
            translate(
                language or DEFAULT_LANGUAGE, "error_could_not_generate_learning_path"
            )
        ) from last_error
    finally:
        if own_client:
            gateway_client.close()


def build_chat_prompt(
    source_material: str,
    history: Sequence[tuple[str, str]],
    question: str,
    language: str | None = None,
) -> str:
    prompt_lines = [
        "You are a helpful study assistant answering questions about the "
        "study material below.",
        "Only rely on the study material and the conversation so far to answer.",
        "If the answer is not covered by the material, say so instead of guessing.",
        "Respond with plain conversational text. Do not use JSON or markdown code fences.",
    ]

    instruction = _language_instruction(language)
    if instruction:
        prompt_lines.append(instruction)

    prompt_lines.extend(
        [
            "",
            "Study material:",
            source_material.strip(),
        ]
    )

    if history:
        prompt_lines.append("")
        prompt_lines.append("Conversation so far:")
        for role, content in history:
            speaker = "Learner" if role == "user" else "Assistant"
            prompt_lines.append(f"{speaker}: {content}")

    prompt_lines.extend(["", f"Learner: {question}", "Assistant:"])
    return "\n".join(prompt_lines)


def answer_chat_message(
    source_material: str,
    history: Sequence[tuple[str, str]],
    question: str,
    client: KSGatewayClient | None = None,
    model: str | None = None,
    language: str | None = None,
) -> str:
    gateway_client = client or KSGatewayClient()
    own_client = client is None

    try:
        prompt = build_chat_prompt(
            source_material, history, question, language=language
        )
        ai_answer = gateway_client.infer(
            prompt=prompt, model=model, language=_gateway_language(language)
        )
        return ai_answer.strip()
    finally:
        if own_client:
            gateway_client.close()
