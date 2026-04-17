#!/usr/bin/env python3
"""
Fetch recent LinkedIn posts and update posts.json.

Required environment variables:
  LINKEDIN_ACCESS_TOKEN  — OAuth 2.0 Bearer token (expires every ~60 days)
  LINKEDIN_PERSON_URN    — Your LinkedIn person ID (the alphanumeric string in
                           your profile URL, e.g. "spencerkoontz" or the numeric
                           ID returned by the /v2/me endpoint)

Setup:
  1. Create a LinkedIn Developer App at https://developer.linkedin.com
  2. Request the 'r_member_social' OAuth scope (requires LinkedIn review)
  3. Complete the OAuth flow to get an access token
  4. Store both values as GitHub repository secrets named above

To find your person URN, run once with a valid token:
  curl -H "Authorization: Bearer $LINKEDIN_ACCESS_TOKEN" \
       https://api.linkedin.com/v2/me
  The "id" field in the response is your person URN.
"""

import json
import os
import sys
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

POSTS_JSON = os.path.join(os.path.dirname(__file__), '..', 'posts.json')
API_BASE = 'https://api.linkedin.com/v2'
MAX_POSTS = 20
PREVIEW_CHARS = 280


def fetch(url, token):
    req = Request(url, headers={
        'Authorization': f'Bearer {token}',
        'LinkedIn-Version': '202304',
        'X-Restli-Protocol-Version': '2.0.0',
    })
    with urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode())


def epoch_ms_to_iso(epoch_ms):
    dt = datetime.fromtimestamp(epoch_ms / 1000, tz=timezone.utc)
    return dt.strftime('%Y-%m-%d')


def extract_text(post):
    try:
        return post['specificContent']['com.linkedin.ugc.ShareContent']['shareCommentary']['text']
    except (KeyError, TypeError):
        return ''


def post_url(post_id, person_urn):
    # LinkedIn post URLs use the numeric activity ID embedded in the URN
    # URN format: urn:li:ugcPost:1234567890
    activity_id = post_id.split(':')[-1]
    return f'https://www.linkedin.com/feed/update/urn:li:ugcPost:{activity_id}/'


def load_existing():
    try:
        with open(POSTS_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'linkedin': [], 'press': [], 'podcasts': []}


def main():
    token = os.environ.get('LINKEDIN_ACCESS_TOKEN', '').strip()
    person_urn = os.environ.get('LINKEDIN_PERSON_URN', '').strip()

    if not token:
        print('ERROR: LINKEDIN_ACCESS_TOKEN is not set.', file=sys.stderr)
        sys.exit(1)
    if not person_urn:
        print('ERROR: LINKEDIN_PERSON_URN is not set.', file=sys.stderr)
        sys.exit(1)

    encoded_urn = f'urn%3Ali%3Aperson%3A{person_urn}'
    url = (
        f'{API_BASE}/ugcPosts'
        f'?q=authors'
        f'&authors=List({encoded_urn})'
        f'&sortBy=LAST_MODIFIED'
        f'&count={MAX_POSTS}'
    )

    print(f'Fetching LinkedIn posts for person URN: {person_urn}')
    try:
        data = fetch(url, token)
    except HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f'ERROR: LinkedIn API returned HTTP {e.code}: {body}', file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f'ERROR: Network error: {e.reason}', file=sys.stderr)
        sys.exit(1)

    elements = data.get('elements', [])
    print(f'Retrieved {len(elements)} post(s) from LinkedIn.')

    existing = load_existing()
    existing_ids = {p['id'] for p in existing.get('linkedin', [])}

    new_posts = []
    for el in elements:
        post_id = el.get('id', '')
        if not post_id or post_id in existing_ids:
            continue
        text = extract_text(el)
        if not text:
            continue
        new_posts.append({
            'id': post_id,
            'date': epoch_ms_to_iso(el.get('created', {}).get('time', 0)),
            'text': text[:PREVIEW_CHARS],
            'url': post_url(post_id, person_urn),
        })

    if not new_posts:
        print('No new posts to add.')
        return

    # Prepend new posts and sort descending by date
    combined = new_posts + existing.get('linkedin', [])
    combined.sort(key=lambda p: p['date'], reverse=True)
    existing['linkedin'] = combined

    with open(POSTS_JSON, 'w', encoding='utf-8') as f:
        json.dump(existing, f, indent=2, ensure_ascii=False)
        f.write('\n')

    print(f'Added {len(new_posts)} new post(s) to posts.json.')


if __name__ == '__main__':
    main()
