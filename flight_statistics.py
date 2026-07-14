"""Persistent nearby-flight observations and compact statistics displays."""

from datetime import datetime, timedelta
import logging
import os
from pathlib import Path
import sqlite3
from threading import Lock

from PIL import Image, ImageDraw, ImageFont

from display_adapter import return_display_lock
from font_utils import get_font_paths

logger = logging.getLogger(__name__)
display_lock = return_display_lock()


def _text(value):
    return str(value).strip() if value is not None else ""


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _year(value):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return None
    return value if 1900 <= value <= datetime.now().year + 1 else None


class FlightStatisticsStore:
    """SQLite-backed flight encounters, deduplicated across nearby polls."""

    FIELDS = (
        "hex",
        "callsign",
        "flight_number",
        "registration",
        "operator",
        "operator_name",
        "origin_code",
        "destination_code",
        "aircraft_type",
        "description",
        "manufacturer",
        "type",
    )

    def __init__(
        self,
        path="cache/flight_statistics.sqlite3",
        retention_days=400,
        encounter_gap_minutes=30,
        update_interval_seconds=120,
    ):
        self.path = str(path)
        self.retention_days = max(31, int(retention_days))
        self.encounter_gap = timedelta(minutes=max(1, int(encounter_gap_minutes)))
        self.update_interval = timedelta(seconds=max(10, int(update_interval_seconds)))
        self._lock = Lock()
        self._last_pruned = None
        if self.path != ":memory:":
            Path(self.path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        self._memory_connection = None
        if self.path == ":memory:":
            self._memory_connection = sqlite3.connect(
                ":memory:", check_same_thread=False
            )
            self._memory_connection.row_factory = sqlite3.Row
        self._initialize()

    def _connect(self):
        if self._memory_connection is not None:
            return self._memory_connection
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _close(self, connection):
        if connection is not self._memory_connection:
            connection.close()

    def _initialize(self):
        with self._lock:
            connection = self._connect()
            try:
                connection.execute("""
                    CREATE TABLE IF NOT EXISTS flight_encounters (
                        id INTEGER PRIMARY KEY,
                        identity TEXT NOT NULL,
                        first_seen TEXT NOT NULL,
                        last_seen TEXT NOT NULL,
                        hex TEXT,
                        callsign TEXT,
                        flight_number TEXT,
                        registration TEXT,
                        operator TEXT,
                        operator_name TEXT,
                        origin_code TEXT,
                        destination_code TEXT,
                        aircraft_type TEXT,
                        description TEXT,
                        manufacturer TEXT,
                        type TEXT,
                        aircraft_year INTEGER,
                        min_distance REAL,
                        max_altitude REAL,
                        max_ground_speed REAL
                    )
                    """)
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_flight_seen "
                    "ON flight_encounters(first_seen)"
                )
                connection.execute(
                    "CREATE INDEX IF NOT EXISTS idx_flight_identity "
                    "ON flight_encounters(identity, last_seen)"
                )
                connection.commit()
            finally:
                self._close(connection)

    @staticmethod
    def identity(flight):
        for field in ("hex", "registration", "callsign", "flight_number"):
            value = _text(flight.get(field))
            if value:
                return f"{field}:{value.upper()}"
        return None

    def record(self, flight, observed_at=None):
        identity = self.identity(flight)
        if not identity:
            return False
        observed_at = observed_at or datetime.now()
        values = {field: _text(flight.get(field)) or None for field in self.FIELDS}
        aircraft_year = flight.get("aircraft_year")
        if aircraft_year is None:
            aircraft_year = flight.get("year")
        values["aircraft_year"] = _year(aircraft_year)
        distance = flight.get("last_distance")
        if distance is None:
            distance = flight.get("distance")
        values["min_distance"] = _number(distance)
        values["max_altitude"] = _number(flight.get("altitude"))
        ground_speed = flight.get("ground_speed")
        if ground_speed is None:
            ground_speed = flight.get("gs")
        values["max_ground_speed"] = _number(ground_speed)

        with self._lock:
            connection = self._connect()
            try:
                latest = connection.execute(
                    "SELECT * FROM flight_encounters WHERE identity = ? "
                    "ORDER BY last_seen DESC LIMIT 1",
                    (identity,),
                ).fetchone()
                if latest:
                    last_seen = datetime.fromisoformat(latest["last_seen"])
                    since_last_seen = observed_at - last_seen
                    if timedelta(0) <= since_last_seen <= self.encounter_gap:
                        if since_last_seen < self.update_interval:
                            return False
                        merged = {}
                        for field in self.FIELDS:
                            merged[field] = values[field] or latest[field]
                        merged["aircraft_year"] = (
                            values["aircraft_year"] or latest["aircraft_year"]
                        )
                        distances = [
                            value
                            for value in (
                                latest["min_distance"],
                                values["min_distance"],
                            )
                            if value is not None
                        ]
                        merged["min_distance"] = min(distances) if distances else None
                        for field in ("max_altitude", "max_ground_speed"):
                            numbers = [
                                value
                                for value in (latest[field], values[field])
                                if value is not None
                            ]
                            merged[field] = max(numbers) if numbers else None
                        assignments = ", ".join(
                            f"{field} = ?"
                            for field in (
                                *self.FIELDS,
                                "aircraft_year",
                                "min_distance",
                                "max_altitude",
                                "max_ground_speed",
                            )
                        )
                        connection.execute(
                            f"UPDATE flight_encounters SET last_seen = ?, {assignments} WHERE id = ?",
                            (
                                observed_at.isoformat(),
                                *(
                                    merged[field]
                                    for field in (
                                        *self.FIELDS,
                                        "aircraft_year",
                                        "min_distance",
                                        "max_altitude",
                                        "max_ground_speed",
                                    )
                                ),
                                latest["id"],
                            ),
                        )
                        connection.commit()
                        return True

                fields = (
                    "identity",
                    "first_seen",
                    "last_seen",
                    *self.FIELDS,
                    "aircraft_year",
                    "min_distance",
                    "max_altitude",
                    "max_ground_speed",
                )
                placeholders = ", ".join("?" for _ in fields)
                connection.execute(
                    f"INSERT INTO flight_encounters ({', '.join(fields)}) VALUES ({placeholders})",
                    (
                        identity,
                        observed_at.isoformat(),
                        observed_at.isoformat(),
                        *(
                            values[field]
                            for field in (
                                *self.FIELDS,
                                "aircraft_year",
                                "min_distance",
                                "max_altitude",
                                "max_ground_speed",
                            )
                        ),
                    ),
                )
                connection.commit()
                self._prune_locked(connection, observed_at)
                return True
            finally:
                self._close(connection)

    def _prune_locked(self, connection, now):
        if self._last_pruned and now - self._last_pruned < timedelta(days=1):
            return
        cutoff = now - timedelta(days=self.retention_days)
        connection.execute(
            "DELETE FROM flight_encounters WHERE last_seen < ?", (cutoff.isoformat(),)
        )
        connection.commit()
        self._last_pruned = now

    @staticmethod
    def _period_start(period, now):
        if period == "day":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        if period == "week":
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            return day_start - timedelta(days=now.weekday())
        if period == "month":
            return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        raise ValueError(f"unknown statistics period: {period}")

    @staticmethod
    def _top(connection, expression, where, params, limit):
        return [
            (row["label"], row["total"])
            for row in connection.execute(
                f"SELECT {expression} AS label, COUNT(*) AS total "
                f"FROM flight_encounters WHERE {where} "
                "GROUP BY label ORDER BY total DESC, label ASC LIMIT ?",
                (*params, limit),
            ).fetchall()
        ]

    @staticmethod
    def _repeat(connection, where, params):
        row = connection.execute(
            "SELECT COALESCE(MAX(registration), MAX(callsign), MAX(hex), identity) "
            "AS label, COUNT(*) AS total FROM flight_encounters "
            f"WHERE {where} GROUP BY identity "
            "ORDER BY total DESC, label ASC LIMIT 1",
            params,
        ).fetchone()
        return (row["label"], row["total"]) if row else None

    def summary(self, period="week", now=None):
        now = now or datetime.now()
        start = self._period_start(period, now)
        bounds = (start.isoformat(), now.isoformat())
        period_where = "first_seen >= ? AND first_seen <= ?"
        with self._lock:
            connection = self._connect()
            try:
                totals = connection.execute(
                    f"SELECT COUNT(*) AS encounters, "
                    "COUNT(DISTINCT identity) AS aircraft "
                    f"FROM flight_encounters WHERE {period_where}",
                    bounds,
                ).fetchone()
                routes = self._top(
                    connection,
                    "UPPER(origin_code) || '>' || UPPER(destination_code)",
                    f"{period_where} AND origin_code IS NOT NULL "
                    "AND destination_code IS NOT NULL",
                    bounds,
                    3,
                )
                operators = self._top(
                    connection,
                    "COALESCE(operator_name, operator)",
                    f"{period_where} AND COALESCE(operator_name, operator) IS NOT NULL",
                    bounds,
                    3,
                )
                types = self._top(
                    connection,
                    "COALESCE(type, aircraft_type, description)",
                    f"{period_where} AND "
                    "COALESCE(type, aircraft_type, description) IS NOT NULL",
                    bounds,
                    2,
                )
                repeat = self._repeat(connection, period_where, bounds)
                busiest = self._top(
                    connection,
                    "CAST(SUBSTR(first_seen, 12, 2) AS INTEGER)",
                    period_where,
                    bounds,
                    1,
                )
                return {
                    "period": period,
                    "label": {
                        "day": "Today",
                        "week": "This week",
                        "month": "This month",
                    }[period],
                    "encounters": totals["encounters"],
                    "unique_aircraft": totals["aircraft"],
                    "top_routes": routes,
                    "top_operators": operators,
                    "top_types": types,
                    "repeat": repeat,
                    "busiest_hour": busiest[0] if busiest else None,
                }
            finally:
                self._close(connection)

    def records(self, now=None):
        now = now or datetime.now()
        end = now.isoformat()
        aircraft = "COALESCE(registration, callsign, hex, identity)"

        def record_row(connection, field, direction):
            return connection.execute(
                f"SELECT {aircraft} AS label, {field} AS value "
                "FROM flight_encounters "
                f"WHERE first_seen <= ? AND {field} IS NOT NULL "
                f"ORDER BY {field} {direction}, first_seen ASC LIMIT 1",
                (end,),
            ).fetchone()

        with self._lock:
            connection = self._connect()
            try:
                total = connection.execute(
                    "SELECT COUNT(*) FROM flight_encounters WHERE first_seen <= ?",
                    (end,),
                ).fetchone()[0]
                repeat = self._repeat(connection, "first_seen <= ?", (end,))
                oldest = record_row(connection, "aircraft_year", "ASC")
                youngest = record_row(connection, "aircraft_year", "DESC")
                closest = record_row(connection, "min_distance", "ASC")
                fastest = record_row(connection, "max_ground_speed", "DESC")
                return {
                    "encounters": total,
                    "oldest": (
                        {"label": oldest["label"], "year": oldest["value"]}
                        if oldest
                        else None
                    ),
                    "youngest": (
                        {"label": youngest["label"], "year": youngest["value"]}
                        if youngest
                        else None
                    ),
                    "repeat": repeat,
                    "closest": (
                        (closest["label"], closest["value"]) if closest else None
                    ),
                    "fastest": (
                        (fastest["label"], fastest["value"]) if fastest else None
                    ),
                }
            finally:
                self._close(connection)


def _fonts():
    paths = get_font_paths()
    try:
        return (
            ImageFont.truetype(paths["dejavu_bold"], 14),
            ImageFont.truetype(paths["dejavu_bold"], 11),
            ImageFont.truetype(paths["dejavu"], 10),
        )
    except (IOError, KeyError):
        fallback = ImageFont.load_default()
        return fallback, fallback, fallback


def _canvas(epd):
    mode = "1" if epd.is_bw_display else "RGB"
    background = 1 if epd.is_bw_display else "white"
    image = Image.new(mode, (epd.height, epd.width), background)
    return image, ImageDraw.Draw(image), _fonts()


def _finish(epd, image, set_base_image):
    image = image.rotate(int(os.getenv("screen_rotation", "90")), expand=True)
    with display_lock:
        buffer = epd.getbuffer(image)
        if hasattr(epd, "displayPartial"):
            if set_base_image:
                epd.init()
                epd.displayPartBaseImage(buffer)
            else:
                epd.displayPartial(buffer)
        else:
            epd.display(buffer)
    return True


def _fit_text(draw, value, font, max_width):
    value = str(value)
    if draw.textbbox((0, 0), value, font=font)[2] <= max_width:
        return value
    while value and draw.textbbox((0, 0), f"{value}…", font=font)[2] > max_width:
        value = value[:-1]
    return f"{value}…" if value else ""


def update_display_with_flight_statistics(epd, summary, set_base_image=False):
    image, draw, (header, bold, detail) = _canvas(epd)
    width = image.width
    draw.text((7, 4), f"Flights · {summary['label']}", fill="black", font=header)
    total = f"{summary['encounters']} flybys · {summary['unique_aircraft']} planes"
    draw.text((7, 21), total, fill="black", font=detail)
    draw.line([(7, 34), (width - 7, 34)], fill="black", width=1)

    rows = []
    rows.extend(
        ("Route", name.replace(">", "→"), count)
        for name, count in summary["top_routes"][:2]
    )
    rows.extend(
        ("Operator", name, count) for name, count in summary["top_operators"][:2]
    )
    if not rows:
        rows.extend(("Type", name, count) for name, count in summary["top_types"][:2])
    if summary["repeat"] and len(rows) < 3:
        rows.append(("Repeat", summary["repeat"][0], summary["repeat"][1]))
    if summary["busiest_hour"] and len(rows) < 3:
        hour, count = summary["busiest_hour"]
        rows.append(("Busy", f"{hour:02d}:00–{(hour + 1) % 24:02d}:00", count))

    if not rows:
        draw.text((7, 54), "No recorded flights yet", fill="black", font=bold)
    for index, (kind, label, count) in enumerate(rows[:4]):
        top = 39 + index * 20
        draw.text((7, top), kind, fill="black", font=detail)
        count_text = f"×{count}"
        count_width = draw.textbbox((0, 0), count_text, font=detail)[2]
        label = _fit_text(draw, label, bold, width - 62 - count_width - 12)
        draw.text((62, top), label, fill="black", font=bold)
        draw.text(
            (width - 7 - count_width, top + 1), count_text, fill="black", font=detail
        )
    return _finish(epd, image, set_base_image)


def update_display_with_flight_records(epd, records, set_base_image=False):
    image, draw, (header, bold, detail) = _canvas(epd)
    draw.text((7, 4), "Flight records", fill="black", font=header)
    draw.text(
        (7, 21), f"{records['encounters']} recorded flybys", fill="black", font=detail
    )
    draw.line([(7, 34), (image.width - 7, 34)], fill="black", width=1)
    rows = []
    for title in ("oldest", "youngest"):
        item = records[title]
        if item:
            rows.append((title.title(), item["label"], str(item["year"])))
    if records["repeat"]:
        rows.append(("Most seen", records["repeat"][0], f"×{records['repeat'][1]}"))
    if records["closest"]:
        rows.append(
            ("Closest", records["closest"][0], f"{records['closest'][1]:.1f} km")
        )
    if not rows:
        draw.text((7, 54), "More sightings needed", fill="black", font=bold)
    for index, (kind, label, value) in enumerate(rows[:4]):
        top = 39 + index * 20
        draw.text((7, top), kind, fill="black", font=detail)
        value_width = draw.textbbox((0, 0), value, font=detail)[2]
        label = _fit_text(draw, label, bold, image.width - 67 - value_width - 12)
        draw.text((67, top), label, fill="black", font=bold)
        draw.text(
            (image.width - 7 - value_width, top + 1), value, fill="black", font=detail
        )
    return _finish(epd, image, set_base_image)
