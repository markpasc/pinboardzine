from datetime import date, datetime
import getpass
import json
import logging
from os.path import join
import re
import subprocess
import tempfile
import uuid
from xml.etree import ElementTree

import argh
from lxml.html.clean import Cleaner
import readability
import readability.cleaners
import requests
from requests.auth import HTTPBasicAuth


__version__ = '0.1'


CONTENTS_NCX_XML = """
    <ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="en">
        <head>
            <meta name="dtb:uid"/>
            <meta content="3" name="dtb:depth"/>
            <meta content="0" name="dtb:totalPageCount"/>
            <meta content="0" name="dtb:maxPageNumber"/>
        </head>
        <docTitle>
            <text></text>
        </docTitle>
        <navMap></navMap>
    </ncx>
    """


CONTENT_OPF_XML = """
    <package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
        <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
            <dc:title></dc:title>
            <dc:language>en</dc:language>
            <dc:identifier id="uid"></dc:identifier>
            <dc:creator>pinboard-zine</dc:creator>
            <dc:source>pinboard-zine</dc:source>
            <dc:date opf:event="publication"></dc:date>
            <!-- meta name="EmbeddedCover" content="images/image00002.jpeg"/ -->
            <meta name="output encoding" content="utf-8"/>
        </metadata>
        <manifest>
            <item href="contents.ncx" id="ncx" media-type="application/x-dtbncx+xml"/>
            <item href="contents.html" media-type="application/xhtml+xml" id="contents"/>
        </manifest>
        <spine toc="ncx"></spine>
        <tours></tours>
        <guide>
            <reference title="Beginning" type="start" href="contents.html"/>
        </guide>
    </package>
    """


readability.cleaners.html_cleaner = Cleaner(
    scripts=True, javascript=True, comments=True,
    style=True, links=True, meta=False, add_nofollow=False,
    processing_instructions=True, annoying_tags=False, remove_tags=None,
    # these options differ:
    page_structure=True, embedded=True, frames=True, forms=True,
    remove_unknown_tags=True, safe_attrs_only=True)


def contents_ncx_for_articles(articles, uid, title):
    root = ElementTree.fromstring(CONTENTS_NCX_XML)
    # Add head/meta name=dtb:uid
    uid_node = root.find("./{http://www.daisy.org/z3986/2005/ncx/}head/{http://www.daisy.org/z3986/2005/ncx/}meta[@name='dtb:uid']")
    uid_node.attrib['content'] = uid

    # Add docTitle/text
    title_node = root.find("./{http://www.daisy.org/z3986/2005/ncx/}docTitle/{http://www.daisy.org/z3986/2005/ncx/}text")
    title_node.text = title

    # Add navMap/navPointz.
    navmap_node = root.find("./{http://www.daisy.org/z3986/2005/ncx/}navMap")

    def nav_point(parent, order, title, src):
        point = ElementTree.SubElement(parent, '{http://www.daisy.org/z3986/2005/ncx/}navPoint', {
            'id': 'nav-{}'.format(order),
            'playOrder': str(order),
        })
        label = ElementTree.SubElement(point, '{http://www.daisy.org/z3986/2005/ncx/}navLabel')
        label_text = ElementTree.SubElement(label, '{http://www.daisy.org/z3986/2005/ncx/}text',
            text=title)
        content = ElementTree.SubElement(point, '{http://www.daisy.org/z3986/2005/ncx/}content', {
            'src': src
        })
        return point

    toc_point = nav_point(navmap_node, 1, 'Table of Contents', 'contents.html')
    first_article = articles[0]
    section_point = nav_point(toc_point, 2, 'Unread', first_article['filename'])
    for order, article in enumerate(articles, 3):
        nav_point(section_point, order, article['d'], article['filename'])

    ElementTree.register_namespace('', 'http://www.daisy.org/z3986/2005/ncx/')
    return ElementTree.tostring(root, encoding='unicode')


def content_opf_for_articles(articles, uid, title):
    root = ElementTree.fromstring(CONTENT_OPF_XML)

    title_node = root.find("./{http://www.idpf.org/2007/opf}metadata/{http://purl.org/dc/elements/1.1/}title")
    title_node.text = title

    uid_node = root.find("./{http://www.idpf.org/2007/opf}metadata/{http://purl.org/dc/elements/1.1/}identifier[@id='uid']")
    uid_node.text = uid

    date_node = root.find("./{http://www.idpf.org/2007/opf}metadata/{http://purl.org/dc/elements/1.1/}date")
    date_node.text = datetime.utcnow().isoformat()

    manifest_node = root.find("./{http://www.idpf.org/2007/opf}manifest")
    spine_node = root.find("./{http://www.idpf.org/2007/opf}spine")
    guide_node = root.find("./{http://www.idpf.org/2007/opf}guide")
    for article in articles:
        ElementTree.SubElement(guide_node, '{http://www.idpf.org/2007/opf}reference', {
            'title': article['d'],
            'href': article['filename'],
            'type': 'text',
        })
        ElementTree.SubElement(manifest_node, '{http://www.idpf.org/2007/opf}item', {
            'href': article['filename'],
            # Cheat by using the filename as the id too. The whole thing! Right in there!
            'id': article['filename'],
            'media-type': 'application/xhtml+xml',
        })
        ElementTree.SubElement(spine_node, '{http://www.idpf.org/2007/opf}itemref', {
            'idref': article['filename'],
        })

    ElementTree.register_namespace('', 'http://www.idpf.org/2007/opf')
    ElementTree.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')
    return ElementTree.tostring(root, encoding='unicode')


def contents_html_for_articles(articles, uid, title):
    HTML = """
        <html><head>
            <meta charset="utf-8">
            <title>{title}</title>
        </head><body>
            <h1>Table of Contents</h1>
            <ul>
            {items}
            </ul>
        </body></html>
    """
    ITEM = """
        <li><a href="{filename}">{d}</a></li>
    """

    items = ''.join(ITEM.format(**article) for article in articles)
    html = HTML.format(title=title, items=items)

    return html


def zine(username: 'Pinboard username to find articles for',
         outputfile: 'filename for the output mobi file',
         items: 'number of items to put in the zine' =20):
    req = requests.Session()
    req.headers.update({'user-agent': 'pinboard-zine/{}'.format(__version__)})

    # What pinboard account do I use?
    password = getpass.getpass('Password for {}: '.format(username))
    pinboard_auth = HTTPBasicAuth(username, password)
    res = requests.get('https://api.pinboard.in/v1/user/secret?format=json', auth=pinboard_auth, verify=True)
    if res.status_code == 401:
        raise argh.CommandError("Could not connect to Pinboard with that username. Is your password correct?")
    res.raise_for_status()
    data = res.json()
    secret = data['result']

    # We want the oldest, so ask for as many posts as possible.
    feed_url = 'https://feeds.pinboard.in/json/secret:{}/u:{}/toread/?count=400'.format(secret, username)
    res = req.get(feed_url, verify=True)
    # The secret should be correct, so don't try to handle an auth error.
    res.raise_for_status()
    data = res.json()

    # Get the oldest `items` items, oldest first.
    articles = data[-items:]
    articles.reverse()
    if logging.getLogger().isEnabledFor(logging.DEBUG):
        logging.debug("Got articles: %s", json.dumps(articles, sort_keys=True, indent=4))

    # Start making a new zine (tmpdir).
    zinedir = tempfile.mkdtemp()
    logging.debug("Writing mobi files to %s", zinedir)

    # For each of however many unread items:
    saved = list()
    for article in articles:
        # Fetch the resource.
        # TODO: we're asking for random internet junk so we should be more defensive probably
        url = article['u']
        try:
            res = req.get(url, timeout=10)
        except Exception as exc:
            logging.exception("Couldn't request article '%s', skipping", article['d'], exc_info=exc)
            continue
        # Is it HTML? We don't even really care if it was an error.
        if not res.headers['Content-Type'].startswith('text/html'):
            # Not for zining. (This `article` doesn't go in `saved`.)
            continue

        # Readabilitize it.
        readable = readability.Document(res.content.decode('utf-8'), url=url)
        # Summarize, then *further* remove some tags kindlegen will just remove anyway.
        readable.summary(html_partial=True)
        for badnode in readable.tags(readable.html, 'embed', 'frameset', 'frame'):
            badnode.drop_tree()
        for badnode in readable.tags(readable.html, 'acronym'):
            badnode.drop_tag()
        read_html = readable.get_clean_html()
        read_title = article['short_title'] = readable.short_title()
        logging.debug("HTML for article %s begins: %r", url, read_html[:50])

        # Write it to the zine directory.
        filename = article['filename'] = re.sub(r'\W+', '-', url) + '.html'
        with open(join(zinedir, filename), 'w') as f:
            f.write(read_html)
        # TODO: Are there images in the summarized HTML? Get those too.

        saved.append(article)

    # Write the metadata files to the zine directory.
    uid = uuid.uuid4().hex
    title = date.today().strftime("Pinboard Unread for %a %d %b %Y")
    ncx_xml = contents_ncx_for_articles(saved, uid, title)
    opf_xml = content_opf_for_articles(saved, uid, title)
    toc_html = contents_html_for_articles(saved, uid, title)
    with open(join(zinedir, 'contents.ncx'), 'w') as f:
        f.write(ncx_xml)
    content_opf_filename = join(zinedir, 'content.opf')
    with open(content_opf_filename, 'w') as f:
        f.write(opf_xml)
    with open(join(zinedir, 'contents.html'), 'w') as f:
        f.write(toc_html)

    logging.debug("Wrote all the files to %s, running kindlegen", zinedir)

    # TODO: Run kindlegen to mobify the zine.
    #subprocess.check_output(['kindlegen', content_opf_filename, '-o', outputfile], stderr=subprocess.STDOUT)

    # Everything went smoothly! Remove the zine dir.
    #shutil.rmtree(zinedir)


def main():
    argh.dispatch_command(zine)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logging.getLogger().setLevel(logging.DEBUG)
    main()
