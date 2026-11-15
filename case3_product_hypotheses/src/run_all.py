"""Запуск всего анализа: python run_all.py <путь к папке db>  ->  results/summary.md + CSV."""
import sys
import time
from pathlib import Path
from common import RESULTS
from logs_parser import parse_logs
import h1_trial_abuse, h2_free_limits, h3_purchase_path, h4_log_errors


def main(db: Path) -> None:
    t0 = time.time()
    parts = [f"# Результаты: кейс 3 «Генерация продуктовых гипотез»\n\nДанные: `{db.name}`. Сгенерировано скриптом run_all.py.\n"]
    print("Разбор клиентских логов…", flush=True)
    sessions, traffic = parse_logs(db)
    for name, fn in [("H1", lambda: h1_trial_abuse.run(db)),
                     ("H2", lambda: h2_free_limits.run(db, traffic)),
                     ("H3", lambda: h3_purchase_path.run(db)),
                     ("H4", lambda: h4_log_errors.run(db, sessions))]:
        print(f"{name}…", flush=True)
        parts.append(fn())
    (RESULTS / "summary.md").write_text("\n".join(parts), encoding="utf-8")
    print(f"Готово за {time.time() - t0:.0f} с: {RESULTS / 'summary.md'}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("Использование: python run_all.py <путь к папке db>")
    main(Path(sys.argv[1]))
