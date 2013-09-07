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
from argh.interaction import safe_input
import arghlog
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
            'title': article['title'],
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
        <li><a href="{filename}">{title}</a> {description}</li>
    """

    items = ''.join(ITEM.format(**article) for article in articles)
    html = HTML.format(title=title, items=items)

    return html


def zine(username: 'Pinboard username to find articles for',
         outputfile: 'filename for the output mobi file',
         items: 'number of items to put in the zine' =20,
         readability_token: 'Readability Parser API token to use to parse articles' =None):
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
    logging.debug("Using oldest %d articles of %d from Pinboard", items, len(data))
    articles = data[-items:]
    articles.reverse()

    # Start making a new zine (tmpdir).
    zinedir = tempfile.mkdtemp()
    logging.debug("Writing mobi files to %s", zinedir)

    if readability_token is None:
        try:
            readability_token = safe_input('Readability Parser API token: ')
        except KeyboardInterrupt:
            return

    # For each of however many unread items:
    saved = list()
    for article in articles:
        # Fetch the resource.
        url = article['u']
        params = {
            'url': url,
            'token': readability_token,
        }
        try:
            res = req.get('https://readability.com/api/content/v1/parser', params=params, timeout=10)
            res.raise_for_status()
        except Exception as exc:
            logging.exception("Couldn't request article '%s', skipping", article['d'], exc_info=exc)
            continue

        readable = res.json()
        article['title'] = readable['title'] or article['d']
        if not article['title']:
            article['title'] = '{} article'.format(readable['domain'])
        article['description'] = article['n'] or readable['dek'] or readable['excerpt']
        article['author'] = readable['author']
        article['content'] = readable['content']
        article['domain'] = readable['domain']
        article['url'] = url

        read_html = """<!DOCTYPE html>
        <html><head>
            <meta charset="utf-8">
            <title>{title}</title>
            <meta name="author" content="{author}">
            <meta name="description" content="{description}"
        </head><body>
            <div id="top">
                <h2>{title}</h2>
                <h3><a href="{url}">{domain}</a> &bull; by {author}</h3>
                <hr>
                {content}
            </div>
        </body></html>
        """.format(**article)

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
    parser = argh.ArghParser()
    arghlog.add_logging(parser)
    parser.set_default_command(zine)

    logging.getLogger('requests').propagate = False

    parser.dispatch()


if __name__ == '__main__':
    main()
