========================================
Latency + Download Speed Logger (speed_log.py)
========================================
Coded by: Muse Spark (Meta AI assistant)
Curated by: smallrug2
License: MIT (see LICENSE file)

WHAT IT DOES:
Pings --host (4 packets, OS-specific flags) and times an HTTP download
of --url each round, appending CSV rows (timestamp, ping_ms,
down_mbps). Prints an ASCII sparkline of the last 20 ping readings.
Default is infinite rounds every 300s; Ctrl+C exits cleanly.

REQUIREMENTS:
Python 3.8+ only - no extra packages needed (stdlib only).

HOW TO RUN:
python speed_log.py --help
python speed_log.py --rounds 3 --interval 5
python speed_log.py --host 1.1.1.1 --rounds 10 --interval 60 --out speeds.csv

PLATFORM:
Windows + Linux + Mac: yes.

CREDITS:
- Coded by Muse Spark (Meta AI assistant) for smallrug2's open-source collection.
- If this script helped you, a star on the repo is appreciated.
