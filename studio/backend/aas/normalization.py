"""Conservative Spanish quantity canonicalization, with a visible transformation ledger.

No spelling correction of legal concepts. A digit/spoken-number equivalence must
preserve value, order, sign, unit, currency and article-reference structure.
"""

import re
import unicodedata
from decimal import Decimal, InvalidOperation

ONES = dict(
    zip(
        "cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciseis diecisiete dieciocho diecinueve veinte veintiuno veintidos veintitres veinticuatro veinticinco veintiseis veintisiete veintiocho veintinueve".split(),
        range(30),
    )
)
ONES.update({"un": 1, "una": 1, "veintiun": 21, "veintiuna": 21})
TENS = dict(
    zip(
        "treinta cuarenta cincuenta sesenta setenta ochenta noventa".split(),
        range(30, 100, 10),
    )
)
HUNDREDS = {
    "cien": 100,
    "ciento": 100,
    "doscientos": 200,
    "doscientas": 200,
    "trescientos": 300,
    "trescientas": 300,
    "cuatrocientos": 400,
    "cuatrocientas": 400,
    "quinientos": 500,
    "quinientas": 500,
    "seiscientos": 600,
    "seiscientas": 600,
    "setecientos": 700,
    "setecientas": 700,
    "ochocientos": 800,
    "ochocientas": 800,
    "novecientos": 900,
    "novecientas": 900,
}
UNITS = {
    "año": "año",
    "años": "año",
    "dia": "día",
    "dias": "día",
    "mes": "mes",
    "meses": "mes",
    "hora": "hora",
    "horas": "hora",
    "minuto": "minuto",
    "minutos": "minuto",
    "segundo": "segundo",
    "segundos": "segundo",
    "porcentaje": "%",
    "pesos": "ARS",
    "peso": "ARS",
    "ars": "ARS",
    "dolares": "USD",
    "dolar": "USD",
    "usd": "USD",
    "monedausd": "USD",
    "monedaars": "ARS",
    "monedaeur": "EUR",
    "euro": "EUR",
    "euros": "EUR",
    "$": "ARS",
    "€": "EUR",
    "%": "%",
}
MARKERS = {
    "no",
    "ni",
    "nunca",
    "jamas",
    "sin",
    "salvo",
    "excepto",
    "unicamente",
    "solamente",
    "a_menos_que",
    "siempre_que",
}
LEGAL = set(
    "dolo dolor culpa error cuasidelito delito sujeto objeto causa heredero herederos sucesor sucesores acreedor deudor anulabilidad subsanacion lesion cesion nulidad nulidades inoponibilidad prescripcion caducidad discernimiento intencion intension libertad licito licitos ilicito ilicitos voluntario voluntarios involuntario involuntarios consentimiento agente hecho acto contrato testamento condicion plazo cargo imputacion antijuridicidad representacion capacidad persona personas juridico juridicos juridica juridicas".split()
)
ALIASES = {
    "art": "articulo",
    "arts": "articulos",
    "ej": "ejemplo",
    "inc": "inciso",
    "incs": "incisos",
    "num": "numero",
    "nro": "numero",
    "examenoral": "examen oral",
}


def plain(text):
    # ñ must remain distinct: año/ano are NOT interchangeable quantities.
    protected = unicodedata.normalize("NFC", text.casefold()).replace("ñ", "\ue000")
    return "".join(
        c
        for c in unicodedata.normalize("NFKD", protected)
        if not unicodedata.combining(c)
    ).replace("\ue000", "ñ")


def _small(t, i):
    if i >= len(t):
        return None, i
    if t[i] in HUNDREDS:
        value = HUNDREDS[t[i]]
        end = i + 1
        if t[i] != "cien":
            rest, stop = _under100(t, end)
            if rest is not None:
                value += rest
                end = stop
        return value, end
    return _under100(t, i)


def _under100(t, i):
    if i >= len(t):
        return None, i
    if t[i] in ONES:
        return ONES[t[i]], i + 1
    if t[i] in TENS:
        value = TENS[t[i]]
        end = i + 1
        if (
            end + 1 < len(t)
            and t[end] == "y"
            and t[end + 1] in ONES
            and 1 <= ONES[t[end + 1]] <= 9
        ):
            value += ONES[t[end + 1]]
            end += 2
        return value, end
    return None, i


def _thousands(t, i):
    if i < len(t) and t[i] == "mil":
        value, end = 1, i
    else:
        value, end = _small(t, i)
    if value is None:
        return None, i
    if end < len(t) and t[end] == "mil":
        value *= 1000
        end += 1
        rest, stop = _small(t, end)
        if rest is not None:
            value += rest
            end = stop
    return value, end


def cardinal(t, i):
    value, end = _thousands(t, i)
    if value is None:
        return None, i
    if end < len(t) and t[end] in ("millon", "millones"):
        value *= 1_000_000
        end += 1
        rest, stop = _thousands(t, end)
        if rest is not None:
            value += rest
            end = stop
    return value, end


def _decimal_digits(token):
    # Spanish grouping 1.500,25, decimal 1,5, and decimal point 1.5.
    if "," in token and "." in token:
        if not re.fullmatch(r"\d{1,3}(?:\.\d{3})+,\d+|\d+,\d+", token):
            return None
        value = token.replace(".", "").replace(",", ".")
    elif "," in token:
        value = token.replace(",", ".") if token.count(",") == 1 else None
    elif re.fullmatch(r"[1-9]\d{0,2}(?:\.\d{3})+", token):
        value = token.replace(".", "")
    else:
        value = token
    if value is None:
        return None
    try:
        d = Decimal(value)
        return (
            format(d, "f").rstrip("0").rstrip(".") if "." in format(d, "f") else str(d)
        )
    except InvalidOperation:
        return None


def canonicalize(text):
    original = plain(text)
    # Currency/percentage names have defined personal es-AR semantics; recorded below.
    prepared = re.sub(r"(?<!\w)(?:us\$|u\$s|usd)(?![a-z])", " monedausd ", original)
    prepared = re.sub(r"\bpor\s+ciento\b", " % ", prepared)
    spacing_repairs = []
    if re.search(r"\ben\s+numeracion\b", prepared):
        prepared = re.sub(r"\ben\s+numeracion\b", "enumeracion", prepared)
        spacing_repairs.append(
            {
                "kind": "audible_word_boundary",
                "from": "en numeracion",
                "to": "enumeracion",
            }
        )
    prepared = re.sub(r"\ba\s+menos\s+que\b", " a_menos_que ", prepared)
    prepared = re.sub(r"\bsiempre\s+que\b", " siempre_que ", prepared)
    raw = re.findall(r"\d+(?:[.,]\d+)*|[a-zñ_]+|[%$€/−–-]", prepared)
    expanded = []
    ledger = spacing_repairs
    for token in raw:
        replacement = ALIASES.get(token, token)
        if replacement != token:
            ledger.append(
                {"kind": "abbreviation_or_boundary", "from": token, "to": replacement}
            )
        expanded.extend(replacement.split())
    t = expanded
    out = []
    numbers = []
    units = []
    i = 0
    ambiguous = []
    while i < len(t):
        token = t[i]
        sign = ""
        if (
            token in ("menos", "−", "-")
            and i + 1 < len(t)
            and (not out or not re.fullmatch(r"-?\d+(?:\.\d+)?", out[-1]))
        ):
            value, end = cardinal(t, i + 1)
            digit = _decimal_digits(t[i + 1]) if t[i + 1][0].isdigit() else None
            if value is not None or digit is not None:
                sign = "-"
                i += 1
                token = t[i]
        reference_context = bool(
            out
            and out[-1]
            in ("articulo", "articulos", "capitulo", "titulo", "numero", "apartado")
        )
        ordinals = {
            "primero": 1,
            "primer": 1,
            "segundo": 2,
            "tercero": 3,
            "tercer": 3,
            "cuarto": 4,
            "quinto": 5,
            "sexto": 6,
            "septimo": 7,
            "octavo": 8,
            "noveno": 9,
            "decimo": 10,
        }
        if reference_context and token in ordinals:
            ledger.append(
                {"kind": "reference_ordinal", "from": token, "to": str(ordinals[token])}
            )
            token = str(ordinals[token])
        elif reference_context and re.fullmatch(r"[ivxlcdm]+", token):
            values = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
            number = 0
            for j, ch in enumerate(token):
                number += (
                    -values[ch]
                    if j + 1 < len(token) and values[ch] < values[token[j + 1]]
                    else values[ch]
                )
            rendered = ""
            rest = number
            for n, r in [
                (1000, "m"),
                (900, "cm"),
                (500, "d"),
                (400, "cd"),
                (100, "c"),
                (90, "xc"),
                (50, "l"),
                (40, "xl"),
                (10, "x"),
                (9, "ix"),
                (5, "v"),
                (4, "iv"),
                (1, "i"),
            ]:
                while rest >= n:
                    rendered += r
                    rest -= n
            if rendered == token:
                ledger.append(
                    {"kind": "reference_roman", "from": token, "to": str(number)}
                )
                token = str(number)
        if token[0].isdigit():
            value = _decimal_digits(token)
            end = i + 1
            if value is None:
                ambiguous.append(token)
                out.append(token)
                i = end
                continue
        else:
            # Do not turn the indefinite article in 'una manifestación' into a count.
            allowed = (
                token not in ("un", "una")
                or (
                    i + 1 < len(t) and t[i + 1] in {"mil", "millon", "millones", *UNITS}
                )
                or (i and t[i - 1] in ("articulo", "numero", "inciso", "apartado"))
            )
            n, end = cardinal(t, i) if allowed else (None, i)
            value = str(n) if n is not None else None
        if value is not None:
            if end < len(t) and t[end] == "coma":
                start = end + 1
                j = start
                digits = []
                while j < len(t) and t[j] in ONES and 0 <= ONES[t[j]] <= 9:
                    digits.append(str(ONES[t[j]]))
                    j += 1
                if not digits:
                    fraction, j = cardinal(t, start)
                    digits = [str(fraction)] if fraction is not None else []
                if digits:
                    value = (
                        str(Decimal(value + "." + "".join(digits)))
                        .rstrip("0")
                        .rstrip(".")
                        if Decimal(value + "." + "".join(digits)) % 1
                        else str(int(Decimal(value + "." + "".join(digits))))
                    )
                    end = j
            value = sign + value
            out.append(value)
            numbers.append(value)
            spoken = " ".join(t[i:end])
            if spoken != value:
                ledger.append({"kind": "quantity", "from": spoken, "to": value})
            i = end
            continue
        if token in UNITS:
            mapped = UNITS[token]
            units.append(mapped)
            out.append("unit:" + mapped)
            if token != mapped:
                ledger.append({"kind": "unit", "from": token, "to": mapped})
        elif (
            token in ("–", "-")
            and out
            and i + 1 < len(t)
            and re.fullmatch(r"\d+(?:[.,]\d+)*", t[i + 1])
            and re.fullmatch(r"\d+", out[-1])
        ):
            out.append("a")
            ledger.append({"kind": "range_separator", "from": token, "to": "a"})
        elif token not in ("-", "–", "−"):
            out.append(token)
        i += 1
    # Prefix '$ 1500' and suffix '1500 pesos' must keep the same value and currency.
    for j in range(len(out) - 1):
        if out[j] in ("unit:ARS", "unit:USD", "unit:EUR") and re.fullmatch(
            r"-?\d+(?:\.\d+)?", out[j + 1]
        ):
            out[j], out[j + 1] = out[j + 1], out[j]
    j = 0
    while j + 3 < len(out):
        if (
            re.fullmatch(r"\d+", out[j])
            and out[j + 1] in ("unit:ARS", "unit:USD", "unit:EUR")
            and out[j + 2] == "con"
            and re.fullmatch(r"\d{1,2}", out[j + 3])
            and j + 4 < len(out)
            and out[j + 4] in ("centavo", "centavos", "centimo", "centimos")
        ):
            value = str(Decimal(out[j]) + Decimal(out[j + 3]) / 100)
            value = value.rstrip("0").rstrip(".") if "." in value else value
            ledger.append(
                {
                    "kind": "money_minor_units",
                    "from": " ".join(out[j : j + 5]),
                    "to": value,
                }
            )
            out[j : j + 5] = [value, out[j + 1]]
        j += 1
    numbers = [t for t in out if re.fullmatch(r"-?\d+(?:\.\d+)?", t)]
    refs = []
    for j, token in enumerate(out):
        if token not in ("articulo", "articulos"):
            continue
        k = j + 1
        values = []
        connectors = []
        if k < len(out) and out[k] == "numero":
            k += 1
        while k < len(out):
            if re.fullmatch(r"\d+", out[k]):
                values.append(out[k])
                k += 1
            elif (
                values
                and out[k] in ("a", "hasta", "y")
                and k + 1 < len(out)
                and re.fullmatch(r"\d+", out[k + 1])
            ):
                connectors.append("a" if out[k] == "hasta" else out[k])
                k += 1
            else:
                break
        refs.append({"values": values, "connectors": connectors})
    return {
        "tokens": out,
        "numbers": numbers,
        "units": units,
        "articles": refs,
        "markers": [x for x in out if x in MARKERS],
        "legal_terms": [x for x in out if x in LEGAL],
        "normalizations": ledger,
        "ambiguous_numbers": ambiguous,
    }
