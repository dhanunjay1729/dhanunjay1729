#!/usr/bin/env python3
"""Validate generated stats cards before either is published."""
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def validate(name, data):
    root = ET.fromstring(data)
    if root.tag != '{http://www.w3.org/2000/svg}svg':
        raise ValueError('Response is not an SVG card')
    ids = {e.get('data-testid') for e in root.iter()}
    if name == 'github-stats.svg':
        required = {'stars', 'commits', 'prs', 'issues', 'contribs'}
        if not required <= ids:
            raise ValueError('Stats card is missing data')
        counts = {e.get('data-testid'): e.text for e in root.iter()
                  if e.get('data-testid') in required}
        print(f'Generated GitHub stats: {counts}')
    else:
        labels = [''.join(e.itertext()).strip() for e in root.iter()
                  if e.get('data-testid') == 'lang-name']
        if not labels or 'lang-progress' not in ids:
            raise ValueError('Expected language percentages and progress bar')
        if not all('%' in label for label in labels):
            raise ValueError('Language percentages are missing')
        print(f'Generated language shares: {labels}')


if __name__ == '__main__':
    for name in ('github-stats.svg', 'top-languages.svg'):
        validate(name, (ROOT / 'assets' / name).read_bytes())
