#!/usr/bin/env python3
"""Refresh original-style cards; never replace good cards with an error page."""
import argparse
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

ET.register_namespace('', 'http://www.w3.org/2000/svg')
BASE = 'https://github-stats-extended.vercel.app/api'


def card_urls(username):
    common = dict(username=username, theme='tokyonight', hide_border='true',
                  disable_animations='true', cache_seconds='21600')
    return {
        'github-stats.svg': BASE + '?' + urllib.parse.urlencode({
            **common, 'show_icons': 'true', 'include_all_commits': 'true',
            'custom_title': "Dhanunjay's GitHub Stats"}),
        'top-languages.svg': BASE + '/top-langs/?' + urllib.parse.urlencode({
            **common, 'layout': 'compact', 'hide_progress': 'true',
            'langs_count': '8', 'card_width': '450',
            'custom_title': 'Languages by usage'}),
    }


def prepare_card(name, data):
    root = ET.fromstring(data)
    if root.tag != '{http://www.w3.org/2000/svg}svg':
        raise ValueError('Response is not an SVG card')
    testids = {e.get('data-testid') for e in root.iter()}
    if name == 'github-stats.svg':
        if not {'stars', 'commits', 'prs', 'issues', 'contribs'} <= testids:
            raise ValueError('Stats response is missing its data')
    else:
        languages = [e for e in root.iter() if e.get('data-testid') == 'lang-name']
        if not languages or 'lang-progress' in testids:
            raise ValueError('Expected languages without progress bars')
        ranked = []
        for rank, element in enumerate(languages, 1):
            language = ''.join(element.itertext()).strip()
            if '%' in language:
                raise ValueError('Language percentages should be hidden')
            element.text = f'{rank}. {language}'
            ranked.append(element.text)
        root.set('aria-label', 'Languages ranked by source usage: ' + ', '.join(ranked))
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def download(url):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'profile-stats-refresh'})
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.read()
        except (OSError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--username', default='dhanunjay1729')
    parser.add_argument('--from-files', type=Path, help='Validate downloaded cards offline')
    args = parser.parse_args()
    # Download and validate both before overwriting either previous successful card.
    cards = {
        name: prepare_card(name, (args.from_files / name).read_bytes()
                           if args.from_files else download(url))
        for name, url in card_urls(args.username).items()
    }
    output = Path(__file__).resolve().parents[1] / 'assets'
    output.mkdir(exist_ok=True)
    for name, data in cards.items():
        (output / name).write_bytes(data)
    print('Refreshed stats and ranked languages cards.')


if __name__ == '__main__':
    main()
