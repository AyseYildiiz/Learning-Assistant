from __future__ import annotations

SUPPORTED_LANGUAGES: tuple[str, ...] = ("en", "tr")
DEFAULT_LANGUAGE = "en"

# Codes the KS AI Gateway's `language` request field expects.
GATEWAY_LANGUAGE_CODES: dict[str, str] = {"en": "en-US", "tr": "tr-TR"}

# Short labels shown on the language switcher button.
LANGUAGE_LABELS: dict[str, str] = {"en": "EN", "tr": "TR"}

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "app_name": {"en": "Learning Assistant", "tr": "Öğrenme Asistanı"},
    "app_tagline": {
        "en": "Turn reading into active recall",
        "tr": "Okumayı aktif hatırlamaya dönüştürün",
    },
    "toggle_theme": {"en": "Toggle theme", "tr": "Temayı değiştir"},
    "language_switch_label": {"en": "Choose language", "tr": "Dil seç"},
    "home_title": {
        "en": "StudyFlow | PDF Learning Assistant",
        "tr": "StudyFlow | PDF Öğrenme Asistanı",
    },
    "home_heading": {
        "en": "Learn from your PDFs, one quiz at a time.",
        "tr": "PDF'lerinizden, tek seferde bir sınav ile öğrenin.",
    },
    "home_lede": {
        "en": (
            "Upload a study document and get a focused quiz with "
            "spaced-repetition flashcards in seconds."
        ),
        "tr": (
            "Bir çalışma belgesi yükleyin, saniyeler içinde odaklı bir sınav "
            "ve aralıklı tekrar bilgi kartları elde edin."
        ),
    },
    "upload_heading": {"en": "Create a study set", "tr": "Bir çalışma seti oluştur"},
    "upload_hint": {
        "en": (
            "PDF files up to 10 MB each. You can select multiple PDFs at "
            "once; questions will be drawn from all of them."
        ),
        "tr": (
            "Her biri en fazla 10 MB olan PDF dosyaları. Aynı anda birden "
            "fazla PDF seçebilirsiniz; sorular hepsinden oluşturulur."
        ),
    },
    "upload_dropzone_label": {"en": "Choose your PDF(s)", "tr": "PDF(lerinizi) seçin"},
    "upload_dropzone_hint": {"en": "or drop them here", "tr": "veya buraya sürükleyin"},
    "upload_mcq_label": {"en": "Multiple choice", "tr": "Çoktan seçmeli"},
    "upload_fill_blank_label": {"en": "Fill in the blank", "tr": "Boşluk doldurma"},
    "upload_submit": {"en": "Generate set", "tr": "Seti oluştur"},
    "upload_submit_generating": {"en": "Generating...", "tr": "Oluşturuluyor..."},
    "upload_status_generating": {
        "en": "Extracting text and creating your quiz...",
        "tr": "Metin çıkarılıyor ve sınavınız oluşturuluyor...",
    },
    "upload_files_selected": {
        "en": "{count} PDFs selected",
        "tr": "{count} PDF seçildi",
    },
    "library_heading": {"en": "Your study sets", "tr": "Çalışma setleriniz"},
    "library_empty": {
        "en": "Your generated study sets will appear here.",
        "tr": "Oluşturduğunuz çalışma setleri burada görünecek.",
    },
    "action_resume_quiz": {"en": "Resume quiz", "tr": "Sınava devam et"},
    "action_flashcards": {"en": "Flashcards", "tr": "Bilgi kartları"},
    "action_learning_path": {"en": "Learning path", "tr": "Öğrenme haritası"},
    "action_delete": {"en": "Delete", "tr": "Sil"},
    "confirm_delete_set": {
        "en": "Delete this study set permanently?",
        "tr": "Bu çalışma setini kalıcı olarak silmek istiyor musunuz?",
    },
    "nav_review_flashcards": {
        "en": "Review flashcards",
        "tr": "Bilgi kartlarını gözden geçir",
    },
    "nav_back_to_library": {"en": "Back to library", "tr": "Kütüphaneye dön"},
    "nav_start_quiz": {"en": "Start quiz", "tr": "Sınava başla"},
    "quiz_session_heading": {"en": "Quiz session", "tr": "Sınav oturumu"},
    "quiz_source_set": {"en": "Source set: {name}", "tr": "Kaynak set: {name}"},
    "quiz_correct_label": {"en": "Correct", "tr": "Doğru"},
    "quiz_incorrect_label": {"en": "Incorrect", "tr": "Yanlış"},
    "quiz_latest_answer_label": {"en": "Latest answer", "tr": "Son cevap"},
    "quiz_question_progress": {
        "en": "Question {current} of {total}",
        "tr": "Soru {current} / {total}",
    },
    "quiz_fill_blank_hint": {
        "en": "Type the missing word or phrase and submit.",
        "tr": "Eksik kelimeyi veya ifadeyi yazıp gönderin.",
    },
    "quiz_choice_hint": {
        "en": "Choose one option and submit.",
        "tr": "Bir seçenek seçip gönderin.",
    },
    "quiz_your_answer_label": {"en": "Your answer", "tr": "Cevabınız"},
    "quiz_submit_answer": {"en": "Submit answer", "tr": "Cevabı gönder"},
    "quiz_complete_title": {"en": "Quiz complete.", "tr": "Sınav tamamlandı."},
    "quiz_final_score": {
        "en": "Final score: {correct} correct, {incorrect} incorrect.",
        "tr": "Sonuç: {correct} doğru, {incorrect} yanlış.",
    },
    "quiz_score_label": {"en": "Score:", "tr": "Puan:"},
    "quiz_restart_button": {"en": "Solve again from start", "tr": "Baştan tekrar çöz"},
    "quiz_no_cards_title": {"en": "No cards due", "tr": "Bekleyen kart yok"},
    "quiz_no_cards_copy": {
        "en": "There are no flashcards due for this PDF right now.",
        "tr": "Bu PDF için şu anda tekrar edilecek bilgi kartı yok.",
    },
    "quiz_time_up": {"en": "Time's up.", "tr": "Süre doldu."},
    "quiz_feedback_correct": {"en": "Correct answer.", "tr": "Doğru cevap."},
    "quiz_feedback_incorrect": {
        "en": "Incorrect. Correct answer: {answer}",
        "tr": "Yanlış. Doğru cevap: {answer}",
    },
    "flashcards_title": {"en": "Flashcards", "tr": "Bilgi Kartları"},
    "flashcards_heading": {"en": "Flashcards", "tr": "Bilgi Kartları"},
    "flashcards_subtitle": {"en": "Cards from {name}", "tr": "{name} kaynaklı kartlar"},
    "flashcards_answer_label": {"en": "Answer:", "tr": "Cevap:"},
    "flashcards_empty": {
        "en": "There are no cards due for review right now.",
        "tr": "Şu anda gözden geçirilecek kart yok.",
    },
    "learning_path_title": {"en": "Learning path", "tr": "Öğrenme Haritası"},
    "learning_path_subtitle": {
        "en": "A guided route through {name}",
        "tr": "{name} için rehberli bir yol",
    },
    "learning_path_error_prefix": {
        "en": "Could not generate a learning path: {error}",
        "tr": "Öğrenme haritası oluşturulamadı: {error}",
    },
    "learning_path_overview_heading": {"en": "Overview", "tr": "Genel Bakış"},
    "learning_path_empty": {
        "en": "No learning path is available for this study set yet.",
        "tr": "Bu çalışma seti için henüz bir öğrenme haritası yok.",
    },
    "learning_path_regenerate_button": {
        "en": "Regenerate learning path",
        "tr": "Öğrenme haritasını yeniden oluştur",
    },
    "chat_toggle_label": {"en": "Chat with AI", "tr": "Yapay zeka ile sohbet et"},
    "chat_close_label": {"en": "Close chat", "tr": "Sohbeti kapat"},
    "chat_hint": {
        "en": "Ask a question about {name}.",
        "tr": "{name} hakkında bir soru sorun.",
    },
    "chat_input_placeholder": {"en": "Ask a question...", "tr": "Bir soru sorun..."},
    "chat_send_button": {"en": "Send", "tr": "Gönder"},
    "chat_error_generic": {
        "en": "Sorry, something went wrong. Please try again.",
        "tr": "Üzgünüz, bir hata oluştu. Lütfen tekrar deneyin.",
    },
    "chat_answer_failed_prefix": {
        "en": "Sorry, I could not answer that: {error}",
        "tr": "Üzgünüm, bunu yanıtlayamadım: {error}",
    },
    "chat_error_empty_message": {
        "en": "Message cannot be empty",
        "tr": "Mesaj boş olamaz",
    },
    "error_please_select_pdf": {
        "en": "Please select a PDF file.",
        "tr": "Lütfen bir PDF dosyası seçin.",
    },
    "error_pdf_too_large": {
        "en": "The PDF must be smaller than 10 MB.",
        "tr": "PDF 10 MB'den küçük olmalıdır.",
    },
    "error_select_at_least_one_pdf": {
        "en": "Please select at least one PDF file.",
        "tr": "Lütfen en az bir PDF dosyası seçin.",
    },
    "error_too_many_files": {
        "en": "Choose at most {max} PDF files.",
        "tr": "En fazla {max} PDF dosyası seçin.",
    },
    "error_question_counts_negative": {
        "en": "Question counts cannot be negative.",
        "tr": "Soru sayıları negatif olamaz.",
    },
    "error_question_count_range": {
        "en": "Choose between 1 and {max} questions in total.",
        "tr": "Toplamda 1 ile {max} arasında soru seçin.",
    },
    "error_no_extractable_text": {
        "en": "No extractable text was found in {filename}.",
        "tr": "{filename} içinde çıkarılabilir metin bulunamadı.",
    },
    "success_set_deleted": {"en": "Study set deleted.", "tr": "Çalışma seti silindi."},
    "error_set_not_found": {
        "en": "Study set not found.",
        "tr": "Çalışma seti bulunamadı.",
    },
    "error_could_not_generate_questions": {
        "en": "Could not generate valid JSON for question {number}.",
        "tr": "{number}. soru için geçerli JSON oluşturulamadı.",
    },
    "error_could_not_generate_learning_path": {
        "en": "Could not generate a valid learning path.",
        "tr": "Geçerli bir öğrenme haritası oluşturulamadı.",
    },
}


def translate(language: str, key: str, **kwargs: object) -> str:
    entry = _TRANSLATIONS.get(key)
    if entry is None:
        return key

    text = entry.get(language) or entry.get(DEFAULT_LANGUAGE) or key
    return text.format(**kwargs) if kwargs else text


def all_translation_keys() -> list[str]:
    return list(_TRANSLATIONS)
