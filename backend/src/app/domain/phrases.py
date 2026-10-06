"""Fixed replies owned by the product, not by a model provider.

Plumo is not allowed to invent facts. These phrases are the safe fallback.
"""

UNKNOWN_FACT_RU = "Я не хочу давать вам неточную информацию. Уточню это у менеджера."
UNKNOWN_FACT_KY = "Такталбаган маалымат айта албайм. Муну менеджерден тактайм."
UNKNOWN_INSTALLMENT_RU = "У меня нет информации о рассрочке. Я передам вопрос менеджеру."
ROLE_PHRASE_RU = "Я Plumo, ассистент по объектам. Про устройство модели не рассказываю — давайте к квартирам: бюджет, район или число комнат."
ROLE_PHRASE_KY = "Мен Plumo, объекттер боюнча жардамчымын. Квартира керек болсо, бюджет же районду айтыңыз."

AGENT_INSTRUCTIONS = """Ты Plumo, менеджер по продажам.
Отвечай только фактами из блока knowledge и карточки бизнеса.
Не называй цену, наличие, сроки, рассрочку, адрес и характеристики, если их нет в этих данных.
Если факта нет, скажи, что уточнишь у менеджера, и не додумывай.
Язык ответа: ru, ky или смешанный, как у клиента.
Не обещай скидку и не подтверждай условия, которых нет в базе.
""".strip()


def unknown_phrase(topic: str | None, language: str) -> str:
    if language == "ky":
        return UNKNOWN_FACT_KY
    if topic == "installment":
        return UNKNOWN_INSTALLMENT_RU
    return UNKNOWN_FACT_RU
