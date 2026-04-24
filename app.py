from flask import Flask, render_template_string, request, jsonify
import requests
from datetime import datetime
import zoneinfo

app = Flask(__name__)

API_KEY = "95241e6f109df18872f24710e846ef80"
SPORTS = ["americanfootball_nfl", "basketball_nba"]

BOOK_LINKS = {
    "DraftKings": "https://www.draftkings.com/sportsbook",
    "FanDuel": "https://www.fanduel.com/sportsbook",
    "BetMGM": "https://www.betmgm.com/sports",
    "BetRivers": "https://www.betrivers.com",
    "LowVig.ag": "https://www.lowvig.ag",
    "BetOnline.ag": "https://www.betonline.ag",
    "MyBookie.ag": "https://www.mybookie.ag",
    "Bovada": "https://www.bovada.lv",
    "BetUS": "https://www.betus.com.pa"
}

NBA_PROPS = "player_points,player_rebounds,player_assists,player_threes"
NFL_PROPS = "player_pass_yds,player_rush_yds,player_reception_yds,player_anytime_td"

def american_to_decimal(odds):
    if odds > 0:
        return (odds / 100) + 1
    else:
        return (100 / abs(odds)) + 1

def decimal_to_american(decimal):
    if decimal >= 2:
        return round((decimal - 1) * 100)
    else:
        return round(-100 / (decimal - 1))

def get_props(sport, event_id):
    props_market = NBA_PROPS if "basketball" in sport else NFL_PROPS
    url = f"https://api.the-odds-api.com/v4/sports/{sport}/events/{event_id}/odds"
    params = {
        "apiKey": API_KEY,
        "regions": "us",
        "markets": props_market,
        "oddsFormat": "american"
    }
    response = requests.get(url, params=params)
    if response.status_code != 200:
        return {}

    data = response.json()
    props = {}

    for bookmaker in data.get("bookmakers", []):
        book = bookmaker["title"]
        for market in bookmaker.get("markets", []):
            market_key = market["key"].replace("player_", "").replace("_", " ").title()
            if market_key not in props:
                props[market_key] = {}
            for outcome in market.get("outcomes", []):
                player = outcome.get("description", outcome["name"])
                line = outcome.get("point", "")
                bet_type = outcome["name"]
                key = f"{player} - {bet_type} {line}".strip()
                if key not in props[market_key]:
                    props[market_key][key] = {"odds": [], "books": {}}
                props[market_key][key]["odds"].append(outcome["price"])
                props[market_key][key]["books"][book] = outcome["price"]

    averaged = {}
    for market_key, bets in props.items():
        averaged[market_key] = {}
        for bet, data in bets.items():
            odds_list = data["odds"]
            book_odds = data["books"]
            decimals = [american_to_decimal(o) for o in odds_list]
            avg_decimal = sum(decimals) / len(decimals)
            avg_american = decimal_to_american(avg_decimal)
            best_odds = max(odds_list)
            best_book = max(book_odds, key=lambda b: book_odds[b])
            best_link = BOOK_LINKS.get(best_book, "#")
            averaged[market_key][bet] = {
                "average": avg_american,
                "best": best_odds,
                "best_book": best_book,
                "best_link": best_link,
                "books": len(odds_list)
            }
    return averaged

def get_odds():
    games_by_date = {}
    for sport in SPORTS:
        url = f"https://api.the-odds-api.com/v4/sports/{sport}/odds"
        params = {
            "apiKey": API_KEY,
            "regions": "us",
            "markets": "h2h",
            "oddsFormat": "american"
        }
        response = requests.get(url, params=params)
        data = response.json()
        for game in data:
            commence = game.get("commence_time", "")
            try:
                dt = datetime.fromisoformat(commence.replace("Z", "+00:00"))
                local_dt = dt.astimezone(zoneinfo.ZoneInfo("America/Los_Angeles"))
                date_str = local_dt.strftime("%A, %B %d")
                time_str = local_dt.strftime("%I:%M %p PT")
            except:
                date_str = "Unknown Date"
                time_str = ""

            game_data = {
                "sport": sport.replace("americanfootball_", "").replace("basketball_", "").upper(),
                "home": game["home_team"],
                "away": game["away_team"],
                "time": time_str,
                "event_id": game["id"],
                "sport_key": sport,
                "teams": {}
            }
            team_book_odds = {}
            for bookmaker in game["bookmakers"]:
                for market in bookmaker["markets"]:
                    for outcome in market["outcomes"]:
                        team = outcome["name"]
                        odds = outcome["price"]
                        book = bookmaker["title"]
                        if team not in game_data["teams"]:
                            game_data["teams"][team] = []
                            team_book_odds[team] = {}
                        game_data["teams"][team].append(odds)
                        team_book_odds[team][book] = odds

            for team, odds_list in game_data["teams"].items():
                decimals = [american_to_decimal(o) for o in odds_list]
                avg_decimal = sum(decimals) / len(decimals)
                avg_american = decimal_to_american(avg_decimal)
                best_odds = max(odds_list)
                best_book = max(team_book_odds[team], key=lambda b: team_book_odds[team][b])
                best_link = BOOK_LINKS.get(best_book, "#")
                implied_prob = round((1 / avg_decimal) * 100, 1)
                game_data["teams"][team] = {
                    "average": avg_american,
                    "best": best_odds,
                    "best_book": best_book,
                    "best_link": best_link,
                    "books": len(odds_list),
                    "win_prob": implied_prob
                }

            if date_str not in games_by_date:
                games_by_date[date_str] = []
            games_by_date[date_str].append(game_data)

    return games_by_date

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Live Odds Tracker</title>
    <style>
        body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; padding: 20px; }
        h1 { color: #e94560; text-align: center; }
        .nav { display: flex; justify-content: center; align-items: center; gap: 20px; margin: 20px 0; }
        .nav button { background: #0f3460; color: #eee; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; font-size: 1em; }
        .nav button:hover { background: #e94560; }
        .nav button:disabled { background: #333; cursor: not-allowed; }
        .date-title { color: #e94560; font-size: 1.6em; text-align: center; margin: 10px 0; }
        .sport-header { color: #e94560; font-size: 1.2em; margin-top: 20px; border-bottom: 2px solid #e94560; padding-bottom: 5px; }
        .game { background: #16213e; border-radius: 8px; padding: 15px; margin: 10px 0; }
        .game-title { font-size: 1.1em; font-weight: bold; margin-bottom: 5px; color: #fff; }
        .game-time { color: #888; font-size: 0.85em; margin-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
        th { background: #0f3460; padding: 8px; text-align: left; }
        td { padding: 8px; border-bottom: 1px solid #0f3460; }
        .positive { color: #4ecca3; }
        .negative { color: #e94560; }
        .book-link { color: #4ecca3; text-decoration: none; font-weight: bold; }
        .book-link:hover { text-decoration: underline; }
        .props-toggle { background: #0f3460; color: #eee; border: none; padding: 6px 14px; border-radius: 5px; cursor: pointer; margin-top: 10px; font-size: 0.85em; }
        .props-toggle:hover { background: #e94560; }
        .props-section { display: none; margin-top: 15px; }
        .props-section.open { display: block; }
        .prop-category { color: #4ecca3; font-size: 0.95em; margin: 10px 0 5px 0; font-weight: bold; border-bottom: 1px solid #4ecca3; padding-bottom: 3px; }
        .refresh { text-align: center; color: #888; font-size: 0.8em; margin-top: 20px; }
        .loading { color: #888; font-size: 0.85em; font-style: italic; padding: 10px 0; }
    </style>
    <script>
        function toggleProps(gameId, sportKey, eventId) {
            var section = document.getElementById('props-' + gameId);
            var btn = document.getElementById('btn-' + gameId);
            if (section.classList.contains('open')) {
                section.classList.remove('open');
                btn.textContent = '📊 Show Player Props';
                return;
            }
            section.classList.add('open');
            btn.textContent = '📊 Hide Player Props';
            if (section.dataset.loaded) return;
            section.dataset.loaded = true;
            section.innerHTML = '<div class="loading">Loading player props...</div>';
            fetch('/props?sport=' + sportKey + '&event_id=' + eventId)
                .then(r => r.json())
                .then(data => {
                    if (Object.keys(data).length === 0) {
                        section.innerHTML = '<div class="loading">No props available for this game yet.</div>';
                        return;
                    }
                    var html = '';
                    for (var market in data) {
                        html += '<div class="prop-category">' + market + '</div>';
                        html += '<table><tr><th>Bet</th><th>Average</th><th>Best</th><th>Best Book</th><th>Books</th></tr>';
                        for (var bet in data[market]) {
                            var d = data[market][bet];
                            var avgClass = d.average > 0 ? 'positive' : 'negative';
                            var bestClass = d.best > 0 ? 'positive' : 'negative';
                            var avgStr = (d.average > 0 ? '+' : '') + d.average;
                            var bestStr = (d.best > 0 ? '+' : '') + d.best;
                            html += '<tr>';
                            html += '<td>' + bet + '</td>';
                            html += '<td class="' + avgClass + '">' + avgStr + '</td>';
                            html += '<td class="' + bestClass + '">' + bestStr + '</td>';
                            html += '<td><a href="' + d.best_link + '" target="_blank" class="book-link">' + d.best_book + '</a></td>';
                            html += '<td>' + d.books + '</td>';
                            html += '</tr>';
                        }
                        html += '</table>';
                    }
                    section.innerHTML = html;
                })
                .catch(() => {
                    section.innerHTML = '<div class="loading">Could not load props.</div>';
                });
        }
    </script>
</head>
<body>
    <h1>🏀🏈 Live Odds Tracker</h1>
    <div class="nav">
        {% if day_index > 0 %}
            <a href="/?day={{ day_index - 1 }}"><button>← Previous Day</button></a>
        {% else %}
            <button disabled>← Previous Day</button>
        {% endif %}
        <div class="date-title">{{ current_date }}</div>
        {% if day_index < total_days - 1 %}
            <a href="/?day={{ day_index + 1 }}"><button>Next Day →</button></a>
        {% else %}
            <button disabled>Next Day →</button>
        {% endif %}
    </div>

    {% set last_sport = "" %}
    {% for game in games %}
        {% if game['sport'] != last_sport %}
            <div class="sport-header">{{ game['sport'] }}</div>
            {% set last_sport = game['sport'] %}
        {% endif %}
        <div class="game">
            <div class="game-title">{{ game['away'] }} vs {{ game['home'] }}</div>
            <div class="game-time">🕐 {{ game['time'] }}</div>
            <table>
                <tr><th>Team</th><th>Win %</th><th>Average</th><th>Best Line</th><th>Best Book</th><th>Books</th></tr>
                {% for team, data in game['teams'].items() %}
                <tr>
                    <td>{{ team }}</td>
                    <td class="positive">{{ data['win_prob'] }}%</td>
                    <td class="{{ 'positive' if data['average'] > 0 else 'negative' }}">{{ '+' if data['average'] > 0 else '' }}{{ data['average'] }}</td>
                    <td class="{{ 'positive' if data['best'] > 0 else 'negative' }}">{{ '+' if data['best'] > 0 else '' }}{{ data['best'] }}</td>
                    <td><a href="{{ data['best_link'] }}" target="_blank" class="book-link">{{ data['best_book'] }}</a></td>
                    <td>{{ data['books'] }}</td>
                </tr>
                {% endfor %}
            </table>
            <button class="props-toggle" id="btn-{{ loop.index }}" onclick="toggleProps('{{ loop.index }}', '{{ game['sport_key'] }}', '{{ game['event_id'] }}')">
                📊 Show Player Props
            </button>
            <div class="props-section" id="props-{{ loop.index }}"></div>
        </div>
    {% endfor %}
    <div class="refresh">Data updates every 10 minutes</div>
</body>
</html>
"""

@app.route("/")
def index():
    games_by_date = get_odds()
    dates = list(games_by_date.keys())
    day_index = int(request.args.get("day", 0))
    day_index = max(0, min(day_index, len(dates) - 1))
    current_date = dates[day_index] if dates else "No Games"
    games = games_by_date.get(current_date, [])
    return render_template_string(HTML, games=games, current_date=current_date, day_index=day_index, total_days=len(dates))

@app.route("/props")
def props():
    sport = request.args.get("sport")
    event_id = request.args.get("event_id")
    data = get_props(sport, event_id)
    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True)
