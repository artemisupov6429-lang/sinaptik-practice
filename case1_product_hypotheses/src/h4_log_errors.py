"""Гипотеза 4: типовые ошибки клиентов связаны с повторяющимися паттернами поведения и окружения."""
import sys
from pathlib import Path
import pandas as pd
from common import RESULTS, read_table, to_dt, md_table
from logs_parser import parse_logs

FEATURES = {"http400_server_config": "HTTP 400 на выбор сервера",
            "dns_api_fail": "DNS не находит api.pipster.win",
            "mobile_only": "только мобильная сеть",
            "whitelist_detected": "белые списки оператора",
            "splash_fail": "не загрузилась стартовая информация",
            "time_limit": "обрыв по лимиту времени",
            "traffic_limit": "обрыв по лимиту трафика"}


def paid_at(sessions: pd.DataFrame, db: Path) -> pd.Series:
    sub = read_table(db, "subscribe", usecols=["user_id", "created_at", "expired_time"])
    sub = sub[sub.user_id.isin(set(sessions.user_id))]
    sub["st"], sub["en"] = to_dt(sub.created_at), to_dt(sub.expired_time.astype(str).str[:19])
    m = sessions[["user_id", "t"]].reset_index().merge(sub, on="user_id", how="left")
    m["active"] = (m.st <= m.t) & (m.en >= m.t)
    return m.groupby("index").active.any().reindex(sessions.index, fill_value=False)


def run(db: Path, sessions: pd.DataFrame | None = None) -> str:
    if sessions is None:
        sessions, _ = parse_logs(db)
    s = sessions.copy()
    s["paid"] = paid_at(s, db)
    tried = s[s.vpn_start > 0].assign(fail=lambda x: x.vpn_connected == 0)
    rows = []
    for col, name in FEATURES.items():
        a, b = tried[tried[col] > 0], tried[tried[col] == 0]
        rows.append({"признак": name, "доля всех сессий, %": round((s[col] > 0).mean() * 100, 1),
                     "попыток с признаком": len(a), "неудач с признаком, %": round(a.fail.mean() * 100, 1) if len(a) else None,
                     "неудач без признака, %": round(b.fail.mean() * 100, 1)})
    feat = pd.DataFrame(rows)
    feat.to_csv(RESULTS / "h4_failure_by_feature.csv", index=False)

    free = s[~s.paid]
    weekly = (free.assign(week=free.t.dt.to_period("W").dt.start_time.dt.date)
                  .groupby("week").http400_server_config.agg(сессий="size", доля_400=lambda x: round((x > 0).mean() * 100, 1))
                  .query("сессий >= 100").reset_index())
    weekly.to_csv(RESULTS / "h4_http400_by_week.csv", index=False)
    by_paid = s.groupby("paid").http400_server_config.apply(lambda x: int((x > 0).sum()))

    sep = read_table(db, "user_connection_logs", file="user_connection_logs_09_26.csv",
                     usecols=["user_id", "subscribe_id", "created_at"], dtype={"subscribe_id": str, "created_at": str})
    sep["d"], sep["free"] = sep.created_at.str[:10], sep.subscribe_id.isna()
    dau = sep.groupby(["d", "free"]).user_id.nunique().unstack().rename(columns={True: "бесплатные", False: "платные"})
    dau.to_csv(RESULTS / "h4_daily_users_sep.csv")
    return (f"## Гипотеза 4. Паттерны типовых ошибок\n\n"
            f"Разобрано сессий: {len(s):,} от {s.user_id.nunique()} пользователей; с попыткой подключения: {len(tried)}. "
            f"Сессий с HTTP 400: у бесплатных {by_paid.get(False, 0)}, у платных {by_paid.get(True, 0)}.\n\n"
            f"{md_table(feat)}\n\nДоля сессий бесплатных пользователей с HTTP 400 по неделям:\n\n{md_table(weekly)}\n\n"
            f"Бесплатных пользователей с подключением в день (сентябрь 2026) — см. results/h4_daily_users_sep.csv.\n")


if __name__ == "__main__":
    print(run(Path(sys.argv[1])))
