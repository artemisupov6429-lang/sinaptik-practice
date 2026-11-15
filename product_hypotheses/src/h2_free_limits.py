"""Гипотеза 2: лимиты бесплатного тарифа (500 МБ/день, 15 ГБ/мес) выставлены неоптимально.

Источники:
  * клиентские логи (TrafficLimitBloc) — реальный расход трафика по дням; каждый просмотр рекламы +200 МБ;
  * adv_view_history — все просмотры рекламы за расширение лимита;
  * user_connection_logs_* — сколько дней в месяц бесплатный пользователь подключается.
"""
import sys
from pathlib import Path
import pandas as pd
from common import RESULTS, read_table, load_orders, load_users, md_table
from logs_parser import parse_logs

BASE = 524_288_000   # 500 МБ
AD_BONUS = 200_000_000


def traffic_from_logs(traffic: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    tr = traffic[traffic.limit != "null"].copy()
    tr["limit"] = tr.limit.astype("int64")
    tr["d"] = pd.to_datetime(tr.ts).dt.date
    day = tr.groupby(["user_id", "d"]).agg(used=("used", "max"), limit=("limit", "max")).reset_index()
    day["ads"] = ((day.limit - BASE) / AD_BONUS).round().astype(int)
    day["mb"] = day.used / 2**20
    day.to_csv(RESULTS / "h2_traffic_days.csv", index=False)
    stat = (day.assign(день=day.ads.gt(0).map({False: "без рекламы", True: "с рекламой"}))
               .groupby("день").mb.describe(percentiles=[.5, .75, .9])[["count", "50%", "75%", "90%", "max"]]
               .round(0).reset_index())
    return (f"Расход по клиентским логам: {day.user_id.nunique()} бесплатных пользователей, "
            f"{len(day)} пользователе-дней, МБ в день:\n\n{md_table(stat)}\n"), day


def ads(db: Path) -> str:
    a = read_table(db, "adv_view_history", usecols=["user_id", "created_at"], dtype={"created_at": str})
    a["d"] = a.created_at.str[:10]
    ud = a.groupby(["user_id", "d"]).size().rename("views").reset_index()
    payers = set(load_orders(db).query("status == 'paid'").user_id)
    pu = ud.groupby("user_id").views.max().to_frame("max_per_day")
    pu["paid"] = pu.index.isin(payers)
    pu["bucket"] = pd.cut(pu.max_per_day, [0, 1, 2, 5, 10, 20, 50, 10**6],
                          labels=["1", "2", "3–5", "6–10", "11–20", "21–50", "50+"])
    by = pu.groupby("bucket", observed=True).agg(пользователей=("paid", "size"), доля_платящих=("paid", "mean"))
    by["доля_платящих"] = (by["доля_платящих"] * 100).round(2)
    by.to_csv(RESULTS / "h2_pay_rate_by_ads.csv")
    users = load_users(db)
    base = users.id.isin(payers).mean() * 100
    heavy = ud.views > 10
    return (f"Просмотров рекламы: {len(a):,}, пользователей: {a.user_id.nunique():,}. "
            f"В день: медиана {ud.views.median():.0f}, 90-й перцентиль {ud.views.quantile(.9):.0f}. "
            f"Дни с >10 просмотрами: {heavy.mean():.1%} дней, {ud[heavy].views.sum() / ud.views.sum():.0%} просмотров.\n\n"
            f"Доля платящих по максимуму просмотров в день (по всей базе — {base:.2f}%):\n\n{md_table(by.reset_index())}\n")


def active_days(db: Path) -> str:
    rows = []
    for f in sorted(db.glob("user_connection_logs_*.csv")):
        l = read_table(db, "user_connection_logs", file=f.name, usecols=["user_id", "subscribe_id", "created_at"],
                       dtype={"subscribe_id": str, "created_at": str})
        l["m"], l["d"], l["free"] = l.created_at.str[:7], l.created_at.str[:10], l.subscribe_id.isna()
        g = l.groupby(["m", "user_id"]).agg(days=("d", "nunique"), free=("free", "mean")).reset_index()
        for m, gg in g.groupby("m"):
            fr = gg[gg.free > 0.5]
            rows.append({"месяц": m, "бесплатных": len(fr), "медиана дней": fr.days.median(),
                         "90-й перц. дней": fr.days.quantile(.9), "доля ≥20 дней, %": round((fr.days >= 20).mean() * 100, 1)})
    df = pd.DataFrame(rows)
    df.to_csv(RESULTS / "h2_active_days.csv", index=False)
    return f"Активные дни бесплатных пользователей в месяц:\n\n{md_table(df)}\n"


def run(db: Path, traffic: pd.DataFrame | None = None) -> str:
    if traffic is None:
        _, traffic = parse_logs(db)
    t_text, _ = traffic_from_logs(traffic)
    return "## Гипотеза 2. Лимиты бесплатного тарифа\n\n" + t_text + "\n" + ads(db) + "\n" + active_days(db)


if __name__ == "__main__":
    print(run(Path(sys.argv[1])))
