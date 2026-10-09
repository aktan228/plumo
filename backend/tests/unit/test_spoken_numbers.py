"""Number words from speech recognition become digits; ordinary words stay."""

import pytest

from app.domain.spoken_numbers import spoken_to_digits


@pytest.mark.parametrize(
    ("heard", "expected"),
    [
        # Real Scribe output from the phone-quality probe (2026-10-09).
        ("Две комнаты, 58 квадратных метров, 85 тысяч долларов.", "2 комнаты, 58 квадратных метров, 85000 долларов."),
        ("Можно в субботу в одиннадцать посмотреть?", "Можно в субботу в 11 посмотреть?"),
        ("Баасы сексен беш миң доллар.", "Баасы 85000 доллар."),
        ("Бюджет тоқсон мың долларға шейін.", "Бюджет 90000 долларға шейін."),
        ("$85 тыс. Когда вам удобно?", "$85000. Когда вам удобно?"),
        ("Эртең саат үчтө", "Эртең саат үчтө"),
        ("квартира за восемьдесят пять тысяч", "квартира за 85000"),
        ("до ста двадцати тысяч", "до 120000"),
        ("за сто десять тысяч долларов", "за 110000 долларов"),
        ("он бир миң", "11000"),
        ("два миллиона сомов", "2000000 сомов"),
        ("третий этаж", "третий этаж"),
    ],
)
def test_spoken_numbers(heard: str, expected: str) -> None:
    assert spoken_to_digits(heard) == expected


@pytest.mark.parametrize(
    "text",
    [
        "бир батир барбы",
        "он скоро перезвонит",
        "одна комната или две",
        "через 5 мин буду",
        "торт",
        "Цена 85 000 USD",
    ],
)
def test_ordinary_words_and_digits_stay(text: str) -> None:
    result = spoken_to_digits(text)
    if text == "одна комната или две":
        assert result == "одна комната или 2"
    else:
        assert result == text
