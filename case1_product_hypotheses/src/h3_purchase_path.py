"""Гипотеза 3: сколько живут на бесплатном тарифе до покупки; всегда ли покупка идёт через триал."""
import sys
from pathlib import Path
import pandas as pd
from common import RESULTS, load_orders, load_users, first_purchases, md_table

NAMES = {"trial_then_pay": "Триал → оплата", "trial_only": "Триал без оплаты",
         "pay_no_trial": "Оплата без триала", "pay_then_trial": "Оплата, потом триал"}


def run(db: Path) -> str:
    orders = load_orders(db)
    users = load_users(db).set_index("id")
    fp = first_purchases(orders)
    fp["reg"] = users.reg.reindex(fp.index)
    fp["first"] = fp[["trial_t", "pay_t"]].min(axis=1)
    days = (fp["first"] - fp.reg).dt.total_seconds() / 86400
    fp["когда"] = pd.cut(days, [-10**4, 1 / 24, 1, 7, 30, 90, 10**4],
                         labels=["<1 ч", "1 ч–1 дн", "1–7 дн", "7–30 дн", "30–90 дн", ">90 дн"])
    tab = (pd.crosstab(fp.когда, fp.segment.map(NAMES), normalize="columns") * 100).round(1)
    tab.to_csv(RESULTS / "h3_time_to_first_purchase.csv")
    seg = fp.segment.map(NAMES).value_counts().rename_axis("сценарий").reset_index(name="пользователей")
    seg.to_csv(RESULTS / "h3_segments.csv", index=False)

    tp = fp[fp.segment == "trial_then_pay"]
    hours = (tp.pay_t - tp.trial_t).dt.total_seconds() / 3600
    autopay = hours.between(72, 84).mean()
    trial_conv = (fp.segment == "trial_then_pay").sum() / fp.trial_t.notna().sum()
    npay = orders[(orders.status == "paid") & (orders.trial == "f")].groupby("user_id").size()
    rep = {name: (npay.reindex(fp[fp.segment == s].index).fillna(0) >= 2).mean()
           for s, name in [("trial_then_pay", "через триал"), ("pay_no_trial", "без триала")]}
    guests_paid = users.loc[users.index.isin(fp.index)].role.eq("guest").sum()
    return (f"## Гипотеза 3. Путь от бесплатного тарифа к покупке\n\n"
            f"Платили: {len(fp):,}. Первая покупка — триал: {fp.trial_t.notna().mean():.0%}. "
            f"Первая покупка в первый час после регистрации: {(days < 1/24).mean():.0%}.\n\n{md_table(seg)}\n\n"
            f"Когда случилась первая покупка, % внутри сценария:\n\n{md_table(tab.reset_index())}\n\n"
            f"Конверсия триала в оплату: {trial_conv:.1%}; из них {autopay:.0%} — списание через 72–84 ч (автопродление). "
            f"Платили 2+ раза: через триал {rep['через триал']:.0%}, без триала {rep['без триала']:.0%}. "
            f"Гостевых аккаунтов среди платящих: {guests_paid}.\n")


if __name__ == "__main__":
    print(run(Path(sys.argv[1])))
