import tempfile

import argh
import readability
import requests
from requests.auth import HTTPBasicAuth


def zine(username: 'Pinboard username to find articles for',
         items: 'number of items to put in the zine' =20,
         outputfile: 'filename for the output mobi file'):
    # What pinboard account do I use?
    password = getpass.getpass('Password for {}: '.format(username))
    pinboard_auth = HTTPBasicAuth(username, password)
    res = requests.get('https://api.pinboard.in/v1/user/secret?format=json', auth=pinboard_auth, verify=True)
    if res.status_code == 401:
        raise argh.CommandError("Could not connect to Pinboard with that username. Is your password correct?")
    r.raise_for_status()
    data = r.json()
    secret = data['result']

    # We want the oldest, so ask for as many posts as possible.
    feed_url = 'https://feeds.pinboard.in/json/secret:{}/u:{}/toread/?count=400'.format(secret, username)
    res = requests.get(feed_url, verify=True)
    # The secret should be correct, so don't try to handle an auth error.
    r.raise_for_status()
    data = r.json()

    # Get the oldest `items` items, oldest first.
    articles = data[-items:]
    articles.reverse()

    # Start making a new zine (tmpdir).
    zinedir = tempfile.mkdtemp()

    # For each of however many unread items:
    saved = list()
    for article in articles:
        # Fetch the resource.
        res = requests.get(article)
        # Is it HTML?
        if not res.headers['Content-Type'].startswith('text/html'):
            # Not for zining. (This `article` doesn't go in `saved`.)
            continue

        # TODO: Readabilitize it.
        # TODO: Write it to the zine directory.

        saved.append(article)

    # TODO: Write the metadata files to the zine directory.
    # TODO: Run kindlegen to mobify the zine.

    # Everything went smoothly! Remove the zine dir.
    shutil.rmtree(zinedir)


def main():
    argh.dispatch_command(zine)


if __name__ == '__main__':
    main()
