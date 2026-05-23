"""Echo Mode recommender-data importers (README §5.22).

Parse the documented local export formats into ``recommender_observations``
row dicts (the shape :meth:`EchoStore.add_observations` consumes). Each importer
is a function or class that returns a list of dicts with keys::

    timestamp        int   epoch seconds
    platform         str   youtube|google|amazon|spotify|...
    observation_type str   recommendation|search_suggest|ad|feed_item|...
    content          str   text hashed into content_hash by the store
    raw_content      str   optional plaintext (own retention window)
    source           str   takeout|browser_ext|manual_import

Hard constraint (§5.22): "No cloud sync of recommender data, ever." These
importers operate on *local files only*; there is no network code in this
module. They are tolerant of format variation (Google Takeout in particular
varies across export vintages and locales).
"""

from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


# --- timestamp helpers -------------------------------------------------------
def _epoch_seconds(value: Any) -> int | None:
    """Best-effort parse of the many timestamp shapes exports use."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        v = float(value)
        # Heuristic: ms vs s vs us.
        if v > 1e14:
            v /= 1_000_000.0
        elif v > 1e11:
            v /= 1000.0
        return int(v)
    s = str(value).strip()
    if not s:
        return None
    if s.isdigit():
        return _epoch_seconds(int(s))
    # ISO 8601, tolerate trailing Z and fractional seconds.
    for candidate in (s, s.replace("Z", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    # Common Takeout/Amazon date formats.
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%b %d, %Y", "%m/%d/%Y", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except ValueError:
            continue
    return None


def _read_text(path: str | Path) -> str:
    return Path(path).expanduser().read_text(encoding="utf-8")


def _load_json(path_or_text: str | Path) -> Any:
    p = Path(str(path_or_text)).expanduser()
    text = p.read_text(encoding="utf-8") if p.exists() else str(path_or_text)
    return json.loads(text)


# --- YouTube / Google Takeout (watch + search history JSON) ------------------
def import_youtube_takeout(path: str | Path, *, source: str = "takeout") -> list[dict[str, Any]]:
    """Parse a YouTube Takeout history JSON (watch and/or search history).

    Takeout exports a JSON array of activity records; ``header`` distinguishes
    "YouTube" watch entries from "YouTube Search" entries. We tolerate missing
    keys and varied time fields (``time`` / ``timestamp``).
    """
    data = _load_json(path)
    rows: list[dict[str, Any]] = []
    if isinstance(data, dict):  # some exports wrap the list
        data = data.get("activities") or data.get("items") or []
    for rec in data or []:
        if not isinstance(rec, dict):
            continue
        ts = _epoch_seconds(rec.get("time") or rec.get("timestamp") or rec.get("date"))
        if ts is None:
            continue
        title = (rec.get("title") or "").strip()
        # Takeout prefixes titles, e.g. "Watched X" / "Searched for X".
        header = (rec.get("header") or "").lower()
        is_search = "search" in header or title.lower().startswith("searched for")
        content = title
        for prefix in ("Watched ", "Searched for "):
            if content.startswith(prefix):
                content = content[len(prefix):]
        obs_type = "search_suggest" if is_search else "recommendation"
        rows.append(
            {
                "timestamp": ts,
                "platform": "youtube",
                "observation_type": obs_type,
                "content": content or title,
                "raw_content": title,
                "source": source,
            }
        )
    return rows


def import_google_takeout(path: str | Path, *, source: str = "takeout") -> list[dict[str, Any]]:
    """Parse a Google "My Activity" search-history JSON Takeout export.

    Same activity-record shape as YouTube but ``platform='google'`` and every
    record is a search suggestion / query.
    """
    data = _load_json(path)
    rows: list[dict[str, Any]] = []
    if isinstance(data, dict):
        data = data.get("activities") or data.get("items") or []
    for rec in data or []:
        if not isinstance(rec, dict):
            continue
        ts = _epoch_seconds(rec.get("time") or rec.get("timestamp"))
        if ts is None:
            continue
        title = (rec.get("title") or "").strip()
        content = title
        for prefix in ("Searched for ", "Visited "):
            if content.startswith(prefix):
                content = content[len(prefix):]
        rows.append(
            {
                "timestamp": ts,
                "platform": "google",
                "observation_type": "search_suggest",
                "content": content or title,
                "raw_content": title,
                "source": source,
            }
        )
    return rows


# --- Spotify streaming history JSON ------------------------------------------
def import_spotify_export(path: str | Path, *, source: str = "takeout") -> list[dict[str, Any]]:
    """Parse a Spotify ``StreamingHistory*.json`` export.

    Records use ``endTime`` (``YYYY-MM-DD HH:MM``) plus ``artistName`` and
    ``trackName`` (extended exports use ``ts`` + ``master_metadata_*``). The
    observation content is "artist - track".
    """
    data = _load_json(path)
    rows: list[dict[str, Any]] = []
    if isinstance(data, dict):
        data = data.get("items") or []
    for rec in data or []:
        if not isinstance(rec, dict):
            continue
        ts = _epoch_seconds(
            rec.get("ts")
            or rec.get("endTime")
            or rec.get("end_time")
        )
        # endTime "YYYY-MM-DD HH:MM" needs a tweak for fromisoformat.
        if ts is None and rec.get("endTime"):
            ts = _epoch_seconds(str(rec["endTime"]).replace(" ", "T"))
        if ts is None:
            continue
        artist = rec.get("artistName") or rec.get("master_metadata_album_artist_name") or ""
        track = rec.get("trackName") or rec.get("master_metadata_track_name") or ""
        content = " - ".join(p for p in (artist, track) if p).strip(" -")
        if not content:
            continue
        rows.append(
            {
                "timestamp": ts,
                "platform": "spotify",
                "observation_type": "recommendation",
                "content": content,
                "raw_content": content,
                "source": source,
            }
        )
    return rows


# --- Amazon order history CSV ------------------------------------------------
def import_amazon_orders(path: str | Path, *, source: str = "takeout") -> list[dict[str, Any]]:
    """Parse an Amazon order-history CSV export.

    Amazon's column names vary by report type/locale; we look up a date column
    and a title column case-insensitively from a set of known aliases.
    """
    text = _read_text(path)
    reader = csv.DictReader(io.StringIO(text))
    date_keys = ("order date", "order date", "ship date", "shipment date", "date")
    title_keys = ("title", "product name", "item name", "name")
    rows: list[dict[str, Any]] = []
    for rec in reader:
        norm = { (k or "").strip().lower(): v for k, v in rec.items() }
        ts = None
        for k in date_keys:
            if k in norm and norm[k]:
                ts = _epoch_seconds(norm[k])
                if ts is not None:
                    break
        if ts is None:
            continue
        title = ""
        for k in title_keys:
            if k in norm and norm[k]:
                title = norm[k].strip()
                break
        if not title:
            continue
        rows.append(
            {
                "timestamp": ts,
                "platform": "amazon",
                "observation_type": "recommendation",
                "content": title,
                "raw_content": title,
                "source": source,
            }
        )
    return rows


# --- Generic JSON / CSV importer ---------------------------------------------
def import_generic(
    path: str | Path,
    *,
    platform: str,
    observation_type: str = "recommendation",
    source: str = "manual_import",
    time_field: str = "timestamp",
    content_field: str = "content",
) -> list[dict[str, Any]]:
    """Importer for the long tail / hand-rolled exports.

    Accepts ``.json`` (array of objects) or ``.csv``. Field names are
    configurable so users can map their own exports without code changes.
    """
    p = Path(str(path)).expanduser()
    if p.suffix.lower() == ".json":
        data = _load_json(p)
        records: Iterable[dict[str, Any]] = data if isinstance(data, list) else []
    else:
        records = list(csv.DictReader(io.StringIO(_read_text(p))))
    rows: list[dict[str, Any]] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        ts = _epoch_seconds(rec.get(time_field))
        content = rec.get(content_field)
        if ts is None or not content:
            continue
        rows.append(
            {
                "timestamp": ts,
                "platform": platform,
                "observation_type": rec.get("observation_type", observation_type),
                "content": str(content),
                "raw_content": str(content),
                "source": source,
            }
        )
    return rows


# --- Browser-extension capture interface -------------------------------------
class BrowserCapture(Protocol):
    """Source of DOM-captured recommendation events.

    Real implementations read from a locally-running open-source extension's
    capture buffer (§5.22: browser extensions are Kerckhoffs-public, no network
    sync). This protocol keeps that surface pluggable and testable.
    """

    def events(self) -> Iterable[dict[str, Any]]: ...


class BrowserCaptureImporter:
    """Adapt DOM-captured recommendation events into observation rows.

    The capture source yields raw event dicts (``{platform, type, text, time}``
    or similar); this importer normalizes them. Used for surfaces takeout does
    not expose (Amazon recs, YouTube live recs, X "For You", etc.).
    """

    def __init__(self, capture: BrowserCapture, *, source: str = "browser_ext"):
        self.capture = capture
        self.source = source

    def import_events(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for ev in self.capture.events():
            ts = _epoch_seconds(ev.get("time") or ev.get("timestamp"))
            content = ev.get("text") or ev.get("content") or ev.get("title")
            platform = ev.get("platform")
            if ts is None or not content or not platform:
                continue
            rows.append(
                {
                    "timestamp": ts,
                    "platform": str(platform),
                    "observation_type": ev.get("type", "recommendation"),
                    "content": str(content),
                    "raw_content": str(content),
                    "source": self.source,
                }
            )
        return rows


class ListBrowserCapture:
    """Trivial in-memory :class:`BrowserCapture` (tests / manual feeds)."""

    def __init__(self, events: list[dict[str, Any]]):
        self._events = events

    def events(self) -> Iterable[dict[str, Any]]:
        return list(self._events)
