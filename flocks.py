# -*- coding: utf-8 -*-

### config
DEBUG = True
DEBUG_SQL = False
DB_FILENAME = 'flocks.db'
DEFAULT_FLOCK_FILENAME = 'default_flock.js'
LOGIN_TIMEOUT_SECONDS = 3600 # 1 hour.
FEED_REFRESH_SECONDS = 120 # delay (for each feed) between javascript fetches
FEED_CACHE_TIMEOUT = 180 # Some feeds are etag and last-modified deaf/dumb
MAX_PAGE_ENTRIES = 50
MAX_SINGLE_FEED_ENTRIES = 50
MAX_FLOCK_FEED_ENTRIES = 10
HTTP_PORT = 6378 # "Nest" on phone keyboard
###

from copy import deepcopy
import web
from sys import argv
argv[1:] = ['127.0.0.1:{0}'.format(HTTP_PORT)] # That's how you set ip:port in web.py ;) 
web.config.debug = DEBUG
web.config.debug_sql = DEBUG_SQL # This only works for a tweaked version of web.py (see README)

urls = (
    "/", "view_index",
    "/channel", "view_channel",
    "/channels", "view_channels",
    "/login","view_login",
    "/logout","view_logout",
    "/set_password","view_set_password",
    "/api/channel","view_api_channel",
)

app = web.application(urls, globals())
global_db = web.database(dbn='sqlite',db=DB_FILENAME)

#### Session/debug tweak from http://webpy.org/cookbook/session_with_reloader
if web.config.get('_session') is None:
    global_session = web.session.Session(app, web.session.DiskStore('sessions'))
    web.config._session = global_session
else:
    global_session = web.config._session

#### handy time utils
import datetime
def now(): return datetime.datetime.utcnow()
def seconds2delta(secs): return datetime.timedelta(0,secs)
def datetime2str(dt): return dt.strftime('%Y-%m-%dT%H:%M:%S')
def str2datetime(s): return datetime.datetime.strptime(s,'%Y-%m-%dT%H:%M:%S')
def timestruct2datetime(t): return datetime.datetime(*t[:6])
def timestruct2str(t):
    "can also accept None (doesn't raise error)"
    return t and datetime2str(timestruct2datetime(t))
def timestruct2friendly(t):
    "can also accept None (doesn't raise error)"
    return t and timestruct2datetime(t).ctime()

#### The flash() trick they do at http://flask.pocoo.org
def flash(msg):
    flashes = global_session.get('flashed_messages',[])
    global_session['flashed_messages'] = flashes+[msg]

def pop_flashed_messages():
    flashes = global_session.get('flashed_messages',[])
    global_session['flashed_messages'] = []
    return flashes

#### CSRF protection
def csrf_token():
    """In the template, you should add inside your POST forms:
  <input type=hidden name=csrf_token value="$csrf_token()">
You'll need to initialize your render object like:
  web.template.render('templates',globals={'csrf_token':csrf_token})"""
    if not global_session.has_key('csrf_token'):
        from uuid import uuid4
        global_session.csrf_token=uuid4().hex
    return global_session.csrf_token

def csrf_protected(f):
    """Usage:
  @csrf_protected
  def POST(self):
      ...
(Remember to have a csrf_token() hidden field at the form itself)"""
    def decorated(*args,**kwargs):
        inp = web.input()
        if not (inp.has_key('csrf_token') and inp.csrf_token==global_session.pop('csrf_token',None)):
            #raise web.HTTPError(
            #    "400 Bad request",
            #    {'content-type':'text/html'},
            #    'CSRF forgery (or stale browser form). <a href="">Back to the form</a>')
            ### The "don't panic" approach :) Yes. I know it mixes low level and GUI.
            flash('Something went wrong. Maybe a "stale" page in the browser. Please try again.')
            raise web.seeother('/')
        return f(*args,**kwargs)
    return decorated

### JsonDb
from exceptions import KeyError, SyntaxError
from UserDict import DictMixin
try:
    import simplejson as json
except:
    import json

class JsonDb(DictMixin):
    """A thread-safe persistent-dictionary on top of web.py's web.database. Can only store "jsonable" values.
example:
  db = web.database(dbn="sqlite",db="my.db")
  jdb = JsonDb(db,"mynamespace",key1=val1,...) # if namespace is ommitted, "global" is used
  if jdb.has_key('foo'): # Behaves like a dict
    jdb['bar']={'foo':jdb['foo'],'maybe':jdb.get('maybe','maybe not'),'keys':jdb.keys()}"""
    def __init__(self,db,namespace='global',**kwargs):
        self.db = db
        self.namespace = namespace
        self.table = "jsondb_{0}".format(self.namespace)
        # Don't know why web.database.query doesn't work well with create table :(
        self.db.query('create table if not exists {0} (key text unique,value blob)'.format(self.table),_test=False)
        self.update(kwargs)
    def keys(self):
        return [r.key for r in self.db.select(self.table,what='key')]
    def _get(self,key):
        return list(self.db.select(self.table,what='value',where='key=$k',vars={'k':key},_test=False))
    def has_key(self,key):
        return not not self._get(key)
    def __getitem__(self,key):
        s = self._get(key)
        if not s:
            raise KeyError,key
        return json.loads(s[0].value)
    def __delitem__(self,key):
        if not self.has_key(key):
            raise KeyError,key
        self.db.delete(self.table,where='key=$k',vars={'k':key},_test=False)
    def __setitem__(self,key,value):
        if self.has_key(key):
            self.db.update(self.table,where='key=$k',vars={'k':key},value=json.dumps(value),_test=False)
        else:
            self.db.insert(self.table,key=key,value=json.dumps(value),_test=False)
    def __repr__(self):     
        return '<JsonDB {0}:{1} {2}>'.format(`self.db`,`self.namespace`,`self.keys()`)


#### Sam - Single accout manager
class Sam:
    """There's a single global Sam instance called global_account (or 'account' inside templates).
Methods:
    is_new() - True for a new db before the first time you set a password
    is_logged_in()
    login(password)
    logout()
    change_password(oldpass,newpass) - oldpass is ignored if is_new()"""
    def __init__(self,db,auto_logout_seconds=3600):
        self.jdb = JsonDb(db,"sam")
        self.timeout = seconds2delta(auto_logout_seconds)

    def is_new(self):
        return not self.jdb.has_key('passhash')

    def is_logged_in(self):
        expires = global_session.get('sam_expires')
        if expires:
            if self.is_new(): # happens when you delete db but have a stale cookie
                del global_session['sam_expires']
                return False
            if datetime2str(now())<expires:
                self._renew_lease()
                return True
            else:
                flash("Automatically logged out because of idle time.")
                self.logout()
        return False

    def _renew_lease(self):
        global_session['sam_expires'] = datetime2str(now()+self.timeout)
    
    def _check_password(self,password):
        import hmac
        return hmac.new(self.jdb['key'].decode('hex'),password).hexdigest() == self.jdb['passhash']

    def login(self,password):
        if self._check_password(password):
            self._renew_lease()
            return True
        self.logout()
        return False

    def logout(self):
        if global_session.has_key('sam_expires'):
            del global_session['sam_expires']

    def change_password(self,oldpass,newpass):
        "oldpass is ignored if self.is_new()"
        if self.is_new() or self._check_password(oldpass):
            import hmac
            from os import urandom
            key = urandom(20)
            self.jdb.update({
                'key':key.encode('hex'),
                'passhash':hmac.new(key,newpass).hexdigest()})
            self._renew_lease()
            return True
        return False
    
### Flock functions
def flockslug(obj):
    "Receives a name string for a flock node (dict). Returns an html-safe slug. Case insensitive."
    if type(obj) == type({}):
        obj = obj.get('url',obj.get('title'))
    return 'f%d' % hash(obj.lower())

def flock_get(flock,slugpath):
    if not slugpath:
        return flock
    if flock.get('type')!="flock":
        raise TypeError,'Feeds have no children'
    found=[f for f in flock['items'] if flockslug(f)==slugpath[0]]
    assert len(found)<2,"Duplicate children at flock"
    if not found:
        return None
    return flock_get(found[0],slugpath[1:])

def subflock(flock,name):
    "Flat get by name"
    return flock_get(flock,[flockslug(name)])

def get_flock_feeds(flock,respect_mutes=False,veteran=False):
    "Get all urls of feeds (leafs) in a flock tree. If respect_mutes, ignores mute feeds"
    feeds=set()
    if veteran and respect_mutes and flock.get('mute'):
        return feeds
    flocktype=flock.get('type')
    if flocktype=='feed':
        feeds.add(flock.get('url'))
    elif flocktype=='flock':
        feeds = feeds.union(*[get_flock_feeds(i,respect_mutes,True) for i in flock.get('items',[])])
    else:
        raise ValueError,'bad flock type %s for %s' % (`flocktype`,flock)
    return feeds

def flock_cachify(flock,feed_dict={},path=[]):
    """ To make things easier for templates and such, we add 2 items to each node
        cache_slug - an html-safe string representing the path to the node (e.g. for form field)
        cache_title - for feeds (flock only stores url) """
    flock['cache_slug']='_'.join(path)
    if flock.get('type')=='flock':
        for f in flock['items']:
            flock_cachify(f,feed_dict,path+[flockslug(f)])
    else: ## feed
        url = flock['url']
        flock['cache_title'] = feed_dict.get(url,{}).get('title',url)
    return flock

def flock_render(node,template):
    "Recursively render a flock"
    return template({
        'node':node,
        'items':[flock_render(i,template) for i in node.get('items',[])]})

### Feed functions
def feed_update(myfeed,otherfeed):
    modified = False
    for k in ['title','description','link','rtl']:
        if k=='link' or not myfeed.has_key(k): # link is always updated
            v=otherfeed.get(k,'').strip()
            if v and v != myfeed.get(k):
                myfeed[k]=v
                modified = True
    return modified

def get_feed_info(url,feed_dict=None):
        return dict((feed_dict or JsonDb(global_db,"feed")).get(url,{'title':url}),url=url)

import feedparser
def feed_fetch(url,cache_dict={},feed_dict={}):
    cache = cache_dict.get(url)
    if cache:
        if datetime2str(now())<cache.get('expires',''):
            # cache is still fresh
            return cache
        etag = cache.get('etag')
        modified = cache.get('modified')
    else:
        etag = modified = None
    parsed = feedparser.parse(url,etag=etag)
    status = parsed.get('status',500)
    if status != 304:
        print "Status {0} ({1} entries, bozo={2}) for {3}  (etag={4})".format(
            status,len(parsed.get('entries',[])),parsed.get('bozo_exception'),url,etag)
    if status == 200:
        # kludge because there are 3 ways for a feed to show modified time (if None counts as one)
        feed_modified = timestruct2str(parsed.get('updated_parsed',parsed.feed.get('updated_parsed',None)))
        etag = parsed.get('etag')
        feed_info = feed_dict.get(url,{})
        if feed_update(feed_info,{'title':parsed.feed.title,'link':parsed.feed.link}):
            feed_dict[url] = feed_info
        cache = {
            'expires':datetime2str(now()+seconds2delta(FEED_CACHE_TIMEOUT)),
            'modified':feed_modified,
            'etag':etag,
            'entries':[{'id':'i{0}'.format(hash((url,e.updated_parsed))),'title':e.title.strip() or '(untitled)', 'link':e.link,
                        'description':e.description, 'modified':timestruct2str(e.updated_parsed),
                        'friendly_time':timestruct2friendly(e.updated_parsed),
                        # add feed info in case we put the entry in a multi-channel timeline
                        'feed_url':url,'feed_title':feed_info['title'],
                        'feed_link':feed_info['link'],'feed_rtl':feed_info.get('rtl')
                       } for e in parsed.entries],
        }
        cache.update(feed_info)
        cache_dict[url] = cache
    return cache_dict[url] # might throw an error (e.g. if bad url)

### DB and JsonDb utilities

def import_feeds(feed_dict,import_dict):
    for k in import_dict.keys():
        if k.startswith('feed:'):
            url = k[len('feed:'):]
            feed = feed_dict.get(url,{})
            feed_update(feed,import_dict[k])
            feed_dict[url] = feed

def import_flock_file(db,filename):
    imported = json.load(file(filename))
    import_feeds(JsonDb(db,"feed"),imported)
    return imported.get('flock')

def get_root_or_public_flock(db):
    jdb = JsonDb(db)
    if jdb.has_key('flock'):
        root = jdb['flock']
    else:
        root = import_flock_file(db,DEFAULT_FLOCK_FILENAME)
        jdb['flock'] = root
    if global_account.is_logged_in():
        return root
    return subflock(root,'public') or {'type':'flock','title':'No public flock','items':[]}

def save_root_flock(db,flock):
    JsonDb(db)['flock'] = flock

def get_clipboard():
    return deepcopy(global_session.get('clipboard',{}))

def set_clipboard(node):
    global_session['clipboard'] = deepcopy(node)

### our single account manager
global_account = Sam(global_db,LOGIN_TIMEOUT_SECONDS)

### form validators
from urlparse import urlsplit
def valid_url(url):
    return urlsplit(url).scheme in ['http','https']

### Template forms
login_form = web.form.Form(
    web.form.Hidden('csrf_token'),
    web.form.Password("password",description="Password",tabindex=2), # tabindex after feed form
    web.form.Button('Login'))

logout_form = web.form.Form(
    web.form.Hidden('csrf_token'),
    web.form.Button('Logout'))

password_form = web.form.Form(
    web.form.Hidden("csrf_token"),
    web.form.Password("oldpass",description="Old password",tabindex=100,class_='focusme'),
    web.form.Password("newpass",
        web.form.Validator("must be at least 8 characters",lambda x:len(x)>=8),
        description="New password",tabindex=101,class_='focusme'),
    web.form.Password("newagain",description="New password again",tabindex=102),
    web.form.Button("Update password",tabindex=103),
    validators = [
        web.form.Validator("Passwords didn't match.", lambda i: i.newpass == i.newagain)
    ]
)

feed_form = web.form.Form(
    web.form.Hidden('csrf_token'),
    web.form.Textbox('url',web.form.Validator("Bad or missing url.",valid_url),description='Feed URL',
        size=42,tabindex=1,class_='focusme'), 
    web.form.Button('Go')
)

channel_form = web.form.Form(
    web.form.Hidden('csrf_token'),
    web.form.Hidden('url',web.form.Validator("Bad or missing url.",valid_url),description='Feed URL'),
    web.form.Button('Go')
)

channels_form = web.form.Form(
    web.form.Hidden('csrf_token'),
    web.form.Hidden('flock'),
    web.form.Dropdown('all',args=[('','skip hidden'),('yes','show hidden')],value='',description='All feeds?'),
    web.form.Button('Go')
)


EDIT_VERBS_ALWAYS = [ ('copy','Copy'), ]
EDIT_VERBS_UNLESS_ROOT = [ ('cut','Cut'), ]
EDIT_VERBS_IF_CLIPBOARD = [ ('paste','Paste after'), ]
EDIT_VERBS_FOR_FLOCK_IF_CLIPBOARD = [ ('prepend','Paste inside'), ]
EDIT_VERBS_NOT_IN_MENU = [ ('hide','Hide'), ('show','Show'), ('clearcb','Clear'), ]

# Used for validation
EDIT_VERBS_ALL = deepcopy(EDIT_VERBS_ALWAYS) + deepcopy(EDIT_VERBS_UNLESS_ROOT) + deepcopy(EDIT_VERBS_IF_CLIPBOARD)
EDIT_VERBS_ALL += deepcopy(EDIT_VERBS_FOR_FLOCK_IF_CLIPBOARD) + deepcopy(EDIT_VERBS_NOT_IN_MENU)

edit_form = web.form.Form(web.form.Hidden('csrf_token'), web.form.Hidden('subject'),
    web.form.Dropdown('verb',args=EDIT_VERBS_ALL,value='copy'),
    web.form.Button('Do'))

mini_edit_form = web.form.Form(web.form.Hidden('csrf_token'), web.form.Hidden('subject'), web.form.Hidden('verb'))

### Rendering helpers
from urllib2 import quote as urlquote

def custom_edit_form(node):
    "returns edit_form with custom menu according to node type and clipboard. Also adds csrf_token"
    form = edit_form()
    form.fill(csrf_token=csrf_token(),subject=node.get('cache_slug',''))
    menu = deepcopy(EDIT_VERBS_ALWAYS)
    if node.get('cache_slug'):
        menu += deepcopy(EDIT_VERBS_UNLESS_ROOT)
    if get_clipboard():
        menu += deepcopy(EDIT_VERBS_IF_CLIPBOARD)
        if node.get('type') == 'flock':
            menu += deepcopy(EDIT_VERBS_FOR_FLOCK_IF_CLIPBOARD)
    form.inputs[2].args = menu
    return form

def form_errors(form):
    return ['{0}: {1}'.format(i.description,i.note) for i in form.inputs if i.note]

def get_feed_render_info(url,feed_dict=None):
        return dict(get_feed_info(url,feed_dict),
            button_html='<form class="inline-form noborder" method="post" action="{0}">{1}</form>'.format(
                web.url('/channel'), urlquote(channel_form({'csrf_token':csrf_token(),'url':url}).render_css())))

import jinja2util
def urlize(s):
    return jinja2util.urlize(s,nofollow=True)


### Render objects
render_globals = {
    'ctx':web.ctx, # handy environment info
    'account':global_account,
    'flashes':pop_flashed_messages,
    'urlquote':urlquote,
    'login_form':login_form,
    'feed_form':feed_form,
    'logout_form':logout_form,
    'channel_form':channel_form,
    'channels_form':channels_form,
    'custom_edit_form':custom_edit_form,
    'mini_edit_form':mini_edit_form,
    'csrf_token':csrf_token # to enable csrf_token() hidden fields
}

render = web.template.render('templates',base='layout',globals=render_globals)

# baseless_render doesn't use a page layout wrapper
# for partial render, xml, etc.
baseless_render = web.template.render('templates',globals=render_globals)

### JSON views

from exceptions import Exception

class view_api_channel:
    def PUT(self):
        web.header('Content-Type', 'application/json')
        url = web.input().get('url')
        return json.dumps(feed_fetch(url,JsonDb(global_db,"cache"),JsonDb(global_db,"feed")))
    def GET(self): ### temporary
        return self.PUT()

### Views
class view_index:
    def GET(self):
        feed_dict=JsonDb(global_db,"feed")
        flock = flock_cachify(get_root_or_public_flock(global_db),feed_dict)
        rendered = flock_render(flock,baseless_render.flocknode)
        cb = get_clipboard()
        cb = cb and flock_render(flock_cachify(cb,feed_dict),baseless_render.clipboardnode)
        return render.index({
            'flock':flock,'rendered':rendered,'clipboard':cb})
    @csrf_protected
    def POST(self):
        if not global_account.is_logged_in():
            flash("You're not logged in. You can't {0}.").format(web.input.get('verb','modify information'))
            raise web.seeother('/')
        form=edit_form()
        if not form.validates():
            for e in form_errors(form):
                flash(e)
            raise web.seeother('/')
        root = get_root_or_public_flock(global_db)
        scrollto = form.d.subject
        feed_dict=JsonDb(global_db,"feed")
        if form.d.subject:
            slugpath = form.d.subject.split('_')
            node = flock_get(root,slugpath)
        else:
            slugpath = '[]'
            node = root
            scrollto = 'f-root'
        if not node:
            flash('Item not found. This can happen when you logout, edit your flock, etc.')
            raise web.seeother('/')
        ### Do the verb
        if form.d.verb == 'hide': # Verb: Hide
            node['mute']=True
            save_root_flock(global_db,root)
            flash('Marked {0} as hidden'.format(node['type']))
        elif form.d.verb == 'show': # Verb: Show
            node['mute']=False
            save_root_flock(global_db,root)
            flash('Marked {0} as visible'.format(node['type']))
        elif form.d.verb == 'copy': # Verb: Copy
            set_clipboard(node)
            scrollto = None
            flash('Copied {0} to clipboard'.format(node['type']))
        elif form.d.verb == 'cut': # Verb: Cut
            if not slugpath:
                flash("can't cut root flock.")
            else:
                parent = flock_get(root,slugpath[:-1])
                if not parent:
                    flash("Item not found (logout, rename, etc.). Please try again.")
                else:
                    set_clipboard(node)
                    flash('Moved {0} to clipboard'.format(node['type']))
                    parent['items'].remove(node)
                    save_root_flock(global_db,root)
                    scrollto = None
        elif form.d.verb == 'clearcb': # Verb: Clear
            set_clipboard(None)
            scrollto = None
            flash('Clipboard was cleared.')
        elif form.d.verb == 'paste': # Verb: Paste after
            if not slugpath:
                flash("can't paste after root flock")
            cb = flock_cachify(get_clipboard(),feed_dict)
            if not cb:
                flash("Can't paste from empty clipboard")
            else:
                parent = flock_get(root,slugpath[:-1])
                if not parent:
                    flash("Item not found (logout, rename, etc.). Please try again.")
                elif subflock(parent,cb.get('url',cb.get('title'))):
                    flash("Can't paste duplicate item.")
                else:
                    parent['items'].insert(1+parent['items'].index(node),cb)
                    save_root_flock(global_db,root)
                    flash("Pasted.")
        elif form.d.verb == 'prepend': # Verb: Paste inside
            cb = flock_cachify(get_clipboard(),feed_dict)
            if not cb:
                flash("Can't paste from empty clipboard")
            elif node.get('type')!='flock':
                flash("Can't paste inside a single food.")
            elif subflock(node,cb.get('url',cb.get('title'))):
                flash("Can't paste duplicate item.")
            else:
                node['items'].insert(0,cb)
                save_root_flock(global_db,root)
                flash("Pasted.")
        else: # Unknown verb
            flash('Bug: unknown verb {0}'.format(form.d.verb))
            raise web.seeother('/')
        flock_cachify(root,feed_dict)
        rendered = flock_render(root,baseless_render.flocknode)
        cb = get_clipboard()
        cb = cb and flock_render(flock_cachify(cb,feed_dict),baseless_render.clipboardnode)
        return render.index({
            'flock':root,'rendered':rendered,'clipboard':cb,'scrollto':scrollto})

class view_channel:
    def GET(self):
        flash('Please select a feed to view.')
        return web.seeother('/')
    @csrf_protected
    def POST(self):
        form = channel_form()
        if not form.validates():
            for e in form_errors(form):
                flash(e)
            raise web.seeother('/')
        feed_info = get_feed_render_info(form.d.url)
        title = feed_info['title']
        description = urlize(feed_info.get('description',''))
        return render.timeline({'title':u'Channel: {0}'.format(title),'description':description,'feeds':[feed_info],
            'max_page_entries':MAX_PAGE_ENTRIES,'expand_all_entries':True,
            'max_feed_entries':MAX_SINGLE_FEED_ENTRIES,'feed_refresh_seconds':FEED_REFRESH_SECONDS})

class view_channels:
    def GET(self):
        flash('Please select a flock to view.')
        return web.seeother('/')
    @csrf_protected
    def POST(self):
        form = channels_form()
        if not form.validates():
            for e in form_errors(form):
                flash(e)
        flock = get_root_or_public_flock(global_db)
        if form.d.flock:
            flock = flock_get(flock,form.d.flock.split('_'))
        if not flock:
            flash('Flock not found. This can happen when you logout, edit your flock, etc.')
            raise web.seeother('/')
        feeds = map(get_feed_render_info,get_flock_feeds(flock,respect_mutes=not form.d.all))
        title = flock['title']
        description = urlize(flock.get('description',''))
        return render.timeline({'title':u'Channels: {0}'.format(title),'description':description,'feeds':feeds,
            'max_page_entries':MAX_PAGE_ENTRIES,'expand_all_entries':False,
            'max_feed_entries':MAX_FLOCK_FEED_ENTRIES,'feed_refresh_seconds':FEED_REFRESH_SECONDS})


class view_login:
    def GET(self):
        if global_account.is_new(): # can't login to an empty nest
            flash("Can't login to an empty nest.")
            raise web.seeother('/')
        form = login_form()
        form.fill(csrf_token=csrf_token(),password='')
        return render.login({'form':form})
    @csrf_protected
    def POST(self):
        form = login_form()
        if form.validates() and global_account.login(form.d.password):
            flash('Welcome.')
            raise web.seeother('/')
        form.fill(csrf_token=csrf_token(),password='')
        flash('Wrong password. Please try again.')
        return render.login({'form':form})

class view_logout:
    @csrf_protected
    def POST(self):
        global_account.logout()
        flash('Goodbye.')
        raise web.seeother('/')

class view_set_password:
    def GET(self):
        if not (global_account.is_logged_in() or global_account.is_new()):
            flash("You're not logged in. Can't change your password.")
            raise web.seeother('/')
        form = password_form()
        form.fill(csrf_token=csrf_token(),oldpass='',newpass='',newagain='')
        if global_account.is_new():
            # Hide oldpass field
            form.inputs[1].attrs['style'] = 'display:none'
            form.inputs[1].description = ''
        return render.set_password({'form':form})
    @csrf_protected
    def POST(self):
        form=password_form()
        if form.validates():
            if global_account.change_password(form.d.oldpass,form.d.newpass):
                flash("Your password was saved.")
                raise web.seeother('/')
            flash("Incorrect password. Try again.")
        form.fill(csrf_token=csrf_token(),oldpass='',newpass='',newagain='')
        if global_account.is_new():
            form.inputs[0].attrs['style'] = 'display:none'
            form.inputs[0].description = ''
        return render.set_password({'form':form})

if __name__ == "__main__":
   app.run()
