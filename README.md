# pinboardzine #

`pinboardzine` is a command line tool for converting unread bookmarks in Pinboard into a Kindle magazine for reading on your Kindle.


## Installation ##

`pinboardzine` is a program for Python 3.

Install `pinboardzine` as any other Python program:

    $ python setup.py install

If you don't want to install its dependencies system-wide, try installing it in a [virtual environment](http://www.virtualenv.org/).


## Configuring ##

`pinboardzine` uses the Readability Parser API to simplify HTML pages for Kindle viewing. Before you begin, [register a Readability API app](https://www.readability.com/developers/api) to get a Parser API token.

`pinboardzine` also uses Amazon's KindleGen tool to create the Kindle files. [Download it from Amazon](http://www.amazon.com/gp/feature.html?ie=UTF8&docId=1000765211) and install it so that `kindlegen` can be run from the command line. (This tool was developed with KindleGen v2.9.)


## Usage ##

Once you have a Parser API token, run `pinboardzine`.

    $ pinboardzine markpasc pinboardzine.mobi --readability-token b5Ae2d340BCBa8773FaebE0db4FCE45AABe2a0b6
    Pinboard password for markpasc:
    $ file pinboardzine.mobi
    pinboardzine.mobi: Mobipocket E-book "Pinboard_Unread"
    $

Once you have the `.mobi` file, send it to your Kindle as you would another book you have the file for, such as by copying it over USB, emailing it to your Kindle's `@free.kindle.com` email address, or using the [Send to Kindle desktop application](http://www.amazon.com/gp/sendtokindle).

If you have Send to Kindle on the Mac, you can probably open it by `open`ing the `.mobi` file:

    $ open pinboardzine.mobi

See `pinboardzine --help` for full help.


## Similar projects ##

Do you use [Pocket](http://getpocket.com/) instead of Pinboard? Try [daily\_digest](https://github.com/miyagawa/daily_digest).
