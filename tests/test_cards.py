from hh_job_bot.cards import render_vacancy


def test_card_contains_moscow_publication_time_and_score(vacancy_factory) -> None:
    vacancy = vacancy_factory(
        published_at="2026-06-27T11:35:00+00:00",
        score=76,
        score_matches=["Playwright"],
        score_gaps=["SQL"],
        profile_names=["AI automation"],
    )

    text = render_vacancy(vacancy)

    assert "27.06.2026, 14:35" in text
    assert "Релевантность: 76/100" in text
    assert "Playwright" in text
    assert "SQL" in text
    assert "AI automation" in text


def test_card_escapes_external_html(vacancy_factory) -> None:
    text = render_vacancy(vacancy_factory(title="<b>unsafe</b>"))
    assert "&lt;b&gt;unsafe&lt;/b&gt;" in text
    assert "<b>unsafe</b>" not in text
