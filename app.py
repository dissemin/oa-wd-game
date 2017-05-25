import csv
from functools import wraps

import flask
import requests
from flask import request, jsonify, abort

app = flask.Flask(__name__)


def has_log_for(tile_id):
    for log in read_logs():
        if log['tile'] == tile_id:
            return True
    return False


def create_logs():
    with open('logs.csv', 'w') as fp:
        return csv.DictWriter(fp, ['user', 'tile', 'decision']).writerows([])


def read_logs():
    with open('logs.csv', 'r') as fp:
        return csv.DictReader(fp)


def add_log(row):
    with open('logs.csv', 'a') as fp:
        csv.writer(fp).writerow([row['user'], row['tile'], row['decision']])



def get_papers(limit):
    sparql = """SELECT DISTINCT ?paper ?doi WHERE {
    ?paper wdt:P31 wd:Q13442814 ;
    wdt:P356 ?doi .
    FILTER NOT EXISTS {
    ?paper wdt:P953 ?foo .
    }
    } LIMIT """ + str(limit)

    results = requests.get('https://query.wikidata.org/sparql', {'query': sparql, 'format': 'json'}).json()
    papers = {}
    for res in results['results']['bindings']:
        id_ = res['paper']['value'].replace('http://www.wikidata.org/entity/', '')
        if id_ not in papers:
            papers[id_] = {'authors': [], 'id': id_}
        """if 'title' in res:
            papers[id_]['title'] = res['title']['value']
        if 'author' in res:
            papers[id_]['authors'].add({'plain': res['author']['value']})  # TODO: split first et list
        if 'date' in res:
            papers[id_]['date'] = res['date']['value']"""
        if 'doi' in res:
            papers[id_]['doi'] = res['doi']['value']
    return list(papers.values())


def format_paper(paper, hash_):
    return {
        "id": hash_,
        "sections": [
            {"type": "item", "q": paper['id']},
            {
                "type": "text",
                "title": paper['paper']['title'],
                "url": paper['record']['pdf_url'],
                "text": paper['record'].get('abstract', '')
            }
        ],
        "controls": [
            {
                "type": "buttons",
                "entries": [
                    {
                        "type": "green",
                        "decision": "yes",
                        "label": "Yes, it's the full version of the article",
                        "api_action": {
                            "action": "wbcreateclaim",
                            "entity": paper['id'],
                            "property": "P953",
                            "snaktype": "value",
                            "value": paper['record']['pdf_url']
                        }
                    },
                    {"type": "white", "decision": "skip", "label": "Skip"},
                    {"type": "blue", "decision": "no", "label": "No, it's not the same article"}
                ]
            }
        ]
    }


def build_tiles(limit):
    session = requests.Session()
    count = 0
    for paper in get_papers(limit):
        resp = session.post('http://old.dissem.in/api/query', json=paper).json()

        oa_paper = resp.get('paper', {})
        pdf_url = oa_paper.get('pdf_url', [])
        if not pdf_url:
            continue
        records = oa_paper.get('records', [])
        record = {}
        for record_ in records:
            if 'pdf_url' in record_ and record_['pdf_url'] == pdf_url:
                record = record_
                break

        paper['record'] = record
        paper['paper'] = oa_paper
        hash_ = paper['id'] + str(hash(paper['record']['pdf_url']))
        #if has_log_for(hash_):
        #    continue

        yield format_paper(paper, hash_)
        count += 1
        if count == limit:
            return


def jsonp(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        callback = request.args.get('callback', False)
        if callback:
            data = str(func(*args, **kwargs).data)
            content = str(callback) + '(' + data + ')'
            mimetype = 'application/javascript'
            return app.response_class(content, mimetype=mimetype)
        else:
            return func(*args, **kwargs)

    return decorated_function


def get_description():
    return {
        "label": {"en": "OABot game"},
        "description": {"en": "Game to add open version of scientific articles to Wikidata"},
        "icon": "https://association.dissem.in/files/grue_blue_120.png"
    }


def get_tiles(num, lang):
    return {
        "tiles": list(build_tiles(num))
    }


@app.route('/api', methods=['GET'])
@jsonp
def api():
    action = request.args.get('action', 'desc')
    if action == 'desc':
        return jsonify(get_description())
    if action == 'tiles':
        return jsonify(get_tiles(int(request.args.get('num', 100)), request.args.get('lang', 'en')))
    if action == 'log_action':
        if 'user' not in request.args or 'tile' not in request.args or 'decision' not in request.args:
            abort(400)
        add_log(request.args)
    else:
        abort(404)


if __name__ == "__main__":
    #create_logs()
    app.run()
