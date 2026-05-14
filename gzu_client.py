import os
os.environ["PGCLIENTENCODING"] = "UTF8"
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

psycopg2.extensions.encodings['WIN1251'] = 'cp1251'
psycopg2.extensions.encodings['win1251'] = 'cp1251'

import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8', errors='replace')

# --- config ---
def get_db_params():
    return {
        "host":            "localhost",
        "port":            5433,
        "dbname":          "gzu_db",
        "user":            "postgres",
        "password":        "postgres",
        "options":  "-c search_path=public"
    }
# --- db ---
@contextmanager
def get_connection():
    params = get_db_params()
    params.pop("client_encoding", None)
    
    conn = None
    try:
        conn = psycopg2.connect(**params)
        conn.set_client_encoding('UTF8')
        yield conn
        conn.commit()
    except Exception:
        if conn:
            conn.rollback()
        raise
    finally:
        if conn:
            conn.close()

def fetch_all(sql, args=None):
    args = args or ()
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, args)
            return list(cur.fetchall())


def fetch_one(sql, args=None):
    rows = fetch_all(sql, args)
    return rows[0] if rows else None


def execute(sql, args=None):
    args = args or ()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.rowcount

# --- table_specs ---
@dataclass
class Col:
    sql: str
    label: str
    col_type: str  # text, int, bool, date, numeric, serial, fk_int
    required: bool = False
    editable: bool = True


@dataclass
class TableSpec:
    sql_name: str
    title: str
    pk: List[str]
    columns: List[Col]
    order_by_default: List[str]
    searchable: List[str] = field(default_factory=list)
    filterable: List[str] = field(default_factory=list)


TABLE_SPECS = {
    "services": TableSpec(
        sql_name="services",
        title="Службы",
        pk=["service_id"],
        columns=[
            Col("service_id", "Код (ID)", "serial", required=False, editable=False),
            Col("service_code", "Код службы", "text", required=True),
            Col("name", "Наименование", "text", required=True),
            Col("phone", "Телефон", "text", required=False),
            Col("created_at", "Создано", "timestamp", required=False, editable=False),
        ],
        order_by_default=["service_id"],
        searchable=["service_code", "name", "phone"],
        filterable=["service_code", "name"],
    ),
    "service_departments": TableSpec(
        sql_name="service_departments",
        title="Отделы служб",
        pk=["service_id", "dept_id"],
        columns=[
            Col("service_id", "Код службы (FK)", "fk_int", required=True),
            Col("dept_id", "Код отдела", "int", required=True),
            Col("name", "Наименование", "text", required=True),
            Col("address", "Адрес", "text", required=True),
        ],
        order_by_default=["service_id", "dept_id"],
        searchable=["name", "address"],
        filterable=["service_id", "dept_id", "name"],
    ),
    "maintenance_sites": TableSpec(
        sql_name="maintenance_sites",
        title="Участки (эксплуатация)",
        pk=["service_id", "dept_id", "site_id"],
        columns=[
            Col("service_id", "Код службы", "fk_int", required=True),
            Col("dept_id", "Код отдела", "int", required=True),
            Col("site_id", "Код участка", "int", required=True),
            Col("name", "Наименование", "text", required=True),
        ],
        order_by_default=["service_id", "dept_id", "site_id"],
        searchable=["name"],
        filterable=["service_id", "dept_id", "site_id", "name"],
    ),
    "election_precincts": TableSpec(
        sql_name="election_precincts",
        title="Избирательные участки",
        pk=["precinct_id"],
        columns=[
            Col("precinct_id", "Код", "serial", editable=False),
            Col("precinct_number", "Номер участка", "int", required=True),
            Col("title", "Название", "text", required=True),
            Col("address", "Адрес", "text", required=False),
        ],
        order_by_default=["precinct_number"],
        searchable=["title", "address"],
        filterable=["precinct_number", "title"],
    ),
    "payer_codes": TableSpec(
        sql_name="payer_codes",
        title="Шифры плательщика",
        pk=["code_id"],
        columns=[
            Col("code_id", "Код", "serial", editable=False),
            Col("code_name", "Название", "text", required=True),
            Col("payment_percent", "Процент оплаты", "numeric", required=True),
            Col("notes", "Примечания", "text", required=False),
        ],
        order_by_default=["code_id"],
        searchable=["code_name", "notes"],
        filterable=["code_name"],
    ),
    "tariffs": TableSpec(
        sql_name="tariffs",
        title="Тарифы",
        pk=["tariff_id"],
        columns=[
            Col("tariff_id", "Код", "serial", editable=False),
            Col("has_cold_water", "Холодная вода", "bool", required=True),
            Col("has_hot_water", "Горячая вода", "bool", required=True),
            Col("has_garbage_chute", "Мусоропровод", "bool", required=True),
            Col("has_elevator", "Лифт", "bool", required=True),
            Col("rate_per_sqm", "Тариф за м²", "numeric", required=True),
            Col("valid_from", "Действует с", "date", required=True),
            Col("description", "Описание", "text", required=False),
        ],
        order_by_default=["valid_from", "tariff_id"],
        searchable=["description"],
        filterable=["has_cold_water", "has_hot_water", "has_garbage_chute", "has_elevator"],
    ),
    "houses": TableSpec(
        sql_name="houses",
        title="Дома",
        pk=["house_id"],
        columns=[
            Col("house_id", "Код дома", "serial", editable=False),
            Col("service_id", "Код службы", "fk_int", required=True),
            Col("dept_id", "Код отдела", "int", required=True),
            Col("site_id", "Код участка", "int", required=True),
            Col("street", "Улица", "text", required=True),
            Col("house_number", "Номер дома", "text", required=True),
            Col("building_corpus", "Корпус", "text", required=False),
            Col("election_precinct_id", "Изб. участок (FK)", "fk_int", required=False),
        ],
        order_by_default=["street", "house_number"],
        searchable=["street", "house_number"],
        filterable=["service_id", "dept_id", "site_id", "street", "election_precinct_id"],
    ),
    "apartments": TableSpec(
        sql_name="apartments",
        title="Квартиры",
        pk=["apartment_id"],
        columns=[
            Col("apartment_id", "Код квартиры", "serial", editable=False),
            Col("house_id", "Код дома", "fk_int", required=True),
            Col("apt_number", "Номер квартиры", "text", required=True),
            Col("living_area_sqm", "Жилая площадь", "numeric", required=True),
            Col("total_area_sqm", "Общая площадь", "numeric", required=True),
            Col("is_privatized", "Приватизирована", "bool", required=True),
            Col("has_cold_water", "Холодная вода", "bool", required=True),
            Col("has_hot_water", "Горячая вода", "bool", required=True),
            Col("has_garbage_chute", "Мусоропровод", "bool", required=True),
            Col("has_elevator", "Лифт", "bool", required=True),
            Col("resident_count", "Жильцов (авто)", "int", editable=False, required=False),
            Col(
                "election_precinct_id_snapshot",
                "Участок (снимок, авто)",
                "fk_int",
                editable=False,
                required=False,
            ),
        ],
        order_by_default=["apartment_id"],
        searchable=["apt_number"],
        filterable=["house_id", "apt_number", "is_privatized"],
    ),
    "residents": TableSpec(
        sql_name="residents",
        title="Жильцы",
        pk=["resident_id"],
        columns=[
            Col("resident_id", "Код", "serial", editable=False),
            Col("apartment_id", "Код квартиры", "fk_int", required=True),
            Col("full_name", "ФИО", "text", required=True),
            Col("inn", "ИНН", "text", required=False),
            Col("passport_series_no", "Паспорт", "text", required=False),
            Col("birth_date", "Дата рождения", "date", required=True),
            Col("is_primary_tenant", "Ответственный", "bool", required=True),
            Col("payer_code_id", "Шифр плательщика (FK)", "fk_int", required=False),
        ],
        order_by_default=["full_name"],
        searchable=["full_name", "inn", "passport_series_no"],
        filterable=["apartment_id", "is_primary_tenant", "payer_code_id"],
    ),
}


def get_spec(key: str) -> TableSpec:
    return TABLE_SPECS[key]


def sortable_columns(spec: TableSpec) -> List[str]:
    return [c.sql for c in spec.columns if c.col_type != "timestamp" or c.sql == "created_at"]
# --- ui_utils ---
def parse_bool(s: str) -> Optional[bool]:
    t = (s or "").strip().lower()
    if t in ("", "нет", "н", "no", "n", "0", "false", "ложь"):
        return False
    if t in ("да", "д", "yes", "y", "1", "true", "истина"):
        return True
    return None


def format_bool(v: Any) -> str:
    if v is None:
        return ""
    return "да" if bool(v) else "нет"


def parse_value(raw: str, col: Col) -> Any:
    raw = (raw or "").strip()
    if col.col_type == "serial":
        raise ValueError("Поле только для чтения")
    if not raw and not col.required and col.col_type != "bool":
        return None
    if not raw and col.col_type == "bool" and not col.required:
        return False
    if col.col_type in ("text",):
        if col.required and not raw:
            raise ValueError("Пустое значение недопустимо")
        return raw or None
    if col.col_type == "int":
        if not raw:
            return None if not col.required else (_ for _ in ()).throw(ValueError("Обязательное поле"))
        return int(raw)
    if col.col_type == "fk_int":
        if not raw:
            if col.required:
                raise ValueError("Обязательное поле")
            return None
        return int(raw)
    if col.col_type == "numeric":
        if not raw:
            return None if not col.required else (_ for _ in ()).throw(ValueError("Обязательное поле"))
        try:
            return Decimal(raw.replace(",", "."))
        except InvalidOperation as e:
            raise ValueError("Некорректное число") from e
    if col.col_type == "date":
        if not raw:
            return None if not col.required else (_ for _ in ()).throw(ValueError("Обязательное поле"))
        parts = raw.split(".")
        if len(parts) == 3 and len(parts[2]) == 4:
            d, m, y = parts
            return date(int(y), int(m), int(d))
        return date.fromisoformat(raw)
    if col.col_type == "timestamp":
        return datetime.fromisoformat(raw)
    if col.col_type == "bool":
        p = parse_bool(raw)
        if p is None:
            raise ValueError("Введите да или нет")
        return p
    raise ValueError(f"Неизвестный тип: {col.col_type}")


def format_cell(v: Any, col: Col) -> str:
    if v is None:
        return ""
    if col.col_type == "bool":
        return format_bool(v)
    if col.col_type == "numeric":
        return str(v)
    if col.col_type in ("date", "timestamp"):
        return str(v)
    return str(v)


def prompt_line(label: str, default: Optional[str] = None) -> str:
    hint = f" [{default}]" if default is not None else ""
    s = input(f"{label}{hint}: ").strip()
    if not s and default is not None:
        return default
    return s
# --- crud ---
def _quote_ident(ident: str) -> sql.SQL:
    return sql.Identifier(ident)


def _editable_columns(spec: TableSpec) -> List[Col]:
    return [c for c in spec.columns if c.editable]


def _col_by_sql(spec: TableSpec, name: str) -> Optional[Col]:
    for c in spec.columns:
        if c.sql == name:
            return c
    return None


def _validate_sort(spec: TableSpec, sort_field: str) -> str:
    allowed = {c.sql for c in spec.columns}
    if sort_field not in allowed:
        raise ValueError("Недопустимое поле сортировки")
    return sort_field


def _validate_filter_search(spec: TableSpec, field: str, mode: str) -> str:
    if mode == "search":
        allowed = set(spec.searchable)
    else:
        allowed = set(spec.filterable)
    if field not in allowed:
        raise ValueError("Недопустимое поле для условия")
    return field


def list_rows(
    spec: TableSpec,
    *,
    offset: int = 0,
    limit: int = 20,
    sort_field: Optional[str] = None,
    sort_dir: str = "ASC",
    filters: Optional[Dict[str, str]] = None,
    search: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    filters = filters or {}
    search = search or {}
    order_col = sort_field or spec.order_by_default[0]
    order_col = _validate_sort(spec, order_col)
    direction = "DESC" if sort_dir.upper() == "DESC" else "ASC"
    order_parts = [sql.SQL("{} {}").format(_quote_ident(order_col), sql.SQL(direction))]
    for extra in spec.order_by_default:
        if extra != order_col:
            order_parts.append(sql.SQL("{} ASC").format(_quote_ident(extra)))

    where_clauses: List[sql.Composable] = []
    params: List[Any] = []

    for fname, fval in filters.items():
        if not fval.strip():
            continue
        fname = _validate_filter_search(spec, fname, "filter")
        col = _col_by_sql(spec, fname)
        if col and col.col_type == "bool":
            b = parse_bool(fval)
            if b is None:
                continue
            where_clauses.append(sql.SQL("{} = %s").format(_quote_ident(fname)))
            params.append(b)
        elif col and col.col_type in ("int", "fk_int", "serial"):
            where_clauses.append(sql.SQL("{} = %s").format(_quote_ident(fname)))
            params.append(int(fval))
        else:
            where_clauses.append(sql.SQL("{} = %s").format(_quote_ident(fname)))
            params.append(fval)

    for sname, sval in search.items():
        if not sval.strip():
            continue
        sname = _validate_filter_search(spec, sname, "search")
        where_clauses.append(sql.SQL("{} ILIKE %s").format(_quote_ident(sname)))
        params.append(f"%{sval}%")

    where_sql = sql.SQL("TRUE")
    if where_clauses:
        where_sql = sql.SQL(" AND ").join(where_clauses)

    order_sql = sql.SQL(", ").join(order_parts)
    query = sql.SQL(
        "SELECT * FROM {tbl} WHERE {where} ORDER BY {ord} OFFSET %s LIMIT %s"
    ).format(tbl=_quote_ident(spec.sql_name), where=where_sql, ord=order_sql)

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params + [offset, limit])
            return list(cur.fetchall())


def count_rows(
    spec: TableSpec,
    *,
    filters: Optional[Dict[str, str]] = None,
    search: Optional[Dict[str, str]] = None,
) -> int:
    filters = filters or {}
    search = search or {}
    where_clauses: List[sql.Composable] = []
    params: List[Any] = []

    for fname, fval in filters.items():
        if not fval.strip():
            continue
        fname = _validate_filter_search(spec, fname, "filter")
        col = _col_by_sql(spec, fname)
        if col and col.col_type == "bool":
            b = parse_bool(fval)
            if b is None:
                continue
            where_clauses.append(sql.SQL("{} = %s").format(_quote_ident(fname)))
            params.append(b)
        elif col and col.col_type in ("int", "fk_int", "serial"):
            where_clauses.append(sql.SQL("{} = %s").format(_quote_ident(fname)))
            params.append(int(fval))
        else:
            where_clauses.append(sql.SQL("{} = %s").format(_quote_ident(fname)))
            params.append(fval)

    for sname, sval in search.items():
        if not sval.strip():
            continue
        sname = _validate_filter_search(spec, sname, "search")
        where_clauses.append(sql.SQL("{} ILIKE %s").format(_quote_ident(sname)))
        params.append(f"%{sval}%")

    where_sql = sql.SQL("TRUE")
    if where_clauses:
        where_sql = sql.SQL(" AND ").join(where_clauses)

    query = sql.SQL("SELECT COUNT(*) AS c FROM {tbl} WHERE {w}").format(
        tbl=_quote_ident(spec.sql_name), w=where_sql
    )
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return int(row["c"]) if row else 0


def get_by_pk(spec: TableSpec, pk_values: Tuple[Any, ...]) -> Optional[Dict[str, Any]]:
    if len(pk_values) != len(spec.pk):
        raise ValueError("Неверный состав первичного ключа")
    parts = [sql.SQL("{} = %s").format(_quote_ident(k)) for k in spec.pk]
    where_sql = sql.SQL(" AND ").join(parts)
    query = sql.SQL("SELECT * FROM {t} WHERE {w}").format(
        t=_quote_ident(spec.sql_name), w=where_sql
    )
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, list(pk_values))
            row = cur.fetchone()
            return dict(row) if row else None


def insert_row(spec: TableSpec, values: Dict[str, Any]) -> Tuple[Any, ...]:
    cols = [c.sql for c in _editable_columns(spec) if c.sql in values]
    if not cols:
        raise ValueError("Нет данных для вставки")
    col_ids = sql.SQL(", ").join(map(_quote_ident, cols))
    placeholders = sql.SQL(", ").join(sql.Placeholder() * len(cols))
    returning = sql.SQL(", ").join(map(_quote_ident, spec.pk))
    q = sql.SQL("INSERT INTO {t} ({c}) VALUES ({p}) RETURNING {r}").format(
        t=_quote_ident(spec.sql_name),
        c=col_ids,
        p=placeholders,
        r=returning,
    )
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q, [values[c] for c in cols])
            return cur.fetchone()


def update_row(spec: TableSpec, pk_values: Tuple[Any, ...], values: Dict[str, Any]) -> int:
    if len(pk_values) != len(spec.pk):
        raise ValueError("Неверный состав первичного ключа")
    sets = []
    params: List[Any] = []
    for c in _editable_columns(spec):
        if c.sql in values:
            sets.append(sql.SQL("{} = %s").format(_quote_ident(c.sql)))
            params.append(values[c.sql])
    if not sets:
        return 0
    set_sql = sql.SQL(", ").join(sets)
    wh = [sql.SQL("{} = %s").format(_quote_ident(k)) for k in spec.pk]
    where_sql = sql.SQL(" AND ").join(wh)
    params.extend(list(pk_values))
    q = sql.SQL("UPDATE {t} SET {s} WHERE {w}").format(
        t=_quote_ident(spec.sql_name), s=set_sql, w=where_sql
    )
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q, params)
            return cur.rowcount


def delete_row(spec: TableSpec, pk_values: Tuple[Any, ...]) -> int:
    if len(pk_values) != len(spec.pk):
        raise ValueError("Неверный состав первичного ключа")
    wh = [sql.SQL("{} = %s").format(_quote_ident(k)) for k in spec.pk]
    where_sql = sql.SQL(" AND ").join(wh)
    q = sql.SQL("DELETE FROM {t} WHERE {w}").format(
        t=_quote_ident(spec.sql_name), w=where_sql
    )
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q, list(pk_values))
            return cur.rowcount
# --- forms ---
from typing import Any, Dict, List

from psycopg2.extras import RealDictCursor



def _prompt_col(col: Col, default: Any = None) -> Any:
    d = None
    if default is not None and col.col_type == "bool":
        d = format_bool(default)
    elif default is not None:
        d = str(default)
    while True:
        raw = prompt_line(col.label, d)
        try:
            return parse_value(raw, col)
        except ValueError as e:
            print(f"Ошибка: {e}")


def wizard_apartment_with_residents():
    """Сначала создаётся квартира, затем — произвольное число жильцов."""
    apt_spec = get_spec("apartments")
    res_spec = get_spec("residents")

    print("\n=== Форма: квартира и жильцы (1:М) ===")
    print("Шаг 1. Реквизиты квартиры")
    apt_values: Dict[str, Any] = {}
    for col in apt_spec.columns:
        if not col.editable:
            continue
        apt_values[col.sql] = _prompt_col(col)

    residents_payload: List[Dict[str, Any]] = []
    print("\nШаг 2. Жильцы (пустое ФИО — завершить список)")
    while True:
        name = prompt_line("ФИО жильца (пусто — конец)")
        if not name.strip():
            break
        row: Dict[str, Any] = {"full_name": name}
        for col in res_spec.columns:
            if col.sql in ("resident_id", "apartment_id", "full_name"):
                continue
            if not col.editable:
                continue
            row[col.sql] = _prompt_col(col)
        residents_payload.append(row)

    if not residents_payload:
        print("Нет жильцов — квартира не будет создана.")
        return

    apt_cols = list(apt_values.keys())
    apt_placeholders = ", ".join(["%s"] * len(apt_cols))
    apt_sql = f"INSERT INTO apartments ({', '.join(apt_cols)}) VALUES ({apt_placeholders}) RETURNING apartment_id"

    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(apt_sql, [apt_values[c] for c in apt_cols])
            apt_id = cur.fetchone()["apartment_id"]
            ins_res = """
                INSERT INTO residents (apartment_id, full_name, inn, passport_series_no,
                    birth_date, is_primary_tenant, payer_code_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
            """
            for r in residents_payload:
                cur.execute(
                    ins_res,
                    [
                        apt_id,
                        r["full_name"],
                        r.get("inn"),
                        r.get("passport_series_no"),
                        r["birth_date"],
                        r["is_primary_tenant"],
                        r.get("payer_code_id"),
                    ],
                )
    print(f"\nГотово: квартира apartment_id={apt_id}, жильцов: {len(residents_payload)}.")
# --- reports ---
from collections import defaultdict
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from psycopg2.extras import RealDictCursor



def _prompt_sort(allowed: List[str], default: str) -> Tuple[str, str]:
    print("Доступные поля сортировки:", ", ".join(allowed))
    field = prompt_line("Поле сортировки", default)
    if field not in allowed:
        print(f"Неверное поле, используется {default}")
        field = default
    direction = prompt_line("Направление (ASC/DESC)", "ASC").upper()
    if direction not in ("ASC", "DESC"):
        direction = "ASC"
    return field, direction


def report_kvartplata():
    """Отчёт «Квартплата»: квартиры, дома, тарифы, доля оплаты; группировка по улице."""
    print("\n=== Отчёт: начисление квартплаты (несколько таблиц) ===")
    street = prompt_line("Фильтр: улица содержит (пусто — все)", "")
    min_area = prompt_line("Фильтр: мин. общая площадь (пусто — нет)", "")
    max_area = prompt_line("Фильтр: макс. общая площадь (пусто — нет)", "")
    precinct = prompt_line("Фильтр: номер изб. участка (пусто — все)", "")

    allowed_sort = ["street", "apt_number", "total_area_sqm", "monthly_charge", "pay_pct"]
    sort_field, sort_dir = _prompt_sort(allowed_sort, "street")

    min_a: Optional[Decimal] = Decimal(min_area) if min_area.strip() else None
    max_a: Optional[Decimal] = Decimal(max_area) if max_area.strip() else None
    prec: Optional[int] = int(precinct) if precinct.strip() else None
    st = f"%{street}%" if street.strip() else None

    sql = """
WITH base AS (
    SELECT
        h.street,
        h.house_number,
        h.building_corpus,
        a.apt_number,
        a.total_area_sqm,
        tr.rate_per_sqm,
        COALESCE(
            (
                SELECT pc.payment_percent
                FROM residents r
                JOIN payer_codes pc ON pc.code_id = r.payer_code_id
                WHERE r.apartment_id = a.apartment_id AND r.is_primary_tenant
                LIMIT 1
            ),
            (
                SELECT pc.payment_percent
                FROM residents r
                JOIN payer_codes pc ON pc.code_id = r.payer_code_id
                WHERE r.apartment_id = a.apartment_id
                ORDER BY r.resident_id
                LIMIT 1
            ),
            100::numeric
        ) AS pay_pct
    FROM apartments a
    JOIN houses h ON h.house_id = a.house_id
    JOIN LATERAL (
        SELECT t.*
        FROM tariffs t
        WHERE t.has_cold_water = a.has_cold_water
          AND t.has_hot_water = a.has_hot_water
          AND t.has_garbage_chute = a.has_garbage_chute
          AND t.has_elevator = a.has_elevator
        ORDER BY t.valid_from DESC
        LIMIT 1
    ) tr ON TRUE
    LEFT JOIN election_precincts ep ON ep.precinct_id = a.election_precinct_id_snapshot
    WHERE (%(st)s IS NULL OR h.street ILIKE %(st)s)
      AND (%(min_a)s IS NULL OR a.total_area_sqm >= %(min_a)s)
      AND (%(max_a)s IS NULL OR a.total_area_sqm <= %(max_a)s)
      AND (%(prec)s IS NULL OR ep.precinct_number = %(prec)s)
)
SELECT
    street,
    house_number,
    building_corpus,
    apt_number,
    total_area_sqm,
    rate_per_sqm,
    pay_pct,
    ROUND(total_area_sqm * rate_per_sqm * pay_pct / 100.0, 2) AS monthly_charge
FROM base
"""

    params = {"st": st, "min_a": min_a, "max_a": max_a, "prec": prec}
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows: List[Dict[str, Any]] = [dict(r) for r in cur.fetchall()]

    # Сортировка в Python по вычисляемому полю / подмножеству
    reverse = sort_dir == "DESC"
    rows.sort(key=lambda r: r[sort_field], reverse=reverse)

    by_street: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_street[r["street"]].append(r)

    grand = Decimal("0")
    print("\nДетализация по улицам (группировка 1-го уровня):")
    for street_name in sorted(by_street.keys()):
        chunk = by_street[street_name]
        sub = sum((r["monthly_charge"] for r in chunk), Decimal("0"))
        grand += sub
        print(f"\n--- Улица: {street_name} (квартир: {len(chunk)}, сумма: {sub}) ---")
        for r in chunk:
            corp = (r["building_corpus"] or "").strip()
            corp_s = f" корп. {corp}" if corp else ""
            print(
                f"  д. {r['house_number']}{corp_s}, кв. {r['apt_number']}: "
                f"S={r['total_area_sqm']} м², тариф={r['rate_per_sqm']}, "
                f"доля={r['pay_pct']}%, начислено={r['monthly_charge']}"
            )
        print(f"  Итого по улице: {sub}")
    print(f"\n>>> ВСЕГО по отчёту: {grand}")


def report_electoral_lists():
    """Список жильцов для избирательных участков."""
    print("\n=== Отчёт: жильцы по избирательным участкам ===")
    precinct = prompt_line("Фильтр: номер участка (пусто — все)", "")
    only_primary = prompt_line("Только ответственные (да/нет)", "нет")

    prim = parse_bool(only_primary)
    only_pr = prim is True
    prec_val: Optional[int] = int(precinct) if precinct.strip() else None

    allowed_sort = ["precinct_number", "full_name", "birth_date", "street"]
    sort_field, sort_dir = _prompt_sort(allowed_sort, "precinct_number")

    sql = """
SELECT
    ep.precinct_number,
    ep.title AS precinct_title,
    h.street,
    h.house_number,
    a.apt_number,
    r.full_name,
    r.birth_date,
    r.is_primary_tenant,
    (EXTRACT(YEAR FROM age(current_date, r.birth_date)))::int AS age_years
FROM residents r
JOIN apartments a ON a.apartment_id = r.apartment_id
JOIN houses h ON h.house_id = a.house_id
LEFT JOIN election_precincts ep ON ep.precinct_id = a.election_precinct_id_snapshot
WHERE (%(prec)s IS NULL OR ep.precinct_number = %(prec)s)
  AND (%(only_pr)s::boolean = FALSE OR r.is_primary_tenant = TRUE)
"""
    params = {"prec": prec_val, "only_pr": only_pr}
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(x) for x in cur.fetchall()]

    reverse = sort_dir == "DESC"
    rows.sort(key=lambda r: r[sort_field], reverse=reverse)

    by_prec: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        key = int(r["precinct_number"] or 0)
        by_prec[key].append(r)

    print("\nГруппировка по избирательному участку:")
    total_people = 0
    for pnum in sorted(by_prec.keys()):
        chunk = by_prec[pnum]
        total_people += len(chunk)
        title = chunk[0]["precinct_title"] if chunk else ""
        print(f"\n--- Участок №{pnum} ({title}) — человек: {len(chunk)} ---")
        for r in chunk:
            pr = "да" if r["is_primary_tenant"] else "нет"
            print(
                f"  {r['full_name']}, {r['birth_date']}, возраст {r['age_years']}, "
                f"ответств.: {pr}, адрес: {r['street']} {r['house_number']}, кв. {r['apt_number']}"
            )
        avg_age = sum(r["age_years"] for r in chunk) / len(chunk) if chunk else 0
        print(f"  Средний возраст по участку: {avg_age:.1f}")
    print(f"\n>>> Всего записей: {total_people}")


def report_department_summary():
    """Сводка по отделам: дома, квартиры, площади (агрегация)."""
    print("\n=== Отчёт: сводка по отделам служб ===")
    svc = prompt_line("Фильтр: код службы service_id (пусто — все)", "")
    min_apartments = prompt_line("Только отделы с числом квартир не меньше (пусто — 1)", "")

    svc_id: Optional[int] = int(svc) if svc.strip() else None
    min_apt = int(min_apartments) if min_apartments.strip() else 1

    allowed_sort = ["dept_name", "apartments_cnt", "houses_cnt", "sum_area", "avg_area"]
    sort_field, sort_dir = _prompt_sort(allowed_sort, "apartments_cnt")

    sql = """
SELECT
    d.service_id,
    d.dept_id,
    d.name AS dept_name,
    COUNT(DISTINCT h.house_id) AS houses_cnt,
    COUNT(a.apartment_id) AS apartments_cnt,
    COALESCE(SUM(a.total_area_sqm), 0) AS sum_area,
    CASE WHEN COUNT(a.apartment_id) > 0
         THEN ROUND(SUM(a.total_area_sqm) / COUNT(a.apartment_id), 2)
         ELSE 0 END AS avg_area
FROM service_departments d
LEFT JOIN houses h
    ON h.service_id = d.service_id AND h.dept_id = d.dept_id
LEFT JOIN apartments a ON a.house_id = h.house_id
WHERE (%(svc)s IS NULL OR d.service_id = %(svc)s)
GROUP BY d.service_id, d.dept_id, d.name
HAVING COUNT(a.apartment_id) >= %(min_apt)s
"""
    params = {"svc": svc_id, "min_apt": min_apt}
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = [dict(x) for x in cur.fetchall()]

    reverse = sort_dir == "DESC"
    rows.sort(key=lambda r: r[sort_field], reverse=reverse)

    print("\nГруппировка по отделу (итоги по службе/отделу):")
    sum_apts = 0
    sum_houses = 0
    sum_area = Decimal("0")
    for r in rows:
        sum_apts += int(r["apartments_cnt"])
        sum_houses += int(r["houses_cnt"])
        sum_area += Decimal(str(r["sum_area"]))
        print(
            f"{r['dept_name']} (служба {r['service_id']}, отдел {r['dept_id']}): "
            f"домов {r['houses_cnt']}, квартир {r['apartments_cnt']}, "
            f"суммарная площадь {r['sum_area']} м², ср. площадь кв. {r['avg_area']} м²"
        )
    print(
        f"\n>>> ИТОГО: отделов в выборке {len(rows)}, "
        f"домов {sum_houses}, квартир {sum_apts}, площадь {sum_area} м²"
    )
# --- main ---
PAGE_SIZE = 5

TABLE_MENU_ORDER = [
    "services",
    "service_departments",
    "maintenance_sites",
    "election_precincts",
    "payer_codes",
    "tariffs",
    "houses",
    "apartments",
    "residents",
]

VIEWS = [
    ("v_services_list", "Представление: службы (одна таблица + вычисляемое поле)"),
    ("v_apartments_with_house_service", "Представление: квартиры с адресом и службой (JOIN)"),
    ("v_sites_with_multiple_houses", "Представление: участки с >=2 домами (GROUP BY/HAVING)"),
    ("v_precinct_residents_grouped", "Представление: жильцы по участкам (GROUP BY/HAVING)"),
]


def _print_row(spec: TableSpec, row: Dict[str, Any]) -> None:
    for c in spec.columns:
        if c.sql in row:
            print(f"  {c.label}: {format_cell(row.get(c.sql), c)}")


def _parse_pk(spec: TableSpec, s: str) -> Tuple[Any, ...]:
    parts = [p.strip() for p in s.split(",") if p.strip() != ""]
    if len(parts) != len(spec.pk):
        raise ValueError(f"Ожидается {len(spec.pk)} значений через запятую")
    out: List[Any] = []
    for i, p in enumerate(parts):
        col_name = spec.pk[i]
        col = next(c for c in spec.columns if c.sql == col_name)
        out.append(parse_value(p, col))
    return tuple(out)


def browse_table(key: str) -> None:
    spec = get_spec(key)
    offset = 0
    sort_field = spec.order_by_default[0]
    sort_dir = "ASC"
    filters: Dict[str, str] = {}
    search: Dict[str, str] = {}

    while True:
        total = count_rows(spec, filters=filters, search=search)
        rows = list_rows(
            spec,
            offset=offset,
            limit=PAGE_SIZE,
            sort_field=sort_field,
            sort_dir=sort_dir,
            filters=filters,
            search=search,
        )
        print(f"\n=== {spec.title} ===")
        print(f"Всего записей (с учётом фильтров): {total}. Показ с {offset + 1} по {offset + len(rows)}.")
        print(f"Сортировка: {sort_field} {sort_dir}")
        if filters:
            print("Фильтры:", filters)
        if search:
            print("Поиск:", search)
        preview_col = next((c.sql for c in spec.columns if c.sql not in spec.pk), None)
        for idx, row in enumerate(rows):
            print(f"[{idx}] ", end="")
            pk_show = ", ".join(str(row[k]) for k in spec.pk)
            extra = row.get(preview_col, "") if preview_col else ""
            print(f"PK=({pk_show}) {extra}")
        print(
            "Команды: n — вперёд, p — назад, b — в начало, g — к смещению, "
            "s — поиск, f — фильтр, o — сортировка, a — добавить, "
            "e — правка по PK, d — удалить по PK, c — сбросить фильтры/поиск, q — назад"
        )
        cmd = prompt_line("Команда", "q").lower()
        if cmd == "q":
            return
        if cmd == "n":
            if total == 0:
                offset = 0
            else:
                last_page_start = ((total - 1) // PAGE_SIZE) * PAGE_SIZE
                offset = min(offset + PAGE_SIZE, last_page_start)
        if cmd == "p":
            offset = max(0, offset - PAGE_SIZE)
        if cmd == "b":
            offset = 0
        if cmd == "g":
            try:
                off = int(prompt_line("Смещение (offset)", str(offset)))
                offset = max(0, min(max(total - 1, 0), off))
            except ValueError:
                print("Некорректное число")
        if cmd == "s":
            print("Доступные поля поиска:", ", ".join(spec.searchable))
            field = prompt_line("Поле")
            if field in spec.searchable:
                search[field] = prompt_line("Подстрока")
            else:
                print("Поле недопустимо")
        if cmd == "f":
            print("Доступные поля фильтра:", ", ".join(spec.filterable))
            field = prompt_line("Поле")
            if field in spec.filterable:
                filters[field] = prompt_line("Точное значение")
            else:
                print("Поле недопустимо")
        if cmd == "o":
            opts = ", ".join(sortable_columns(spec))
            print("Поля:", opts)
            sort_field = prompt_line("Поле", sort_field)
            sort_dir = prompt_line("ASC/DESC", sort_dir).upper() or "ASC"
            try:
                list_rows(
                    spec,
                    offset=0,
                    limit=1,
                    sort_field=sort_field,
                    sort_dir=sort_dir,
                    filters=filters,
                    search=search,
                )
            except Exception as e:
                print(f"Ошибка сортировки: {e}")
                sort_field = spec.order_by_default[0]
                sort_dir = "ASC"
        if cmd == "c":
            filters.clear()
            search.clear()
            offset = 0
        if cmd == "a":
            try:
                vals: Dict[str, Any] = {}
                for col in spec.columns:
                    if not col.editable:
                        continue
                    raw = prompt_line(col.label + (" *" if col.required else ""))
                    vals[col.sql] = parse_value(raw, col)
                new_pk = insert_row(spec, vals)
                print("Создана запись, PK:", new_pk)
            except Exception as e:
                print(f"Ошибка вставки: {e}")
        if cmd == "e":
            try:
                pk_s = prompt_line("PK через запятую")
                pk = _parse_pk(spec, pk_s)
                row = get_by_pk(spec, pk)
                if not row:
                    print("Не найдено")
                    continue
                print("Текущие значения:")
                _print_row(spec, row)
                updates: Dict[str, Any] = {}
                for col in spec.columns:
                    if not col.editable:
                        continue
                    cur = row.get(col.sql)
                    disp = format_cell(cur, col) if cur is not None else ""
                    raw = prompt_line(f"{col.label} (пусто — оставить)", disp)
                    if raw == "" or raw == disp:
                        continue
                    updates[col.sql] = parse_value(raw, col)
                if updates:
                    n = update_row(spec, pk, updates)
                    print("Обновлено строк:", n)
            except Exception as e:
                print(f"Ошибка: {e}")
        if cmd == "d":
            try:
                pk_s = prompt_line("PK через запятую")
                pk = _parse_pk(spec, pk_s)
                n = delete_row(spec, pk)
                print("Удалено строк:", n)
            except Exception as e:
                print(f"Ошибка: {e}")


def browse_views() -> None:
    print("\n=== Представления (VIEW) в базе ===")
    for i, (name, desc) in enumerate(VIEWS, 1):
        print(f"{i}. {name} — {desc}")
    choice = prompt_line("Номер (q — назад)", "q")
    if choice.lower() == "q":
        return
    try:
        idx = int(choice) - 1
        name = VIEWS[idx][0]
    except (ValueError, IndexError):
        print("Неверный выбор")
        return
    lim = int(prompt_line("LIMIT", "50"))
    allowed = {v[0] for v in VIEWS}
    if name not in allowed:
        print("Внутренняя ошибка: неизвестное представление")
        return
    q = sql.SQL("SELECT * FROM {} LIMIT %s").format(sql.Identifier(name))
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q, (lim,))
            rows = cur.fetchall()
    for r in rows:
        print(dict(r))


def reports_menu() -> None:
    while True:
        print("\n=== Отчёты ===")
        print("1. Квартплата (тарифы, площади, льготы)")
        print("2. Жильцы по избирательным участкам")
        print("3. Сводка по отделам (агрегация по дому/квартирам)")
        print("q. Назад")
        c = prompt_line("Выбор", "q").lower()
        if c == "q":
            return
        if c == "1":
            try:
                report_kvartplata()
            except Exception as e:
                print(f"Ошибка отчёта: {e}")
        elif c == "2":
            try:
                report_electoral_lists()
            except Exception as e:
                print(f"Ошибка отчёта: {e}")
        elif c == "3":
            try:
                report_department_summary()
            except Exception as e:
                print(f"Ошибка отчёта: {e}")


def tables_menu() -> None:
    while True:
        print("\n=== Таблицы ===")
        for i, k in enumerate(TABLE_MENU_ORDER, 1):
            print(f"{i}. {TABLE_SPECS[k].title} ({k})")
        print("q. Назад")
        c = prompt_line("Выбор", "q").lower()
        if c == "q":
            return
        try:
            idx = int(c) - 1
            key = TABLE_MENU_ORDER[idx]
        except (ValueError, IndexError):
            print("Неверный выбор")
            continue
        browse_table(key)


def main() -> None:
    print("Служба заказчика ГЖУ — консоль клиента PostgreSQL")
    print("Параметры подключения: переменные PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD")
    while True:
        print("\n=== Главное меню ===")
        print("1. Работа с таблицами (просмотр, поиск, фильтр, сортировка, CRUD)")
        print("2. Представления (VIEW)")
        print("3. Отчёты")
        print("4. Форма: квартира + жильцы (1:М)")
        print("q. Выход")
        c = prompt_line("Выбор", "q").lower()
        if c == "q":
            print("До свидания.")
            return
        if c == "1":
            tables_menu()
        elif c == "2":
            browse_views()
        elif c == "3":
            reports_menu()
        elif c == "4":
            try:
                wizard_apartment_with_residents()
            except Exception as e:
                print(f"Ошибка формы: {e}")
        else:
            print("Неизвестная команда")


if __name__ == "__main__":
    main()
