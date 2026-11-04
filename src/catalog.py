import json
import sqlite3
import unicodedata
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

AVAILABLE = "disponivel"
UNAVAILABLE = "indisponivel"
DISCONTINUED = "fora_de_catalogo"
NEW_RELEASE = "lancamento"
PIX_PERCENT = 5
PIX_NOTE_ON_PROMOTION = "O PIX não soma ao desconto da promoção."
# Fields that the record contradicts in another column (DQ-05); the model must not state them.
CONFLICTING_FIELDS = {137: {"strings"}}
# The record has the `specs` keys and some values in English; the customer reads Portuguese.
SPEC_NAMES = {
    "top": "tampo",
    "back_sides": "fundo e laterais",
    "neck": "braço",
    "strings": "cordas",
    "scale": "escala",
    "electronics": "eletrônica",
    "color": "cor",
    "body": "corpo",
    "shells": "cascos",
    "pieces": "peças",
    "hardware": "ferragens",
    "keys": "teclas",
    "type": "tipo",
    "polyphony": "polifonia",
}
SPEC_VALUES = {
    "yes": "sim",
    "no": "não",
    "steel": "aço",
    "nylon": "náilon",
    "included": "incluídas",
}
MIN_LENGTH_FOR_TYPO = 5
# Connecting words the customer writes that are not part of any name.
CONNECTING_WORDS = frozenset(
    "a as o os um uma e ou da das de do dos com para pra no na em".split()
)


@dataclass(frozen=True)
class Filters:
    """What the customer asked for in the search, already normalized."""

    words: list[str]
    category: str
    max_price: float | None
    only_available: bool
    quantity: int | None
    only_on_sale: bool


@dataclass(frozen=True)
class Product:
    id: int
    name: str
    category: str
    price: str
    discount_percent: int | None
    final_price: str
    pix_price: str | None
    availability: str
    specifications: dict[str, str]
    # Only present when the customer asked for a quantity; the exact stock is never exposed.
    meets_quantity: bool | None = None
    # Only present when there is an active promotion, which does not stack with the PIX discount.
    pix_note: str | None = None
    # The PIX discount ("5%"), present together with pix_price; the answer may cite it.
    pix_percent: str | None = None


def format_price(cents: int) -> str:
    reais, remainder = divmod(cents, 100)
    return f"R$ {reais:,}".replace(",", ".") + f",{remainder:02d}"


def normalize(text: str) -> str:
    without_accents = unicodedata.normalize("NFD", text.casefold())
    return "".join(c for c in without_accents if not unicodedata.combining(c))


def singularize(text: str) -> str:
    """Reduces each normalized word to the singular, so that "violão" matches "Violões"."""
    words = []
    for word in text.split():
        if len(word) > 3:
            for plural, singular in (("oes", "ao"), ("aes", "ao"), ("ns", "m"), ("s", "")):
                if word.endswith(plural):
                    word = word.removesuffix(plural) + singular
                    break
        words.append(word)
    return " ".join(words)


def _differs_by_at_most_one_character(a: str, b: str) -> bool:
    """Says whether two words differ by at most one insertion, deletion, or substitution."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b)) <= 1
    short, long_turn = sorted((a, b), key=len)
    return any(long_turn[:i] + long_turn[i + 1 :] == short for i in range(len(long_turn)))


def _contains(word: str, name: str) -> bool:
    return word in name


def _approximate_word(word: str, name: str) -> bool:
    """Accepts a typo only in long names; model codes stay exact."""
    if word in name:
        return True
    long_enough = len(word) >= MIN_LENGTH_FOR_TYPO
    return word.isalpha() and long_enough and any(
        _differs_by_at_most_one_character(word, part) for part in name.split()
    )


def classify(status: str, stock: int) -> str:
    # The status takes precedence over the stock.
    if status == "discontinued":
        return DISCONTINUED
    if status == "coming_soon":
        return NEW_RELEASE
    return AVAILABLE if stock > 0 else UNAVAILABLE


def apply_discount(cents: int, percent: int) -> int:
    return int((Decimal(cents) * (100 - percent) / 100).quantize(Decimal(1), ROUND_HALF_UP))


def calculate_final_price(row: sqlite3.Row) -> int:
    discount = row["discount_percent"]
    return apply_discount(row["price_cents"], discount) if discount else row["price_cents"]


def build_product(row: sqlite3.Row, quantity: int | None = None) -> Product:
    discount = row["discount_percent"]
    cents = row["price_cents"]
    # PIX applies to the list price and does not stack with promotions.
    pix = None if discount else format_price(apply_discount(cents, PIX_PERCENT))
    availability = classify(row["status"], row["stock_quantity"])
    meets = None
    if quantity is not None:
        meets = availability == AVAILABLE and row["stock_quantity"] >= quantity
    return Product(
        row["product_id"],
        row["name"],
        row["category"],
        format_price(cents),
        discount,
        format_price(calculate_final_price(row)),
        pix,
        availability,
        {
            SPEC_NAMES.get(key, key): SPEC_VALUES.get(amount, amount)
            for key, amount in json.loads(row["specs"]).items()
            if key not in CONFLICTING_FIELDS.get(row["product_id"], ())
        },
        meets,
        PIX_NOTE_ON_PROMOTION if discount else None,
        None if discount else f"{PIX_PERCENT}%",
    )


def search_products(
    connection: sqlite3.Connection,
    search_term: str | None = None,
    category: str | None = None,
    max_price: float | None = None,
    only_available: bool = False,
    quantity: int | None = None,
    only_on_sale: bool = False,
) -> list[Product]:
    rows = connection.execute(
        """
        SELECT p.product_id, p.name, c.name AS category, p.price_cents,
               p.stock_quantity, p.status, p.specs, pr.discount_percent
        FROM products p
        JOIN categories c ON c.category_id = p.category_id
        LEFT JOIN promotions pr ON pr.product_id = p.product_id AND pr.is_active = 1
        ORDER BY p.name
        """
    ).fetchall()

    customer_words = normalize(search_term or "").split()
    words = [p for p in customer_words if p not in CONNECTING_WORDS]
    if customer_words and not words:
        # Only connecting words do not say what the customer is looking for.
        return []
    normalized_category = singularize(normalize(category or ""))
    filters = Filters(
        words, normalized_category, max_price, only_available, quantity, only_on_sale
    )
    products = _filter_rows(rows, filters)
    if not products and (words or normalized_category):
        products = _filter_rows(rows, filters, approximate=True)
    return products


def _filter_rows(rows, filters: Filters, approximate: bool = False):
    products = []
    for row in rows:
        name = normalize(row["name"])
        product_category = singularize(normalize(row["category"]))
        category_words = set(product_category.split())
        matches = _approximate_word if approximate else _contains
        # "violão takamine": the category word is not in the product name.
        # "GF3D" and "GF-3D" are the same model: the hyphen does not count in the exact comparison.
        name_without_hyphen = name.replace("-", "")
        if not all(
            matches(word, name)
            or _contains(word.replace("-", ""), name_without_hyphen)
            or singularize(word) in category_words
            for word in filters.words
        ):
            continue
        # The category also tolerates a typo, but only after the exact comparison.
        if filters.category not in product_category and not (
            approximate
            and all(_approximate_word(word, product_category) for word in filters.category.split())
        ):
            continue
        if filters.only_on_sale and not row["discount_percent"]:
            continue
        if (
            filters.max_price is not None
            and calculate_final_price(row) > Decimal(str(filters.max_price)) * 100
        ):
            continue
        product = build_product(row, filters.quantity)
        if filters.only_available and product.availability != AVAILABLE:
            continue
        products.append(product)
    return products


def _price_row(connection: sqlite3.Connection, product_id: int) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT p.name, p.price_cents, p.stock_quantity, p.status, pr.discount_percent
        FROM products p
        LEFT JOIN promotions pr ON pr.product_id = p.product_id AND pr.is_active = 1
        WHERE p.product_id = ?
        """,
        (product_id,),
    ).fetchone()


def final_price_cents(connection: sqlite3.Connection, product_id: int) -> int | None:
    row = _price_row(connection, product_id)
    return calculate_final_price(row) if row else None


@dataclass(frozen=True)
class PricingData:
    name: str
    final_price: int
    # Paying with PIX: the discount applies to the list price and does not stack with the promotion.
    price_with_pix: int
    on_promotion: bool
    availability: str
    stock: int


def pricing_data(connection: sqlite3.Connection, product_id: int) -> PricingData | None:
    row = _price_row(connection, product_id)
    if row is None:
        return None
    on_promotion = bool(row["discount_percent"])
    final_price = calculate_final_price(row)
    return PricingData(
        row["name"],
        final_price,
        final_price if on_promotion else apply_discount(row["price_cents"], PIX_PERCENT),
        on_promotion,
        classify(row["status"], row["stock_quantity"]),
        row["stock_quantity"],
    )


def product_name(connection: sqlite3.Connection, product_id: int) -> str | None:
    row = connection.execute(
        "SELECT name FROM products WHERE product_id = ?", (product_id,)
    ).fetchone()
    return row["name"] if row else None
