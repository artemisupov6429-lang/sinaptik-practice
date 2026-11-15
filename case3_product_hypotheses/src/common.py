"""Общие функции: чтение выгрузки БД и путей к данным."""
from pathlib import Path
import pandas as pd

RESULTS = Path(__file__).resolve().parent.parent / "results"
RESULTS.mkdir(exist_ok=True)


def columns(db: Path, table: str) -> list[str]:
    """Имена колонок таблицы берутся из db_structure/<table>.csv (первая строка)."""
    first = (db / "db_structure" / f"{table}.csv").read_text(encoding="utf-8-sig").splitlines()[0]
    return first.strip().split(";")


def read_table(db: Path, table: str, usecols=None, file: str | None = None, **kw) -> pd.DataFrame:
    """Читает CSV из выгрузки. В выгрузке нет строки заголовка, кроме user_connection_logs_*."""
    path = db / (file or f"{table}.csv")
    names = columns(db, table)
    with open(path, encoding="utf-8-sig") as f:
        has_header = f.readline().startswith(names[0] + ";" + names[1])
    return pd.read_csv(path, sep=";", header=0 if has_header else None, names=names,
                       usecols=usecols, encoding="utf-8-sig", low_memory=False, **kw)


def to_dt(s: pd.Series) -> pd.Series:
    """Время без часового пояса (в выгрузке встречаются суффиксы +03)."""
    return pd.to_datetime(s.astype(str).str[:26], format="mixed", errors="coerce")


def load_orders(db: Path) -> pd.DataFrame:
    o = read_table(db, "orders")
    o["t"] = to_dt(o.created_at)
    return o


def load_users(db: Path) -> pd.DataFrame:
    u = read_table(db, "users", usecols=["id", "email", "created_at", "role", "is_was_guest"])
    # created_at в users записан на 3 часа позже, чем время заказов (МСК против UTC)
    u["reg"] = to_dt(u.created_at) - pd.Timedelta(hours=3)
    u["domain"] = u.email.astype(str).str.split("@").str[1]
    return u


def first_purchases(orders: pd.DataFrame) -> pd.DataFrame:
    """Первый оплаченный триал и первая оплаченная полная подписка по пользователю."""
    paid = orders[orders.status == "paid"]
    trial = paid[paid.trial == "t"].groupby("user_id").t.min().rename("trial_t")
    full = paid[paid.trial == "f"].groupby("user_id").t.min().rename("pay_t")
    df = pd.concat([trial, full], axis=1)
    df["segment"] = "trial_only"
    df.loc[df.trial_t.isna(), "segment"] = "pay_no_trial"
    both = df.trial_t.notna() & df.pay_t.notna()
    df.loc[both & (df.pay_t > df.trial_t), "segment"] = "trial_then_pay"
    df.loc[both & (df.pay_t <= df.trial_t), "segment"] = "pay_then_trial"
    return df


def md_table(df: pd.DataFrame) -> str:
    """DataFrame -> markdown-таблица (без зависимости от tabulate)."""
    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(str(v) for v in row) + " |")
    return "\n".join(lines)
