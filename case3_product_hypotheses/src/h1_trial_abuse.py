"""Гипотеза 1: пользователи заводят новые аккаунты ради повторного триала.

Признаки одного человека на нескольких аккаунтах:
  * один push-токен FCM (одна установка приложения),
  * один идентификатор устройства iOS (на Android в device_identifier лежит номер сборки прошивки — не годится),
  * одна банковская карта (первые 6 + последние 4 цифры + срок действия).
"""
import json
import sys
from pathlib import Path
import pandas as pd
from common import RESULTS, read_table, load_orders, load_users, first_purchases, md_table


def card_key(raw) -> str | None:
    try:
        d = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not d or "last4" not in d:
        return None
    return f"{d.get('first6')}*{d['last4']}*{d.get('expiry_month')}/{d.get('expiry_year')}"


def run(db: Path) -> str:
    orders = load_orders(db)
    trial_users = set(orders[(orders.trial == "t") & (orders.status == "paid")].user_id)

    dev = read_table(db, "devices", usecols=["user_id", "device_identifier", "os", "fcm_push_token"], dtype=str)
    dev["user_id"] = pd.to_numeric(dev.user_id)
    cards = read_table(db, "saved_payment_methods", usecols=["user_id", "card_info"])
    cards["card"] = cards.card_info.map(card_key)

    keys = {
        "push_token": dev[["user_id", "fcm_push_token"]].rename(columns={"fcm_push_token": "key"}),
        "ios_device": dev[dev.os == "ios"][["user_id", "device_identifier"]].rename(columns={"device_identifier": "key"}),
        "card": cards[["user_id", "card"]].rename(columns={"card": "key"}),
    }
    rows, flagged = [], set()
    for name, k in keys.items():
        k = k.dropna().query("key != ''").drop_duplicates()
        k = k[k.user_id.isin(trial_users)]
        per_key = k.groupby("key").user_id.nunique()
        multi = per_key[per_key >= 2]
        accs = set(k[k.key.isin(multi.index)].user_id)
        flagged |= accs
        rows.append({"признак": name, "ключей с ≥2 триалами": len(multi),
                     "триальных аккаунтов на них": len(accs), "максимум на ключ": int(per_key.max())})
    signals = pd.DataFrame(rows)
    signals.to_csv(RESULTS / "h1_signals.csv", index=False)

    # Ритм: пауза между соседними триалами на одном push-токене
    tt = orders[(orders.trial == "t") & (orders.status == "paid")].groupby("user_id").t.min()
    k = keys["push_token"].dropna().drop_duplicates()
    k = k[k.user_id.isin(tt.index)].assign(tt=lambda x: x.user_id.map(tt))
    k = k[k.groupby("key").user_id.transform("nunique") >= 2].sort_values(["key", "tt"])
    gap = (k.groupby("key").tt.diff().dropna().dt.total_seconds() / 86400)
    gaps = pd.cut(gap, [-1, 1, 3, 4, 7, 30, 10_000],
                  labels=["≤1 дн", "1–3 дн", "3–4 дн", "4–7 дн", "7–30 дн", ">30 дн"]).value_counts().sort_index()
    gaps.rename_axis("пауза").reset_index(name="пар").to_csv(RESULTS / "h1_gaps.csv", index=False)

    # Сравнение помеченных аккаунтов с остальными
    fp = first_purchases(orders)
    t = fp[fp.trial_t.notna()].copy()
    t["flagged"] = t.index.isin(flagged)
    t["converted"] = t.segment.eq("trial_then_pay")
    users = load_users(db).set_index("id")
    t["guest_origin"] = users.is_was_guest.reindex(t.index).eq("t")
    cmp = t.groupby("flagged").agg(аккаунтов=("converted", "size"),
                                   конверсия=("converted", "mean"),
                                   из_гостя=("guest_origin", "mean")).round(3)
    cmp.to_csv(RESULTS / "h1_flagged_vs_rest.csv")

    share = len(flagged) / len(trial_users)
    return (f"## Гипотеза 1. Повторные аккаунты ради триала\n\n"
            f"Аккаунтов с оплаченным триалом: {len(trial_users):,}. Помечено как повторные: "
            f"**{len(flagged):,} ({share:.1%})** — нижняя оценка.\n\n{md_table(signals)}\n\n"
            f"Пауза между соседними триалами на одном устройстве (медиана {gap.median():.1f} дн):\n\n"
            f"{md_table(gaps.rename_axis('пауза').reset_index(name='пар'))}\n\n"
            f"Помеченные против остальных:\n\n{md_table(cmp.reset_index())}\n")


if __name__ == "__main__":
    print(run(Path(sys.argv[1])))
