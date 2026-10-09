"""Spoken numbers to digits for speech transcripts, Russian and Kyrgyz.

Speech recognition writes "восемьдесят пять тысяч" or "сексен беш миң" where a
chat customer types "85000". Retrieval and the fact validator match digits, so
a voice turn is normalized before the core sees it. Checked on Scribe output
from phone-quality audio (see app.voice_probe).

A lone "один" / "бир" stays a word: in "бир батир барбы" it means "an
apartment", and a stray 1 would look like an unknown price to the validator.
"""

import re

_UNITS = {
    # Russian, nominative / accusative / genitive / prepositional
    **dict.fromkeys(("ноль", "нуль"), 0),
    **dict.fromkeys(("один", "одна", "одно", "одну", "одного", "одной", "одном"), 1),
    **dict.fromkeys(("два", "две", "двух", "двум"), 2),
    **dict.fromkeys(("три", "трех", "трём", "трем", "трёх"), 3),
    **dict.fromkeys(("четыре", "четырех", "четырёх"), 4),
    **dict.fromkeys(("пять", "пяти"), 5),
    **dict.fromkeys(("шесть", "шести"), 6),
    **dict.fromkeys(("семь", "семи"), 7),
    **dict.fromkeys(("восемь", "восьми"), 8),
    **dict.fromkeys(("девять", "девяти"), 9),
    # Kyrgyz (Kazakh-looking spellings appear in mixed-speech transcripts)
    "бир": 1,
    "эки": 2,
    "үч": 3,
    "уч": 3,
    "төрт": 4,
    "беш": 5,
    "алты": 6,
    "жети": 7,
    "сегиз": 8,
    "тогуз": 9,
}
_TEENS = {
    **dict.fromkeys(("десять", "десяти"), 10),
    **dict.fromkeys(("одиннадцать", "одиннадцати"), 11),
    **dict.fromkeys(("двенадцать", "двенадцати"), 12),
    **dict.fromkeys(("тринадцать", "тринадцати"), 13),
    **dict.fromkeys(("четырнадцать", "четырнадцати"), 14),
    **dict.fromkeys(("пятнадцать", "пятнадцати"), 15),
    **dict.fromkeys(("шестнадцать", "шестнадцати"), 16),
    **dict.fromkeys(("семнадцать", "семнадцати"), 17),
    **dict.fromkeys(("восемнадцать", "восемнадцати"), 18),
    **dict.fromkeys(("девятнадцать", "девятнадцати"), 19),
}
_TENS = {
    **dict.fromkeys(("двадцать", "двадцати"), 20),
    **dict.fromkeys(("тридцать", "тридцати"), 30),
    **dict.fromkeys(("сорок", "сорока"), 40),
    **dict.fromkeys(("пятьдесят", "пятидесяти"), 50),
    **dict.fromkeys(("шестьдесят", "шестидесяти"), 60),
    **dict.fromkeys(("семьдесят", "семидесяти"), 70),
    **dict.fromkeys(("восемьдесят", "восьмидесяти"), 80),
    **dict.fromkeys(("девяносто", "девяноста"), 90),
    "он": 10,
    "жыйырма": 20,
    "жийирма": 20,
    "отуз": 30,
    "кырк": 40,
    "элүү": 50,
    "элуу": 50,
    "алтымыш": 60,
    "жетимиш": 70,
    "сексен": 80,
    "токсон": 90,
}
_HUNDREDS = {
    **dict.fromkeys(("сто", "ста"), 100),
    **dict.fromkeys(("двести", "двухсот"), 200),
    **dict.fromkeys(("триста", "трехсот", "трёхсот"), 300),
    **dict.fromkeys(("четыреста", "четырехсот", "четырёхсот"), 400),
    **dict.fromkeys(("пятьсот", "пятисот"), 500),
    **dict.fromkeys(("шестьсот", "шестисот"), 600),
    **dict.fromkeys(("семьсот", "семисот"), 700),
    **dict.fromkeys(("восемьсот", "восьмисот"), 800),
    **dict.fromkeys(("девятьсот", "девятисот"), 900),
}
_KY_HUNDRED = ("жүз", "жуз")
_MILLION = ("миллион", "млн")
# Words that are numbers only inside a longer number: Russian "он" is "he", Kyrgyz "бир" is also "a".
_LONE_ONES = frozenset(("один", "одна", "одно", "одну", "одного", "одной", "одном", "бир", "он"))

_TOKEN = re.compile(r"\d+(?:[   ]\d{3})*|[^\W\d_]+|\S", re.UNICODE)
# Kazakh letters that recognition sometimes writes for Kyrgyz speech.
_KAZAKH = str.maketrans({"қ": "к", "ғ": "г", "ұ": "у", "і": "и"})


def _word(token: str) -> str:
    return token.lower().replace("ё", "е").translate(_KAZAKH)


def _multiplier(word: str) -> int | None:
    if any(word.startswith(stem) for stem in _MILLION):
        return 1_000_000
    if word in ("тыс", "миң", "мың") or word.startswith(("тысяч", "миң", "мың")):
        return 1000
    return None


def _small(word: str) -> int | None:
    for table in (_HUNDREDS, _TENS, _TEENS, _UNITS):
        if word in table:
            return table[word]
    return None


def spoken_to_digits(text: str) -> str:
    """Replace number words with digits; leave every other token as it was."""

    tokens = list(_TOKEN.finditer(text))
    out: list[str] = []
    cursor = 0
    i = 0
    while i < len(tokens):
        value, end = _read_number(tokens, i)
        if value is None:
            i += 1
            continue
        out.append(text[cursor : tokens[i].start()])
        out.append(str(value))
        cursor = tokens[end - 1].end()
        i = end
    out.append(text[cursor:])
    return "".join(out)


def _read_number(tokens, start: int) -> tuple[int | None, int]:
    """Longest number starting at `start`: (value, index of the token after it)."""

    total = 0
    group = 0
    used = 0
    i = start
    last_small: int | None = None
    while i < len(tokens):
        raw = tokens[i].group(0)
        word = _word(raw)
        if raw[0].isdigit():
            if used:
                break
            group = int(re.sub(r"\D", "", raw))
            used += 1
            last_small = group
            i += 1
            continue
        if word in _KY_HUNDRED:
            group = (group or 1) * 100
            used += 1
            i += 1
            continue
        multiplier = _multiplier(word)
        if multiplier is not None and used:
            total += (group or 1) * multiplier
            group = 0
            used += 1
            last_small = None
            i += 1
            continue
        small = _small(word)
        if small is None or (last_small is not None and not _fits(last_small, small)):
            break
        group += small
        last_small = small
        used += 1
        i += 1
    if used == 0:
        return None, start + 1
    if used == 1 and tokens[start].group(0)[0].isdigit():
        return None, start + 1
    if used == 1 and _word(tokens[start].group(0)) in _LONE_ONES:
        return None, start + 1
    return total + group, i


def _fits(previous: int, following: int) -> bool:
    """Words compose only from larger to smaller orders: "восемьдесят пять", not "пять восемьдесят"."""

    def order(value: int) -> int:
        return 3 if value >= 100 else 2 if value >= 20 else 1

    if previous >= 100:
        return following < 100
    if previous == 10:
        # Kyrgyz "он бир" is 11; Russian never says "десять пять".
        return following < 10
    if previous >= 20 and previous % 10 == 0:
        return following < 10
    return order(following) < order(previous) and previous >= 20
