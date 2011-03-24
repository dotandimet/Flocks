## ![Logo V0.0](https://github.com/thedod/Flocks/raw/master/flocks-75x75.png "Feel free to send me a nicer logo :)") Flocks - Not all eggs in the same nest

_Flocks_ is [yet another attempt](http://r2.reallysimple.org/howto/radio2/) to go back from centralized [social networking services](https://secure.wikimedia.org/wikipedia/en/wiki/Social_networking_service) to decentralized [microblogging](https://secure.wikimedia.org/wikipedia/en/wiki/Microblogging).

At the moment, the part for publishing (the _nest_), is not yet written, but the part that browses inputs from others (the _flock_) is already here. It's true that we don't have nests to watch yet, but since _Flocks_ is based on RSS/Atom, we can already watch anything out there that has a feed.

This makes the current version look like yet-another-feed-aggregator, but the distinction between "_Flocks read-only_" and an aggregator (whether a web service or a desktop/phone app) is that if an aggregator is like a Tivo box (giving access to what was on TV _yesterday_), _Flocks_ is like the set top box that connects to it - its purpose is to let you figure out what's going on _now_.

### Screenshots:

Flock view:
<a target="_blank" href="https://github.com/thedod/Flocks/raw/master/flocks-screenshot-root.jpg"><img border="0" height="100" src="https://github.com/thedod/Flocks/raw/master/flocks-screenshot-root.jpg" alt="Flock view"></a>
Timeline view:
<a target="_blank" href="https://github.com/thedod/Flocks/raw/master/flocks-screenshot-timeline.jpg"><img border="0" height="100" src="https://github.com/thedod/Flocks/raw/master/flocks-screenshot-timeline.jpg" alt="Timeline view"></a>

### Prerequisites:

* [Python](http://python.org/download/)
* [Pysqlite](http://pypi.python.org/pypi/pysqlite/)
* [Feedparser](http://pypi.python.org/pypi/feedparser/)
* [Web.py](http://pypi.python.org/pypi/web.py/)

#### On Debian/ubuntu:

    sudo apt-get install python-sqlite python-feedparser python-webpy

#### Optional web.py tweak

You can also use my tweaked fork of wepby by doing (from this folder):

    git submodule update --init

The only difference is that in this version you can suppress sql logging to stdout in debug mode (see `DEBUG_SQL` at `flocks.py`).

### Running _Flocks_:

    python flocks.py

And then browse to `http://127.0.0.1:6378/` (6387 is _nest_ on a phone's keypad)

### Privacy, threats, and nuisances:

First time you run _Flocks_, it creates `flocks.db`, and asks you to "own your nest" (i.e. set a password). Some of the functionality is only available when you're logged in. Another difference is that when you're logged out, you only see the top-level flock called [case insensitive] `Public` (if there is one).

Note that this is a _single account_ system (no username. Only a password): If your sister wants to run her own _Flocks_ app on your PC, she should copy the folder, remove `flocks.db`, and set up her own nest.

This may lead to an **illusion of privacy**, since [at the moment] the content of `flocks.db` is _not_ encrypted (except for the password). This means that if your adversaries gets a copy of that file (physical access, trojans, court order, etc.), they can see what feeds you're interested in, how you call them, etc.

This means that you can show your public flock to people in logged-out mode (without leaving your computer unattended) and they probably wouldn't be able to know what feeds you use for the scoop you're working on, or that you're interested in knitting :).
 You _shouldn't_ - however - use _Flocks_ to browse to the feed of a rebel nest in onion land  unless your disk is encrypted and your computer is bullet-proof (i.e. never :) ). Even if you don't add the feed to your flock, the url can be recovered from your `flocks.db`.

#### Nuisances [as promised]:

The main reason for keeping flock information hard to get (even if not "100% secure") is to minimize the ability of others to analyze your [social network](https://secure.wikimedia.org/wikipedia/en/wiki/Social_network). As opposed to the paradigm of "following" or "befriending" peers in centralized social networks, I don't think I should make it public what I _watch_ (just like I don't upload my browser history), only what I _recommend_ (i.e. my public flock - that is also published as part of my _nest_ anyway).

For that reason - almost all http requests in _Flocks_ are POST and not GET, to avoid leakage of details about my flock via browser history or as HTTP_REFERER to sites. These urls don't reveal much, but if an adversary collects enough of them from enough people, this is cluster-analysis food).

This means that if you reload the page or use the back button, it makes _Flocks_ suspect a [CSRF attack](https://secure.wikimedia.org/wikipedia/en/wiki/Csrf). Nothing serious happens. You simply get redirected to the home page with a warning about a "stale browser page". Since almost everything is a click away, I hope this isn't _too much_ of a nuisance. Note that the homepage itself _can_ be reloaded without problems.

An additional nuisance (that I hope to fix eventually) is that you can't use _Flocks_ on more than a single browser tab (nothing bad happens if you do - you just get a redirection and warning). This is not inheret to CSRF protection, but happens because at the moment, the CSRF protection algorithm is pretty lame, and prefers to err on the safe side ;)

### What next?

Next thing on the list is the _nest_ which is actually a static html single page blog (+ css, js, rss, opml for the flock, etc.) that contains many posts. A link to a post in a nest also contains an anchor. This pretty small folder will be generated by the system, and the user will then [manually] upload to some site (implying that early adaptors will be people who can open a static html folder somewhere, or run a server in onionland :) ).

Later on - once we incorporate [DSA?] signatures of files, we can think (e.g.) of nest servers (or tree houses) that only accepts the admin[s] and anyone who is in an existing user's "Good friends" flock, but we need to establish identities first (key fingerprints as part of the feed's object in the flock).

I'll write more about why, how-to, what next, etc. in the wiki here, but I need to finish some code first :)

### Meanwhile:

[IMHO] It's already useful as it is. So please try it out, send me flocks (use the _share_ option to export as JSON), or even fork it and make it better.

Cheers.
