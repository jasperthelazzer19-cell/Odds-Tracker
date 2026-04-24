from flask import Flask, render_template_string, request, jsonify
import requests
from datetime import datetime
import zoneinfo

app = Flask(__name__)

API_KEY = "1cbed467fdd475e6e2816804ad864e83"
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
    scores = {"NBA": [], "NFL": []}
    espn_sports = [
        ("basketball/nba", "NBA"),
        ("football/nfl", "NFL")
    ]
    for sport_path, sport_label in espn_sports:
        try:
            url = "https://site.api.espn.com/apis/site/v2/sports/" + sport_path + "/scoreboard"
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
                scores[sport_label].append({
                    "event_id": event["id"],
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

def get_game_stats(sport, event_id):
    sport_path = "basketball/nba" if sport == "NBA" else "football/nfl"
    url = "https://site.api.espn.com/apis/site/v2/sports/" + sport_path + "/summary"
    try:
        r = requests.get(url, params={"event": event_id}, timeout=5)
        data = r.json()
        result = {"teams": [], "labels": []}
        labels_set = False
        for team_data in data.get("boxscore", {}).get("players", []):
            team_name = team_data["team"]["shortDisplayName"]
            team_stats = {"name": team_name, "players": []}
            for stat_group in team_data.get("statistics", []):
                keys = stat_group.get("labels", stat_group.get("keys", []))
                if not labels_set:
                    result["labels"] = keys
                    labels_set = True
                for athlete in stat_group.get("athletes", []):
                    player_name = athlete["athlete"]["shortName"]
                    stats = athlete.get("stats", [])
                    if not stats:
                        continue
                    player_row = {"name": player_name, "stats": {}}
                    for i, label in enumerate(keys):
                        if i < len(stats):
                            player_row["stats"][label] = stats[i]
                    team_stats["players"].append(player_row)
                break
            result["teams"].append(team_stats)
        return result
    except Exception as e:
        return {"error": str(e), "teams": [], "labels": []}

def get_props(sport, event_id):
    props_market = NBA_PROPS if "basketball" in sport else NFL_PROPS
    url = "https://api.the-odds-api.com/v4/sports/" + sport + "/events/" + event_id + "/odds"
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
                key = str(player) + " - " + str(bet_type) + " " + str(line)
                key = key.strip()
                if key not in props[market_key]:
                    props[market_key][key] = {"odds": [], "books": {}}
                props[market_key][key]["odds"].append(outcome["price"])
                props[market_key][key]["books"][book] = outcome["price"]
    averaged = {}
    for market_key, bets in props.items():
        averaged[market_key] = {}
        for bet, bdata in bets.items():
            odds_list = bdata["odds"]
            book_odds = bdata["books"]
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
    result = {"NBA": {}, "NFL": {}}
    sport_map = {"americanfootball_nfl": "NFL", "basketball_nba": "NBA"}
    for sport in SPORTS:
        label = sport_map[sport]
        url = "https://api.the-odds-api.com/v4/sports/" + sport + "/odds"
        params = {
            "apiKey": API_KEY,
            "regions": "us",
            "markets": "h2h",
            "oddsFormat": "american"
        }
        try:
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
        except:
            continue
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
                "home": game["home_team"],
                "away": game["away_team"],
                "time": time_str,
                "event_id": game["id"],
                "sport_key": sport,
                "teams": {}
            }
            team_book_odds = {}
            for bookmaker in game.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    for outcome in market.get("outcomes", []):
                        team = outcome["name"]
                        odds = outcome["price"]
                        book = bookmaker["title"]
                        if team not in game_data["teams"]:
                            game_data["teams"][team] = []
                            team_book_odds[team] = {}
                        game_data["teams"][team].append(odds)
                        team_book_odds[team][book] = odds
            for team, odds_list in game_data["teams"].items():
                if not odds_list:
                    continue
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
            if date_str not in result[label]:
                result[label][date_str] = []
            result[label][date_str].append(game_data)
    return result

HTML = """<!DOCTYPE html>
<html>
<head>
    <title>Live Odds Tracker</title>
    <style>
        * { box-sizing: border-box; }
        body { font-family: Arial, sans-serif; background: #1a1a2e; color: #eee; margin: 0; padding: 0; }
        h1 { color: #e94560; text-align: center; padding: 20px 0 0 0; margin: 0; }
        .layout { display: flex; min-height: 100vh; }
        .sidebar { width: 230px; min-width: 180px; background: #0f3460; padding: 15px; overflow-y: auto; flex-shrink: 0; }
        .sidebar h2 { color: #e94560; font-size: 1em; margin: 0 0 10px 0; border-bottom: 1px solid #e94560; padding-bottom: 6px; }
        .sidebar-sport { color: #4ecca3; font-size: 0.8em; font-weight: bold; margin: 10px 0 5px 0; }
        .score-card { background: #16213e; border-radius: 6px; padding: 8px 10px; margin-bottom: 6px; font-size: 0.82em; cursor: pointer; }
        .score-card:hover { background: #1e3a6e; }
        .score-row { display: flex; justify-content: space-between; margin: 2px 0; }
        .score-team { color: #eee; }
        .score-num { color: #4ecca3; font-weight: bold; }
        .score-status { font-size: 0.75em; margin-top: 3px; }
        .live { color: #4ecca3; }
        .final { color: #888; }
        .pre { color: #aaa; }
        .no-scores { color: #888; font-size: 0.82em; font-style: italic; }
        .main { flex: 1; padding: 0 20px 20px 20px; min-width: 0; }
        .sport-tabs { display: flex; gap: 10px; margin: 20px 0 10px 0; justify-content: center; }
        .tab-btn { background: #0f3460; color: #eee; border: none; padding: 10px 30px; border-radius: 5px; cursor: pointer; font-size: 1.1em; font-weight: bold; }
        .tab-btn:hover { background: #c73652; }
        .tab-btn.active { background: #e94560; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
        .nav { display: flex; justify-content: center; align-items: center; gap: 20px; margin: 15px 0; }
        .nav a button, .nav button { background: #0f3460; color: #eee; border: none; padding: 8px 18px; border-radius: 5px; cursor: pointer; font-size: 0.95em; }
        .nav a button:hover, .nav button:hover { background: #e94560; }
        .nav button:disabled { background: #333; cursor: not-allowed; }
        .date-title { color: #e94560; font-size: 1.4em; }
        .game { background: #16213e; border-radius: 8px; padding: 15px; margin: 10px 0; }
        .game-title { font-size: 1.05em; font-weight: bold; margin-bottom: 5px; color: #fff; cursor: pointer; }
        .game-title:hover { color: #4ecca3; }
        .game-time { color: #888; font-size: 0.85em; margin-bottom: 10px; }
        table { width: 100%; border-collapse: collapse; margin-bottom: 10px; }
        th { background: #0f3460; padding: 7px 8px; text-align: left; font-size: 0.82em; }
        td { padding: 7px 8px; border-bottom: 1px solid #0f3460; font-size: 0.82em; }
        .positive { color: #4ecca3; }
        .negative { color: #e94560; }
        .book-link { color: #4ecca3; text-decoration: none; font-weight: bold; }
        .book-link:hover { text-decoration: underline; }
        .btn-props { background: #0f3460; color: #eee; border: none; padding: 6px 13px; border-radius: 5px; cursor: pointer; font-size: 0.83em; margin-top: 8px; }
        .btn-props:hover { background: #e94560; }
        .props-section { display: none; margin-top: 12px; }
        .props-section.open { display: block; }
        .prop-cat { color: #4ecca3; font-size: 0.9em; margin: 10px 0 4px 0; font-weight: bold; border-bottom: 1px solid #4ecca3; padding-bottom: 2px; }
        .refresh { text-align: center; color: #888; font-size: 0.8em; margin-top: 20px; }
        .loading { color: #888; font-size: 0.85em; font-style: italic; padding: 8px 0; }
        .no-games { color: #888; text-align: center; padding: 30px; font-style: italic; }
        .modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.75); z-index: 999; align-items: flex-start; justify-content: center; overflow-y: auto; padding: 40px 20px; }
        .modal-overlay.open { display: flex; }
        .modal { background: #16213e; border-radius: 10px; padding: 25px; max-width: 950px; width: 100%; position: relative; }
        .modal-close { position: absolute; top: 12px; right: 12px; background: #e94560; border: none; color: #fff; width: 28px; height: 28px; border-radius: 50%; cursor: pointer; font-size: 0.95em; }
        .modal-title { color: #e94560; font-size: 1.2em; font-weight: bold; margin-bottom: 15px; }
        .modal-team { color: #4ecca3; font-size: 0.95em; font-weight: bold; margin: 14px 0 6px 0; }
        .stats-wrap { overflow-x: auto; }
        .stats-tbl { border-collapse: collapse; font-size: 0.78em; min-width: 100%; }
        .stats-tbl th { background: #0f3460; padding: 5px 8px; white-space: nowrap; text-align: left; }
        .stats-tbl td { padding: 5px 8px; border-bottom: 1px solid #0f3460; white-space: nowrap; }
    </style>
    <script>
        var currentSport = 'NBA';

        function switchTab(sport) {
            currentSport = sport;
            document.querySelectorAll('.tab-btn').forEach(function(b) { b.classList.remove('active'); });
            document.querySelectorAll('.tab-content').forEach(function(c) { c.classList.remove('active'); });
            document.getElementById('content-' + sport).classList.add('active');
            document.getElementById('tab-' + sport).classList.add('active');
        }

        function toggleProps(gameId, sportKey, eventId) {
            var section = document.getElementById('props-' + gameId);
            var btn = document.getElementById('btn-' + gameId);
            if (section.classList.contains('open')) {
                section.classList.remove('open');
                btn.textContent = 'Show Player Props';
                return;
            }
            section.classList.add('open');
            btn.textContent = 'Hide Player Props';
            if (section.dataset.loaded) return;
            section.dataset.loaded = '1';
            section.innerHTML = '<div class="loading">Loading props...</div>';
            fetch('/props?sport=' + encodeURIComponent(sportKey) + '&event_id=' + encodeURIComponent(eventId))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    var keys = Object.keys(data);
                    if (keys.length === 0) {
                        section.innerHTML = '<div class="loading">No props available yet.</div>';
                        return;
                    }
                    var html = '';
                    keys.forEach(function(market) {
                        html += '<div class="prop-cat">' + market + '</div>';
                        html += '<table><tr><th>Bet</th><th>Avg</th><th>Best</th><th>Best Book</th><th>Books</th></tr>';
                        Object.keys(data[market]).forEach(function(bet) {
                            var d = data[market][bet];
                            var avgStr = (d.average > 0 ? '+' : '') + d.average;
                            var bestStr = (d.best > 0 ? '+' : '') + d.best;
                            html += '<tr><td>' + bet + '</td>';
                            html += '<td class="' + (d.average > 0 ? 'positive' : 'negative') + '">' + avgStr + '</td>';
                            html += '<td class="' + (d.best > 0 ? 'positive' : 'negative') + '">' + bestStr + '</td>';
                            html += '<td><a href="' + d.best_link + '" target="_blank" class="book-link">' + d.best_book + '</a></td>';
                            html += '<td>' + d.books + '</td></tr>';
                        });
                        html += '</table>';
                    });
                    section.innerHTML = html;
                })
                .catch(function() { section.innerHTML = '<div class="loading">Could not load props.</div>'; });
        }

        function openStats(sport, eventId, title) {
            var modal = document.getElementById('stats-modal');
            document.getElementById('modal-title').textContent = title;
            document.getElementById('modal-body').innerHTML = '<div class="loading">Loading stats...</div>';
            modal.classList.add('open');
            if (!eventId) {
                document.getElementById('modal-body').innerHTML = '<div class="loading">No event ID available.</div>';
                return;
            }
            fetch('/game_stats?sport=' + encodeURIComponent(sport) + '&event_id=' + encodeURIComponent(eventId))
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data.teams || data.teams.length === 0) {
                        document.getElementById('modal-body').innerHTML = '<div class="loading">Stats not available yet.</div>';
                        return;
                    }
                    var html = '';
                    data.teams.forEach(function(team) {
                        if (!team.players || team.players.length === 0) return;
                        html += '<div class="modal-team">' + team.name + '</div>';
                        html += '<div class="stats-wrap"><table class="stats-tbl"><tr><th>Player</th>';
                        data.labels.forEach(function(l) { html += '<th>' + l + '</th>'; });
                        html += '</tr>';
                        team.players.forEach(function(p) {
                            html += '<tr><td>' + p.name + '</td>';
                            data.labels.forEach(function(l) { html += '<td>' + (p.stats[l] || '-') + '</td>'; });
                            html += '</tr>';
                        });
                        html += '</table></div>';
                    });
                    document.getElementById('modal-body').innerHTML = html || '<div class="loading">No stats yet.</div>';
                })
                .catch(function() { document.getElementById('modal-body').innerHTML = '<div class="loading">Could not load stats.</div>'; });
        }

        function closeModal() {
            document.getElementById('stats-modal').classList.remove('open');
        }

        function refreshScores() {
            fetch('/scores')
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    ['NBA', 'NFL'].forEach(function(sport) {
                        var el = document.getElementById('scores-' + sport);
                        if (!el) return;
                        var games = data[sport] || [];
                        if (games.length === 0) {
                            el.innerHTML = '<div class="no-scores">No games today</div>';
                            return;
                        }
                        var html = '';
                        games.forEach(function(g) {
                            var sc = g.state === 'in' ? 'live' : (g.state === 'post' ? 'final' : 'pre');
                            html += '<div class="score-card" onclick="openStats(\'' + sport + '\', \'' + g.event_id + '\', \'' + g.away_team.replace(/'/g, '') + ' vs ' + g.home_team.replace(/'/g, '') + '\')">';
                            html += '<div class="score-row"><span class="score-team">' + g.away_team + '</span><span class="score-num">' + g.away_score + '</span></div>';
                            html += '<div class="score-row"><span class="score-team">' + g.home_team + '</span><span class="score-num">' + g.home_score + '</span></div>';
                            html += '<div class="score-status ' + sc + '">' + g.status + '</div>';
                            html += '</div>';
                        });
                        el.innerHTML = html;
                    });
                })
                .catch(function() {});
        }

        setInterval(refreshScores, 30000);
        window.onload = function() {
            switchTab('NBA');
            refreshScores();
        };
    </script>
</head>
<body>
    <h1>🏀🏈 Live Odds Tracker</h1>

    <div class="modal-overlay" id="stats-modal" onclick="if(event.target===this)closeModal()">
        <div class="modal">
            <button class="modal-close" onclick="closeModal()">x</button>
            <div class="modal-title" id="modal-title"></div>
            <div id="modal-body"></div>
        </div>
    </div>

    <div class="layout">
        <div class="sidebar">
            <h2>Live Scores</h2>
            <div class="sidebar-sport">NBA</div>
            <div id="scores-NBA"><div class="no-scores">Loading...</div></div>
            <div class="sidebar-sport">NFL</div>
            <div id="scores-NFL"><div class="no-scores">Loading...</div></div>
        </div>
        <div class="main">
            <div class="sport-tabs">
                <button class="tab-btn" id="tab-NBA" onclick="switchTab('NBA')">NBA</button>
                <button class="tab-btn" id="tab-NFL" onclick="switchTab('NFL')">NFL</button>
            </div>

            <div class="tab-content" id="content-NBA">
                <div class="nav">
                    {% if nba_day > 0 %}
                        <a href="/?sport=NBA&day={{ nba_day - 1 }}"><button>Prev Day</button></a>
                    {% else %}
                        <button disabled>Prev Day</button>
                    {% endif %}
                    <div class="date-title">{{ nba_date }}</div>
                    {% if nba_day < nba_total - 1 %}
                        <a href="/?sport=NBA&day={{ nba_day + 1 }}"><button>Next Day</button></a>
                    {% else %}
                        <button disabled>Next Day</button>
                    {% endif %}
                </div>
                {% if nba_games %}
                    {% for game in nba_games %}
                    <div class="game">
                        <div class="game-title" onclick="openStats('NBA', '', '{{ game.away }} vs {{ game.home }}')">
                            {{ game.away }} vs {{ game.home }} &nbsp;<span style="color:#4ecca3;font-size:0.75em;">click for stats</span>
                        </div>
                        <div class="game-time">{{ game.time }}</div>
                        <table>
                            <tr><th>Team</th><th>Win%</th><th>Average</th><th>Best Line</th><th>Best Book</th><th>Books</th></tr>
                            {% for team, d in game.teams.items() %}
                            <tr>
                                <td>{{ team }}</td>
                                <td class="positive">{{ d.win_prob }}%</td>
                                <td class="{{ 'positive' if d.average > 0 else 'negative' }}">{{ '+' if d.average > 0 else '' }}{{ d.average }}</td>
                                <td class="{{ 'positive' if d.best > 0 else 'negative' }}">{{ '+' if d.best > 0 else '' }}{{ d.best }}</td>
                                <td><a href="{{ d.best_link }}" target="_blank" class="book-link">{{ d.best_book }}</a></td>
                                <td>{{ d.books }}</td>
                            </tr>
                            {% endfor %}
                        </table>
                        <button class="btn-props" id="btn-nba-{{ loop.index }}" onclick="toggleProps('nba-{{ loop.index }}', '{{ game.sport_key }}', '{{ game.event_id }}')">Show Player Props</button>
                        <div class="props-section" id="props-nba-{{ loop.index }}"></div>
                    </div>
                    {% endfor %}
                {% else %}
                    <div class="no-games">No NBA games on this date.</div>
                {% endif %}
            </div>

            <div class="tab-content" id="content-NFL">
                <div class="nav">
                    {% if nfl_day > 0 %}
                        <a href="/?sport=NFL&day={{ nfl_day - 1 }}"><button>Prev Day</button></a>
                    {% else %}
                        <button disabled>Prev Day</button>
                    {% endif %}
                    <div class="date-title">{{ nfl_date }}</div>
                    {% if nfl_day < nfl_total - 1 %}
                        <a href="/?sport=NFL&day={{ nfl_day + 1 }}"><button>Next Day</button></a>
                    {% else %}
                        <button disabled>Next Day</button>
                    {% endif %}
                </div>
                {% if nfl_games %}
                    {% for game in nfl_games %}
                    <div class="game">
                        <div class="game-title" onclick="openStats('NFL', '', '{{ game.away }} vs {{ game.home }}')">
                            {{ game.away }} vs {{ game.home }} &nbsp;<span style="color:#4ecca3;font-size:0.75em;">click for stats</span>
                        </div>
                        <div class="game-time">{{ game.time }}</div>
                        <table>
                            <tr><th>Team</th><th>Win%</th><th>Average</th><th>Best Line</th><th>Best Book</th><th>Books</th></tr>
                            {% for team, d in game.teams.items() %}
                            <tr>
                                <td>{{ team }}</td>
                                <td class="positive">{{ d.win_prob }}%</td>
                                <td class="{{ 'positive' if d.average > 0 else 'negative' }}">{{ '+' if d.average > 0 else '' }}{{ d.average }}</td>
                                <td class="{{ 'positive' if d.best > 0 else 'negative' }}">{{ '+' if d.best > 0 else '' }}{{ d.best }}</td>
                                <td><a href="{{ d.best_link }}" target="_blank" class="book-link">{{ d.best_book }}</a></td>
                                <td>{{ d.books }}</td>
                            </tr>
                            {% endfor %}
                        </table>
                        <button class="btn-props" id="btn-nfl-{{ loop.index }}" onclick="toggleProps('nfl-{{ loop.index }}', '{{ game.sport_key }}', '{{ game.event_id }}')">Show Player Props</button>
                        <div class="props-section" id="props-nfl-{{ loop.index }}"></div>
                    </div>
                    {% endfor %}
                {% else %}
                    <div class="no-games">No NFL games on this date.</div>
                {% endif %}
            </div>

            <div class="refresh">Odds update every 10 minutes &middot; Scores update every 30 seconds</div>
        </div>
    </div>
</body>
</html>"""

@app.route("/")
def index():
    all_odds = get_odds()
    sport_param = request.args.get("sport", "NBA")

    nba_dates = list(all_odds["NBA"].keys())
    nfl_dates = list(all_odds["NFL"].keys())

    nba_day = int(request.args.get("day", 0)) if sport_param == "NBA" else 0
    nfl_day = int(request.args.get("day", 0)) if sport_param == "NFL" else 0

    nba_day = max(0, min(nba_day, len(nba_dates) - 1)) if nba_dates else 0
    nfl_day = max(0, min(nfl_day, len(nfl_dates) - 1)) if nfl_dates else 0

    nba_date = nba_dates[nba_day] if nba_dates else "No Games"
    nfl_date = nfl_dates[nfl_day] if nfl_dates else "No Games"

    nba_games = all_odds["NBA"].get(nba_date, [])
    nfl_games = all_odds["NFL"].get(nfl_date, [])

    return render_template_string(HTML,
        nba_games=nba_games, nba_date=nba_date, nba_day=nba_day, nba_total=max(len(nba_dates), 1),
        nfl_games=nfl_games, nfl_date=nfl_date, nfl_day=nfl_day, nfl_total=max(len(nfl_dates), 1)
    )

@app.route("/scores")
def scores():
    return jsonify(get_scores())

@app.route("/game_stats")
def game_stats():
    sport = request.args.get("sport", "NBA")
    event_id = request.args.get("event_id", "")
    if not event_id:
        return jsonify({"error": "no id", "teams": [], "labels": []})
    return jsonify(get_game_stats(sport, event_id))

@app.route("/props")
def props():
    sport = request.args.get("sport", "")
    event_id = request.args.get("event_id", "")
    return jsonify(get_props(sport, event_id))
@app.route("/debug")
def debug():
    try:
        r = requests.get("https://api.the-odds-api.com/v4/sports", params={"apiKey": API_KEY}, timeout=10)
        return jsonify({"status": r.status_code, "body": r.json()})
    except Exception as e:
        return jsonify({"error": str(e)})
if __name__ == "__main__":
    app.run(debug=True)
