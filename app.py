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

def get_scores():
    scores = []
    espn_sports = [
        ("basketball/nba", "NBA"),
        ("football/nfl", "NFL")
    ]
    for sport_path, sport_label in espn_sports:
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/{sport_path}/scoreboard"
            r = requests.get(url, timeout=5)
            data = r.json()
            for event in data.get("events", []):
                comp = event["competitions"][0]
                status = event["status"]["type"]
                state = status["state"]
                status_detail = status.get("shortDetail", "")
                
                competitors = comp["competitors"]
                home = next((c for c in competitors if c["homeAway"] == "home"), competitors[0])
                away = next((c for c in competitors if c["homeAway"] == "away"), competitors[1])
                
                scores.append({
                    "sport": sport_label,
                    "home_team": home["team"]["shortDisplayName"],
                    "away_team": away["team"]["shortDisplayName"],
                    "home_score": home.get("score", "0"),
                    "away_score": away.get("score", "0"),
                    "state": state,
                    "status": status_detail
                })
        except:
            pass
    return scores

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
        * { box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; margin: 0; padding: 0; display: flex; flex-direction: column; min-height: 100vh; }
        h1 { color: #e94560; text-align: center; padding: 20px 0 0 0; margin: 0; }
        .layout { display: flex; flex: 1; gap: 0; }
        .sidebar { width: 260px; min-width: 220px; background: #0f3460; padding: 15px; overflow-y: auto; }
        .sidebar h2 { color: #e94560; font-size: 1em; margin: 0 0 12px 0; border-bottom: 1px solid #e94560; padding-bottom: 6px; }
        .score-card { background: #16213e; border-radius: 6px; padding: 10px; margin-bottom: 8px; font-size: 0.85em; }
        .score-sport { color: #888; font-size: 0.75em; margin-bottom: 4px; }
        .score-row { display: flex; justify-content: space-between; margin: 2px 0; }
        .score-team { color: #eee; }
        .score-num { color: #4ecca3; font-weight: bold; }
        .score-status { color: #e94560; font-size: 0.75em; margin-top: 4px; }
        .score-status.live { color: #4ecca3; }
        .score-status.final { color: #888; }
        .main { flex: 1; padding: 0 20px 20px 20px; overflow-y: auto; }
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
        .refresh { text-align: center; color: #888; font-size: 0.8em; margin-top: 20px; padding-bottom: 10px; }
        .loading { color: #888; font-size: 0.85em; font-style: italic; padding: 10px 0; }
        .no-scores { color: #888; font-size: 0.85em; font-style: italic; }
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

        function refreshScores() {
            fetch('/scores')
                .then(r => r.json())
                .then(data => {
                    var sidebar = document.getElementById('scores-list');
                    if (data.length === 0) {
                        sidebar.innerHTML = '<div class="no-scores">No games currently</div>';
                        return;
                    }
                    var html = '';
                    var lastSport = '';
                    data.forEach(function(g) {
                        if (g.sport !== lastSport) {
                            html += '<div class="score-sport">' + g.sport + '</div>';
                            lastSport = g.sport;
                        }
                        var stateClass = g.state === 'in' ? 'live' : (g.state === 'post' ? 'final' : '');
                        html += '<div class="score-card">';
                        html += '<div class="score-row"><span class="score-team">' + g.away_team + '</span><span class="score-num">' + g.away_score + '</span></div>';
                        html += '<div class="score-row"><span class="score-team">' + g.home_team + '</span><span class="score-num">' + g.home_score + '</span></div>';
                        html += '<div class="score-status ' + stateClass + '">' + g.status + '</div>';
                        html += '</div>';
                    });
                    sidebar.innerHTML = html;
                })
                .catch(() => {});
        }

        // Refresh scores every 30 seconds
        setInterval(refreshScores, 30000);
        window.onload = refreshScores;
    </script>
</head>
<body>
    <h1>🏀🏈 Live Odds Tracker</h1>
    <div class="layout">
        <div class="sidebar">
            <h2>📺 Live Scores</h2>
            <div id="scores-list"><div class="no-scores">Loading scores...</div></div>
        </div>
        <div class="main">
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
            <div class="refresh">Odds update every 10 minutes · Scores update every 30 seconds</div>
        </div>
    </div>
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

@app.route("/scores")
def scores():
    return jsonify(get_scores())

@app.route("/props")
def props():
    sport = request.args.get("sport")
    event_id = request.args.get("event_id")
    data = get_props(sport, event_id)
    return jsonify(data)

if __name__ == "__main__":
    app.run(debug=True)
