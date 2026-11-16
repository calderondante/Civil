"""Reviewed spoken representation, never a rewrite of the written legal source."""

import re
from .tts import spoken_text
from .normalization import _decimal_digits

POLICY = "es-ar-reading-v1"


class SpeechPlanError(ValueError):
    pass


SMALL = [
    "cero",
    "uno",
    "dos",
    "tres",
    "cuatro",
    "cinco",
    "seis",
    "siete",
    "ocho",
    "nueve",
    "diez",
    "once",
    "doce",
    "trece",
    "catorce",
    "quince",
    "dieciséis",
    "diecisiete",
    "dieciocho",
    "diecinueve",
    "veinte",
    "veintiuno",
    "veintidós",
    "veintitrés",
    "veinticuatro",
    "veinticinco",
    "veintiséis",
    "veintisiete",
    "veintiocho",
    "veintinueve",
]


def apocope(text):
    if text.endswith("veintiuno"):
        return text[:-9] + "veintiún"
    return text[:-3] + "un" if text.endswith("uno") else text


def integer(n):
    if n < 0:
        return "menos " + integer(-n)
    if n < 30:
        return SMALL[n]
    if n < 100:
        q, r = divmod(n, 10)
        return [
            "",
            "",
            "",
            "treinta",
            "cuarenta",
            "cincuenta",
            "sesenta",
            "setenta",
            "ochenta",
            "noventa",
        ][q] + (" y " + SMALL[r] if r else "")
    if n == 100:
        return "cien"
    if n < 1000:
        q, r = divmod(n, 100)
        return [
            "",
            "ciento",
            "doscientos",
            "trescientos",
            "cuatrocientos",
            "quinientos",
            "seiscientos",
            "setecientos",
            "ochocientos",
            "novecientos",
        ][q] + (" " + integer(r) if r else "")
    if n < 1_000_000:
        q, r = divmod(n, 1000)
        return ("mil" if q == 1 else apocope(integer(q)) + " mil") + (
            " " + integer(r) if r else ""
        )
    if n < 1_000_000_000_000:
        q, r = divmod(n, 1_000_000)
        return ("un millón" if q == 1 else apocope(integer(q)) + " millones") + (
            " " + integer(r) if r else ""
        )
    raise SpeechPlanError("quantity_outside_reviewed_speech_range")


def say_number(raw):
    value = _decimal_digits(raw)
    if value is None:
        raise SpeechPlanError("ambiguous_spoken_quantity")
    whole, _, fraction = value.partition(".")
    return integer(int(whole)) + (
        " coma " + " ".join(SMALL[int(d)] for d in fraction) if fraction else ""
    )


def compile_speech(text, dictionary):
    policy = dictionary.get("__policy__")
    dictionary = {k: v for k, v in dictionary.items() if not k.startswith("__")}
    current = spoken_text(text, dictionary)
    ledger = []
    if current != text:
        ledger.append({"rule": "approved_dictionary", "from": text, "to": current})
    if policy is None:
        return {
            "original_text": text,
            "spoken_text": current,
            "policy": "legacy-dictionary",
            "transformations": ledger,
        }
    if policy not in (POLICY, "es-ar-symbols-v1"):
        raise SpeechPlanError("unsupported_speech_policy")

    def substitute(pattern, fn, rule, flags=0):
        nonlocal current

        def change(match):
            replacement = fn(match)
            ledger.append(
                {
                    "rule": rule,
                    "from": match.group(),
                    "to": replacement,
                    "stage_span": [match.start(), match.end()],
                }
            )
            return replacement

        current = re.sub(pattern, change, current, flags=flags)

    substitute(
        r"\b(art[íi]culos?\s+)(\d+)[°º]",
        lambda m: m[1] + say_number(m[2]),
        "article_ordinal_not_temperature",
        re.I,
    )
    substitute(
        r"\b(art[íi]culos\s+)(\d+(?:\.\d{3})*)\s*[-–]\s*(\d+(?:\.\d{3})*)",
        lambda m: m[1] + say_number(m[2]) + " a " + say_number(m[3]),
        "article_range",
        re.I,
    )

    def money(m):
        prefix = m[1].upper()
        context = current[max(0, m.start() - 100) : m.end() + 30]
        if prefix == "$" and not re.search(r"\bpesos?\b", context, re.I):
            raise SpeechPlanError("ambiguous_currency_requires_explicit_dictionary")
        unit = (
            "dólares"
            if prefix in ("US$", "U$S")
            else "euros"
            if prefix == "€"
            else "pesos"
        )
        return say_number(m[2]) + " " + unit

    substitute(
        r"(US\$|U\$S|\$|€)\s*(\d+(?:[.,]\d+)*)",
        money,
        "explicit_currency_and_quantity",
        re.I,
    )
    if policy == POLICY:
        substitute(
            r"(?<!\w)\d+(?:[.,]\d+)*(?!\w)",
            lambda m: say_number(m.group()),
            "quantity_spelled_for_voice",
        )
    return {
        "original_text": text,
        "spoken_text": current,
        "policy": POLICY,
        "transformations": ledger,
    }
