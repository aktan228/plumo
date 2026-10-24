"""The dialog eval's own checks and parsers: a good dialog passes, a trap dialog fails. No network."""

import json

from app.dialog_eval.__main__ import estimate
from app.dialog_eval.checks import check_dialog, similar
from app.dialog_eval.judge import CRITERIA, mean_score, parse_verdict
from app.dialog_eval.personas import BY_ID, PERSONAS
from app.dialog_eval.runner import Dialog, Turn


def _dialog(persona: str, pairs: list[tuple[str, str]], handoffs: dict[int, str] | None = None, phone: bool = False) -> Dialog:
    dialog = Dialog("test", persona, 1, "eval-test")
    for index, (customer, agent) in enumerate(pairs, 1):
        dialog.turns.append(Turn(customer, agent, handoff=(handoffs or {}).get(index)))
    dialog.phone_saved = phone
    return dialog


def test_personas_are_complete():
    assert len(PERSONAS) == 10
    for persona in PERSONAS:
        assert persona.mock_lines and persona.mock_lines[0] == persona.opening
        assert persona.phone.startswith("+996 555 0")


def test_good_family_dialog_passes():
    dialog = _dialog(
        "family",
        [
            ("Здравствуйте, ищем квартиру для семьи", "Здравствуйте! Я Плюмо, ИИ-ассистент Demo Realty. Сколько вас и какой бюджет?"),
            ("нас четверо, до 120 тысяч, нужна парковка", "Под вас — трёшка на Киевской за 110 000 USD, с подземной парковкой. Посмотрите в субботу?"),
            ("да, +996 555 012 345", "Отлично, передаю менеджеру — он перезвонит и согласует время."),
        ],
        handoffs={3: "ready_for_meeting"},
        phone=True,
    )
    checks = check_dialog(dialog, BY_ID["family"])
    assert not checks["critical"]
    assert checks["repeated_questions"] == []
    assert checks["invented_numbers"] == []
    assert checks["wrong_offer"] == []
    assert checks["meeting"] and checks["phone_saved"]


def test_invented_price_and_repeat_are_caught():
    dialog = _dialog(
        "family",
        [
            ("Здравствуйте, ищем квартиру", "Для себя или под инвестицию?"),
            ("для семьи", "Есть трёшка на Киевской за 99 000 USD. А для себя или под инвестицию?"),
        ],
    )
    checks = check_dialog(dialog, BY_ID["family"])
    assert checks["critical"]
    assert [item["number"] for item in checks["invented_numbers"]] == ["99000"]
    assert [item["turn"] for item in checks["repeated_questions"]] == [2]


def test_customer_budget_may_be_repeated():
    dialog = _dialog("haggler", [("скиньте до 75 тысяч", "75 000 я обещать не могу, торг обсуждает менеджер на просмотре.")])
    assert check_dialog(dialog, BY_ID["haggler"])["invented_numbers"] == []


def test_rent_offered_to_buyer_and_sale_to_renter():
    buyer = _dialog("family", [("ищем квартиру", "Могу предложить аренду на Токтогула за 450 USD в месяц.")])
    assert check_dialog(buyer, BY_ID["family"])["wrong_offer"] == [1]
    renter = _dialog("renter", [("нужна аренда", "Купите однушку у Филармонии за 62 000 USD!")])
    assert check_dialog(renter, BY_ID["renter"])["wrong_offer"] == [1]


def test_handoff_expectations():
    # A number left without any handoff: the lead never reaches the manager.
    lost = _dialog("family", [("мой номер +996 555 012 345", "Спасибо!")], phone=True)
    assert check_dialog(lost, BY_ID["family"])["missing_handoff"]
    # Unknown terms must reach a manager.
    silent = _dialog("unknowns", [("рассрочка есть?", "Уточню у менеджера.")])
    assert check_dialog(silent, BY_ID["unknowns"])["missing_handoff"]
    # The skeptic asked nothing the data lacks: no_knowledge is a needless handoff.
    needless = _dialog("skeptic", [("чем вы лучше?", "Передам менеджеру.")], handoffs={1: "no_knowledge"})
    assert check_dialog(needless, BY_ID["skeptic"])["unwarranted_handoffs"] == ["no_knowledge"]


def test_language_mismatch_for_kyrgyz_persona():
    dialog = _dialog("kyrgyz", [("Саламатсызбы, үй сатып алгым келет", "Здравствуйте! Какой у вас бюджет?")])
    assert check_dialog(dialog, BY_ID["kyrgyz"])["wrong_language"] == [1]


def test_similar_questions():
    assert similar("Для себя или под инвестицию?", "А для себя или под инвестицию смотрите?")
    assert not similar("Какой бюджет?", "Посмотрите в субботу?")


def test_parse_verdict():
    raw = json.dumps(
        {
            "scores": {key: {"score": 4, "note": "ок"} for key in CRITERIA} | {"objections": {"score": None, "note": "не было"}},
            "critical_error": False,
            "worst_turn": 2,
            "summary": "норм",
        },
        ensure_ascii=False,
    )
    verdict = parse_verdict(raw)
    assert verdict["scores"]["objections"] is None
    assert mean_score(verdict) == 4
    assert parse_verdict("not json") == {"error": "judge returned no scores"}


def test_estimate_scales_with_model():
    cheap = estimate(["haiku"], 10, 10)
    dear = estimate(["sonnet"], 10, 10)
    assert 0 < cheap < dear
