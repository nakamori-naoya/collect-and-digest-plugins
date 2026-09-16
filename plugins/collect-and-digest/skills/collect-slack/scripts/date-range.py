#!/usr/bin/env python3
"""設定timezoneのローカル日付から、DSTを含む正確なepoch境界を返す。"""
import argparse
import json
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

p = argparse.ArgumentParser()
p.add_argument("--date", required=True)
p.add_argument("--timezone", required=True)
args = p.parse_args()
try:
    day = date.fromisoformat(args.date)
    zone = ZoneInfo(args.timezone)
except (ValueError, ZoneInfoNotFoundError) as exc:
    p.error(str(exc))
start = datetime.combine(day, time.min, zone)
end = datetime.combine(day + timedelta(days=1), time.min, zone)
print(json.dumps({"target_date": args.date, "target_start_ts": str(start.timestamp()),
                  "target_end_ts": str(end.timestamp())}))
