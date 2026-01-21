import argparse
import requests
from bs4 import BeautifulSoup
import csv
import time
from datetime import datetime

# Endpoint for BGG XML API v1 (Often more stable for bulk data)
DEFAULT_TOTAL_GAMES = 20
BASE_URL = "https://boardgamegeek.com/xmlapi/boardgame/{}?stats=1"
BROWSE_URL = "https://boardgamegeek.com/browse/boardgame/page/{}"

TOKEN_FILE = "bgg_token.txt"

def load_api_token(path=TOKEN_FILE):
    try:
        with open(path, encoding="utf-8") as token_file:
            return token_file.read().strip()
    except FileNotFoundError:
        print(f"   [!] Token file {path} not found. Requests may be rejected.")
    except Exception as exc:
        print(f"   [!] Unable to read token file: {exc}")
    return None

# Rotating a slightly different User-Agent to try and bypass 401
BASE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/xml"
}

API_TOKEN = load_api_token()
HEADERS = BASE_HEADERS.copy()
if API_TOKEN:
    HEADERS["Authorization"] = f"Bearer {API_TOKEN}"
else:
    print("   [!] No API token available; calls may fail.")

def get_top_game_ids(limit=DEFAULT_TOTAL_GAMES):
    game_ids = []
    page = 1
    while len(game_ids) < limit:
        print(f"Fetching IDs from page {page}...")
        res = requests.get(BROWSE_URL.format(page), headers=HEADERS)
        if res.status_code != 200:
            print(f"   [!] Error {res.status_code} fetching IDs from browse page.")
            break
        soup = BeautifulSoup(res.text, 'html.parser')
        links = soup.find_all('a', class_='primary')
        for link in links:
            href = link.get('href')
            if href and '/boardgame/' in href:
                gid = href.split('/')[2]
                if gid not in game_ids: game_ids.append(gid)
            if len(game_ids) >= limit: break
        page += 1
        time.sleep(2)
    return game_ids

def fetch_game_data(batch_ids):
    id_string = ",".join(batch_ids)
    target_url = BASE_URL.format(id_string)
    
    # --- PRINT THE ENDPOINT ---
    print(f"   >> API GET: {target_url}")
    
    try:
        response = requests.get(target_url, headers=HEADERS, timeout=20)
        if response.status_code == 200:
            return BeautifulSoup(response.text, 'xml')
        else:
            print(f"   [!] Failed with status: {response.status_code}")
            return None
    except Exception as e:
        print(f"   [!] Connection error: {e}")
        return None


def extract_link_values(game, link_type):
    values = []
    for link in game.find_all('link'):
        if (link.get('type') or '').lower() != link_type.lower():
            continue
        raw = (link.get('value') or link.text or '').strip()
        if raw:
            values.append(raw)
    return "; ".join(values) if values else "N/A"


def join_tag_values(game, tag_name):
    values = []
    for tag in game.find_all(tag_name):
        text = (tag.get('value') or tag.text or '').strip()
        if text:
            values.append(text)
    return "; ".join(values) if values else "N/A"


def find_tag_value(game, tag_name):
    tag = game.find(tag_name)
    if not tag:
        return "N/A"
    return (tag.get('value') or tag.text or "").strip() or "N/A"


def parse_poll_numplayers_outcomes(game):
    poll = game.find('poll', {'name': 'suggested_numplayers'})
    if not poll:
        return []

    outcomes = []

    for results in poll.find_all('results'):
        num_players = results.get('numplayers')
        if not num_players or not num_players.isdigit():
            continue
        count = int(num_players)
        top_votes = -1
        top_values = []

        for result in results.find_all('result'):
            votes = int(result.get('numvotes', '0')) if result.get('numvotes') else 0
            value = (result.get('value') or '').strip()
            if votes > top_votes:
                top_votes = votes
                top_values = [value]
            elif votes == top_votes:
                top_values.append(value)

        if top_votes <= 0:
            continue

        lowered = [value.lower() for value in top_values if value]
        chosen = None
        for preferred in ('best', 'recommended'):  # tie-break preference
            if preferred in lowered:
                chosen = preferred
                break

        if not chosen and lowered:
            chosen = lowered[0]

        if chosen:
            outcomes.append((count, chosen))

    return outcomes


def range_for_poll_outcomes(game, target_values):
    outcomes = parse_poll_numplayers_outcomes(game)
    if not outcomes:
        return None, None

    valid = [count for count, winner in outcomes if winner in {value.lower() for value in target_values}]
    if not valid:
        return None, None
    return min(valid), max(valid)


def parse_poll_top_value(game, poll_name):
    poll = game.find('poll', {'name': poll_name})
    if not poll:
        return None

    top_value = None
    top_votes = -1

    for results in poll.find_all('results'):
        for result in results.find_all('result'):
            votes = int(result.get('numvotes', '0')) if result.get('numvotes') else 0
            value = (result.get('value') or '').strip()
            if votes > top_votes and value:
                top_votes = votes
                top_value = value

    return top_value


def format_numeric(value):
    return str(value) if value is not None else "N/A"

def parse_arguments():
    parser = argparse.ArgumentParser(description="Download top board games from BoardGameGeek.")
    parser.add_argument("--total-games", type=int, default=DEFAULT_TOTAL_GAMES,
                        help="Number of games to fetch for the dump")
    return parser.parse_args()


def main():
    args = parse_arguments()
    total_games = args.total_games
    ids = get_top_game_ids(total_games)
    data_rows = []
    total_batches = max(1, (len(ids) + 9) // 10)

    for i in range(0, len(ids), 10):
        batch = ids[i:i+10]
        print(f"\nProcessing batch {i//10 + 1}/{total_batches}")
        soup = fetch_game_data(batch)
        
        if not soup:
            print("   Batch failed. Skipping...")
            time.sleep(10)
            continue

        for game in soup.find_all('boardgame'):
            try:
                stats = game.find('statistics').find('ratings')
                
                rank_val = "N/A"
                for r in stats.find_all('rank'):
                    if r.get('name') == 'boardgame':
                        rank_val = r.get('value')
                        break

                designers = join_tag_values(game, 'boardgamedesigner')
                artists = join_tag_values(game, 'boardgameartist')
                categories = join_tag_values(game, 'boardgamecategory')
                if categories == "N/A":
                    categories = extract_link_values(game, 'boardgamecategory')

                type_value = "N/A"
                type_entries = []
                for r in stats.find_all('rank'):
                    r_type = (r.get('type') or '').strip()
                    if not r_type or r_type.lower() == 'subtype':
                        continue
                    friendly = (r.get('friendlyname') or r.get('name') or '').strip()
                    if friendly.lower().endswith('rank'):
                        friendly = friendly[:-4].strip()
                    label = friendly or r_type
                    value = r.get('value') or "N/A"
                    type_entries.append(f"{label}({value})")

                community_player_min, community_player_max = range_for_poll_outcomes(game, {'best', 'recommended'})
                community_best_player_min, community_best_player_max = range_for_poll_outcomes(game, {'best'})

                age_value = join_tag_values(game, 'age')
                community_age_value = parse_poll_top_value(game, 'suggested_playerage') or "N/A"
                playing_time_min = find_tag_value(game, 'minplaytime')
                playing_time_max = find_tag_value(game, 'maxplaytime')

                row = {
                    'Rank': rank_val,
                    'Title': game.find('name', {'primary': 'true'}).text if game.find('name', {'primary': 'true'}) else "Unknown",
                    'Year': game.find('yearpublished').text if game.find('yearpublished') else "N/A",
                    'Rating': stats.find('average').text if stats.find('average') else "N/A",
                    'Weight': stats.find('averageweight').text if stats.find('averageweight') else "N/A",
                    'Type': ", ".join(type_entries) if type_entries else "N/A",
                    'Min Players': game.find('minplayers').text if game.find('minplayers') else "N/A",
                    'Max Players': game.find('maxplayers').text if game.find('maxplayers') else "N/A",
                    'Community Player Count Min': format_numeric(community_player_min),
                    'Community Player Count Max': format_numeric(community_player_max),
                    'Community Best Player Count Min': format_numeric(community_best_player_min),
                    'Community Best Player Count Max': format_numeric(community_best_player_max),
                    'Playing Time Min': playing_time_min,
                    'Playing Time Max': playing_time_max,
                    'Age': age_value,
                    'Community Age': community_age_value,
                    'Designers': designers,
                    'Artists': artists,
                    'Categories': categories
                }
                data_rows.append(row)
            except Exception as e:
                print(f"   Error parsing a game: {e}")

        # Very conservative delay to prevent the next 401
        time.sleep(6)

    if data_rows:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        csv_filename = f"bgg_dump_{total_games}_{timestamp}.csv"
        with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=data_rows[0].keys())
            writer.writeheader()
            writer.writerows(data_rows)
        print(f"\nSaved {len(data_rows)} games to {csv_filename}")
    else:
        print("\nNo data was collected; no CSV was written.")


if __name__ == "__main__":
    main()