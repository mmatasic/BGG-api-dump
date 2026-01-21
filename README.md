# BoardGameGeek API Dump

A small Python helper that scrapes BoardGameGeek's browse pages for the top-ranked titles, then requests their statistics from the official XML API so you can export that snapshot to CSV.

## Setup

1. Request api token on BGG site and place it in `bgg_token.txt`.
2. Ensure the token lives next to `BGGApiDump.py` so the script can automatically read it.
3. (Optional) Adjust the `DEFAULT_TOTAL_GAMES` constant if you always want a different default.

## Usage

`python BGGApiDump.py --total-games N`

- `--total-games` controls how many game IDs the scraper fetches before requesting stats.
- If you omit the flag, the script uses the default (currently 20).
- HEADERS includes a `User-Agent`, `Accept`, and the bearer token read from `bgg_token.txt`.
- Requests pause 2 seconds between browse pages and 10 seconds between XML batches to stay polite and avoid 401 errors.

### Examples

- Fetch the top 200 games:
	```
	python BGGApiDump.py --total-games 200
	```
- Run the default size (20 games):
	```
	python BGGApiDump.py
	```

## Output

- The script writes `bgg_dump_N_<TIMESTAMP>.csv`, where `N` is the `--total-games` value you passed (or the default) and `<TIMESTAMP>` is the export time in `YYYYMMDDHHMMSS` format.
- Each row mirrors the XML metadata described on [BGG_XML_API](https://boardgamegeek.com/wiki/page/BGG_XML_API#), including:
	- Rank, title, year, average rating, weight, and the raw min/max players
	- Age requirement plus the most-voted community age suggestion
	- `Designers`, `Artists`, and `Categories`
	- Community player count ranges (overall recommended and best-only)
	- Playing time min/max and a comma-separated `Type` list where each entry shows its rank in parentheses (e.g., `Strategy Game(291), Family(340)`)
