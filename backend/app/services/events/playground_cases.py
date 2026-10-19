"""Synthetic, in-memory D03 normalizer inputs; never import these into a corpus."""

from copy import deepcopy

URL = "https://ticketon.kz/synthetic-d03-playground"
START_TEXT = "15 January 2030, 19:00"
END_TEXT = "15 January 2030, 21:00"
CONDITIONS = "Category-dependent admission price"
SOURCE_TEXT = (
    "Synthetic D03 event. City: Astana. Venue: Synthetic venue. "
    "Address: Synthetic street 1, Astana. "
    f"Scheduled session starts {START_TEXT}; ends {END_TEXT}. "
    f"Admission from 3000 KZT; {CONDITIONS}."
)
BASE_INPUT = {
    "now": "2030-01-15T09:00:00+05:00",
    "selected_at": "2030-01-15T10:00:00+05:00",
    "events": [
        {
            "title": "Synthetic D03 event",
            "source_url": URL,
            "page_kind": "event",
            "city": "Astana",
            "venue_name": "Synthetic venue",
            "venue_address": "Synthetic street 1, Astana",
            "sessions": [
                {
                    "source_url": URL,
                    "date_text": START_TEXT,
                    "date_basis": "session",
                    "starts_at": "2030-01-15T19:00:00+05:00",
                    "ends_at": "2030-01-15T21:00:00+05:00",
                    "end_text": END_TEXT,
                    "price_from": 3000,
                    "currency": "KZT",
                    "price_conditions": CONDITIONS,
                    "price_kind": "starting",
                    "status": "scheduled",
                }
            ],
        }
    ],
    "sources": [{"url": URL, "text": SOURCE_TEXT}],
    "pois": [],
    "simulate_start_check": False,
}


def _synthetic_poi(index: int) -> dict:
    # False is_test flags simulate the matcher rights gate ONLY in this harness.
    # URLs, license and permissions are fake assertions, never corpus import data.
    source_id = f"synthetic:playground:source:{index}"
    return {
        "id": f"synthetic:playground:poi:{index}",
        "primary_source_id": source_id,
        "external_id": f"synthetic-playground-{index}",
        "name": "Synthetic venue",
        "address": "Synthetic street 1, Astana",
        "activity_code": "culture",
        "location": {"latitude": 51.12 + index * 0.001, "longitude": 71.45},
        "sources": [
            {
                "source_id": source_id,
                "provider": "osm",
                "url": f"https://www.openstreetmap.org/synthetic-d03-playground/poi-{index}",
                "retrieved_at": BASE_INPUT["now"],
                "license": "Synthetic in-memory permission simulation; not a real license",
                "rights_basis_url": "https://www.openstreetmap.org/synthetic-d03-playground/rights",
                "storage_allowed": True,
                "indexing_allowed": True,
                "is_test": False,
            }
        ],
        "provenance": [
            {
                "source_id": source_id,
                "external_id": f"synthetic-playground-{index}",
                "fields": ["name", "address", "location"],
            }
        ],
        "is_test": False,
    }


def playground_cases() -> list[dict]:
    """Return independent editable copies; no provider, file or database access."""
    cases = []

    def add(identifier: str, label: str, description: str, expected: str) -> dict:
        data = deepcopy(BASE_INPUT)
        cases.append(
            {
                "id": identifier,
                "label": label,
                "description": description,
                "expected": expected,
                "input": data,
            }
        )
        return data

    add(
        "baseline",
        "Обычный сеанс",
        "Полные синтетические факты без POI.",
        "Сеанс discovered, цена от 3000 KZT; координаты и билеты неизвестны.",
    )
    data = add(
        "cancelled",
        "Отмена",
        "Источник явно сообщает отмену.",
        "Сеанс сохранён как cancelled и исключён из рекомендаций.",
    )
    data["events"][0]["sessions"][0]["status"] = "cancelled"
    data["sources"][0]["text"] = SOURCE_TEXT.replace("Scheduled", "Cancelled")
    data = add(
        "past",
        "Прошедший сеанс",
        "Показ состоялся вчера, 14 января.",
        "Сеанс исключён: past_session и дата вне выбранного дня.",
    )
    session = data["events"][0]["sessions"][0]
    for field in ("starts_at", "ends_at"):
        session[field] = session[field].replace("2030-01-15", "2030-01-14")
    for field in ("date_text", "end_text"):
        session[field] = session[field].replace("15 January", "14 January")
    data["sources"][0]["text"] = SOURCE_TEXT.replace("15 January", "14 January")
    data = add(
        "missingyear",
        "Год отсутствует",
        "В цитате нет года, хотя extractor вписал ISO.",
        "Начало и окончание null; год не достраивается из выбранной даты.",
    )
    for field in ("date_text", "end_text"):
        data["events"][0]["sessions"][0][field] = data["events"][0]["sessions"][0][field].replace(
            " 2030", ""
        )
    data["sources"][0]["text"] = SOURCE_TEXT.replace(" 2030", "")
    data = add(
        "missingend",
        "Окончание неизвестно",
        "Источник сообщает только начало.",
        "ends_at=null; сеанс не обещает уложиться во временное окно.",
    )
    data["events"][0]["sessions"][0].update(ends_at=None, end_text=None)
    data["sources"][0]["text"] = SOURCE_TEXT.replace(f"; ends {END_TEXT}", "")
    data = add(
        "unsupported_price",
        "Выдуманная бесплатность",
        "Extractor указал 0, источник — от 3000.",
        "price_from и currency null; ноль не находится внутри числа 3000.",
    )
    data["events"][0]["sessions"][0]["price_from"] = 0
    data = add(
        "promotion",
        "Цена по акции",
        "Акция явно указана рядом с ценой.",
        "1500 KZT и promotion; это не обычная цена.",
    )
    data["events"][0]["sessions"][0].update(price_from=1500, price_kind="regular")
    data["sources"][0]["text"] = SOURCE_TEXT.replace(
        "Admission from 3000", "Promotion admission from 1500"
    )
    data = add(
        "listing",
        "Афиша вместо сеанса",
        "URL заканчивается /ru/posters, тип ошибочно session.",
        "Нормализуется listing без подтверждённых сеансов.",
    )
    listing_url = URL + "/ru/posters"
    data["events"][0].update(source_url=listing_url, page_kind="session")
    data["events"][0]["sessions"][0]["source_url"] = listing_url
    data["sources"][0]["url"] = listing_url
    data = add(
        "othercity",
        "Другой город",
        "И extractor, и источник указывают Алматы.",
        "Событие отклонено; provider status unknown, не no_match.",
    )
    data["events"][0].update(city="Almaty", venue_address="Synthetic street 1, Almaty")
    data["sources"][0]["text"] = SOURCE_TEXT.replace("Astana", "Almaty")
    data = add(
        "duplicate_cancelled",
        "Дубликат с отменой",
        "Один сеанс продублирован со статусом cancelled.",
        "Остаётся один отменённый сеанс; порядок не скрывает отмену.",
    )
    duplicate = deepcopy(data["events"][0]["sessions"][0])
    duplicate["status"] = "cancelled"
    data["events"][0]["sessions"].append(duplicate)
    data["sources"][0]["text"] += f" Cancellation: session {START_TEXT} is cancelled."
    data = add(
        "matchedvenue",
        "Сопоставление площадки",
        "Один вымышленный POI, разрешения имитируются в памяти.",
        "Площадка сопоставлена; эти данные нельзя импортировать в корпус.",
    )
    data["pois"] = [_synthetic_poi(1)]
    data = add(
        "ambiguousvenue",
        "Две одинаковые площадки",
        "Два вымышленных POI с теми же именем и адресом.",
        "venue.basis=ambiguous, координаты null; ближайший POI не угадывается.",
    )
    data["pois"] = [_synthetic_poi(1), _synthetic_poi(2)]
    return cases
