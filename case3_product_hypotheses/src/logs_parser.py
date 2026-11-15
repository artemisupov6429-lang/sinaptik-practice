"""Разбор клиентских логов инцидентов: logs/<user_id>/<архив>.zip -> сессии приложения."""
import re
import zipfile
from pathlib import Path
import pandas as pd

TRAFFIC = re.compile(r"(\d{4}-\d\d-\d\dT[\d:.]+)\s+\[D\]\s+\[TrafficLimitBloc\] "
                     r"Traffic info changed: (\w+) bytes limit, (\d+) bytes used")
HEADER = re.compile(r"Running on Os\.(\w+); OS version ([^;]+); App version ([\d.]+)")
TS = re.compile(r"(\d{4}-\d\d-\d\dT\d\d:\d\d)")


def iter_session_logs(db: Path, max_mb: float = 50):
    """Отдаёт (user_id, имя сессии, текст) для каждого *.log внутри архивов.
    Архивы крупнее max_mb пропускаются (это 6 выбросов по 130–640 МБ у тестовых аккаунтов)."""
    for z in sorted((db / "logs").glob("*/*.zip")):
        if z.stat().st_size > max_mb * 2**20:
            continue
        uid = int(z.parent.name)
        try:
            zf = zipfile.ZipFile(z)
        except zipfile.BadZipFile:
            continue
        for name in zf.namelist():
            if name.endswith(".log"):
                yield uid, f"{z.name}/{name.strip()}", zf.read(name).decode("utf-8", "replace")


def session_features(text: str) -> dict:
    """Признаки одной сессии приложения."""
    m = HEADER.search(text)
    ts = TS.search(text)
    codes = re.findall(r"Error getting server config: DioException\(type=DioExceptionType\.badResponse, status=(\d+)", text)
    return {
        "os": m.group(1) if m else None,
        "app_version": m.group(3) if m else None,
        "ts": ts.group(1) if ts else None,
        "vpn_start": text.count("Vpn start called"),
        "vpn_connected": text.count("Vpn status changed: VpnStatus.connected"),
        "http400_server_config": codes.count("400"),
        "dns_api_fail": len(re.findall(r"Failed host lookup: 'api\.pipster\.win'", text)),
        "whitelist_detected": text.count("verdict=WhitelistVerdict.detected"),
        "mobile_only": text.count("ConnectivityGateVerdict.mobileOnly"),
        "time_limit": text.count("reason=DisconnectReason.timeLimitReached"),
        "traffic_limit": text.count("reason=DisconnectReason.trafficLimitReached"),
        "splash_fail": text.count("[SplashBloc] App init step failed"),
        "ad_load_fail": text.count("Ad failed to load"),
    }


def parse_logs(db: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Возвращает (сессии с признаками, замеры трафика TrafficLimitBloc)."""
    sessions, traffic = [], []
    for uid, sess, text in iter_session_logs(db):
        sessions.append({"user_id": uid, "session": sess, **session_features(text)})
        for t, limit, used in TRAFFIC.findall(text):
            traffic.append((uid, t, limit, int(used)))
    s = pd.DataFrame(sessions)
    s["t"] = pd.to_datetime(s.ts, errors="coerce")
    tr = pd.DataFrame(traffic, columns=["user_id", "ts", "limit", "used"]).drop_duplicates()
    return s, tr
