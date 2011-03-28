# -*- coding: utf-8 -*-

### config
DEBUG = True
DEBUG_SQL = False
DB_FILENAME = 'flocks.db'
LOGIN_TIMEOUT_SECONDS = 3600 # 1 hour.
FEED_REFRESH_SECONDS = 120 # delay (for each feed) between javascript fetches
FEED_CACHE_TIMEOUT = 180 # Some feeds are etag and last-modified deaf/dumb
MAX_PAGE_ENTRIES = 50
MAX_SINGLE_FEED_ENTRIES = 50
MAX_FLOCK_FEED_ENTRIES = 10
HTTP_PORT = 6378 # "Nest" on phone keyboard
PROFILE_DEFAULTS = {
    "title":"My nest",
    "description":"IM IN UR SOSHAL. More about me: https://secure.wikimedia.org/wikipedia/en/wiki/Human",
    "link":"http://example.com/mynest"
}
DEFAULT_FLOCK_FILENAME = 'default_flock.js'
NEST_TEMPLATES = 'default-nest-theme'
NEST_OUTPUT_FOLDER = 'nest' # under static/ (so that we can preview it)
NEST_FEED_FILENAME = 'rss.xml'
###

import web
from sys import argv
argv[1:] = ['127.0.0.1:{0}'.format(HTTP_PORT)] # That's how you set ip:port in web.py ;) 
web.config.debug = DEBUG
web.config.debug_sql = DEBUG_SQL # This only works for a tweaked version of web.py (see README)

urls = (
    "/", "view_index",
    "/nest", "view_nest",
    "/delpost", "view_delpost",
    "/publish", "view_publish",
    "/channel", "view_channel",
    "/channels", "view_channels",
    "/newflock", "view_newflock",
    "/editflock", "view_editflock",
    "/editfeed", "view_editfeed",
    "/login","view_login",
    "/logout","view_logout",
    "/settings","view_settings",
    "/api/channel","view_api_channel",
    "/favicon.ico","view_favicon",
)

app = web.application(urls, globals())
global_db = web.database(dbn='sqlite',db=DB_FILENAME)

#### Session/debug tweak from http://webpy.org/cookbook/session_with_reloader
if web.config.get('_session') is None:
    global_session = web.session.Session(app, web.session.DiskStore('sessions'))
    web.config._session = global_session
else:
    global_session = web.config._session

#### General purpose imports and functions
from copy import deepcopy
try:
    import simplejson as json
except:
    import json
from exceptions import Exception, KeyError, SyntaxError, ValueError
from urllib2 import quote as urlquote

def hard_strip(s):
    """Strips strings. Anything else becomes ''"""
    try: return s.strip()
    except AttributeError: return ''

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
from UserDict import DictMixin

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
        self.db.query('create table if not exists {0} (key text unique,value blob)'.format(self.table))
        self.update(kwargs)
    def keys(self):
        return [r.key for r in self.db.select(self.table,what='key')]
    def _get(self,key):
        return list(self.db.select(self.table,what='value',where='key=$k',vars={'k':key}))
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
        self.db.delete(self.table,where='key=$k',vars={'k':key})
    def __setitem__(self,key,value):
        if self.has_key(key):
            self.db.update(self.table,where='key=$k',vars={'k':key},value=json.dumps(value))
        else:
            self.db.insert(self.table,key=key,value=json.dumps(value))
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
    check_password(password)
    get_profile() - returns dict with nest title, etc.
Public methods that start with _ (can't be called from a template):
    _change_password(oldpass,newpass) - oldpass is ignored if is_new()
    _set_profile(dict)"""
    profile_keys = ['title','description','link']
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
    
    def check_password(self,password):
        import hmac
        return hmac.new(self.jdb['key'].decode('hex'),password).hexdigest()==self.jdb['passhash']

    def login(self,password):
        if self.check_password(password):
            self._renew_lease()
            return True
        self.logout()
        return False

    def logout(self):
        if global_session.has_key('sam_expires'):
            del global_session['sam_expires']

    def _change_password(self,oldpass,newpass):
        "oldpass is ignored if self.is_new()"
        if self.is_new() or self.check_password(oldpass):
            import hmac
            from os import urandom
            key = urandom(20)
            self.jdb.update({
                'key':key.encode('hex'),
                'passhash':hmac.new(key,newpass).hexdigest()})
            self._renew_lease()
            return True
        return False
    
    def get_profile(self):
        p = {}
        for k in self.profile_keys:
            p[k]=self.jdb.get(k,PROFILE_DEFAULTS[k])
        return p

    def _set_profile(self,profile):
        for k in self.profile_keys:
            if profile.has_key(k):
                self.jdb[k]=profile[k]
    
### Flock functions
def flockslug(obj):
    "Receives a name string for a flock node (dict). Returns an html-safe slug. Case insensitive."
    if type(obj)==type({}):
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

def get_all_feed_titles(feed_dict=None):
    feed_dict = feed_dict or JsonDb(global_db,"feed")
    res = set()
    for k,v in feed_dict.items():
        res.add(v['title'].lower())
    return res

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

def flock_decachify(node):
    for k in ['cache_slug','cache_title']:
        try:
            del node[k]
        except KeyError:
            pass
    for i in node.get('items',[]):
        flock_decachify(i)
    return node

def flock_render(node,template):
    "Recursively render a flock"
    return template({
        'node':node,
        'items':[flock_render(i,template) for i in node.get('items',[])]})

### Feed functions
def feed_info_merge(myfeed,otherfeed):
    modified = False
    for k in ['title','description','link','rtl']:
        if k=='link' or not myfeed.has_key(k): # link is always updated
            v = otherfeed.get(k)
            v = k=='rtl' and not not v or hard_strip(v) # coerce to boolean or string
            if v and v!=myfeed.get(k):
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
    if status!=304:
        print "Status {0} ({1} entries, bozo={2}) for {3}  (etag={4})".format(
            status,len(parsed.get('entries',[])),parsed.get('bozo_exception'),url,etag)
    if status==200:
        # kludge because there are 3 ways for a feed to show modified time (if None counts as one)
        feed_modified = timestruct2str(parsed.get('updated_parsed',parsed.feed.get('updated_parsed',None)))
        etag = parsed.get('etag')
        feed_info = feed_dict.get(url,{})
        if feed_info_merge(feed_info,{'title':parsed.feed.title,'link':parsed.feed.link}):
            feed_dict[url] = feed_info
        cache = {
            'expires':datetime2str(now()+seconds2delta(FEED_CACHE_TIMEOUT)),
            'modified':feed_modified,
            'etag':etag,
            'entries':[{'guid':e.get('id','#g'.join((e.link,str(hash((url,e.title.strip().lower(),e.link)))))),
                        'title':e.title.strip() or '(untitled)', 'link':e.link,
                        'description':e.get('description',''), 'modified':timestruct2str(e.updated_parsed),
                        'friendly_time':timestruct2friendly(e.updated_parsed),
                        # add feed info in case we put the entry in a multi-channel timeline
                        'feed_url':url,'feed_title':feed_info['title'],
                        'feed_link':feed_info['link'],'feed_rtl':feed_info.get('rtl')
                       } for e in parsed.entries],
        }
        for e in cache['entries']: e['id'] = 'egg{0}'.format(hash(e['guid'])) # Used for DOM anchors
        cache.update(feed_info)
        cache_dict[url] = cache
    return cache_dict[url] # might throw an error (e.g. if bad url)

### Nest functions
def get_outbox(db):
    entries = JsonDb(db).get('outbox',[])
    profile = global_account.get_profile()
    feed_link = profile['link']
    return [dict(e, link=e['link'] or '/#'.join((feed_link,e['id']))) for e in entries]
    
def set_outbox(db,outbox): JsonDb(db)['outbox'] = outbox

def add_post(db,title,description='',link=''):
    guid = '/#g'.join((global_account.get_profile()['link'],str(hash((title.strip().lower(),link)))))
    item_anchor = 'egg{0}'.format(hash(guid))
    jdb = JsonDb(db)
    entry = { 'guid':guid, 'id':item_anchor, 'modified':now().ctime(),
        'title':title.strip(),'description':description.strip(),'link':link }
    jdb['outbox'] = [entry] + jdb.get('outbox',[])
    return entry

def del_post(db,post_id):
    jdb = JsonDb(db)
    jdb['outbox'] = filter(lambda e:e['id']!=post_id,jdb.get('outbox',[]))

def sync_nests(hard=False):
    feed_url = '/'.join((global_account.get_profile()['link'],NEST_FEED_FILENAME))
    cache = JsonDb(global_db,"cache")
    feeds = JsonDb(global_db,"feed")
    if hard:
        for jdb in [feeds,cache]:
            try: # Make sure we get everything fresh
                del jdb[feed_url]
            except KeyError:
                pass
    try:
        nest = feed_fetch(feed_url,cache,feeds)
    except:
        nest = {'entries':[]}
    guids = set().union(*[set([e['guid']]) for e in nest['entries']])
    print guids
    outbox = filter(lambda e:not e['guid'] in guids,get_outbox(global_db))
    set_outbox(global_db,outbox)
    return nest['entries'],outbox

def publish_nest(db):
    profile = global_account.get_profile()
    nest_link = profile['link']
    feed_url = nest_link and '/'.join((nest_link,NEST_FEED_FILENAME)) or ''
    nest,outbox=sync_nests()
    entries = outbox+nest
    file('static/{0}/index.html'.format(NEST_OUTPUT_FOLDER),'w').write(
        str(nest_render.nest({'entries':entries,'feed_url':feed_url})))
    file('static/{0}/{1}'.format(NEST_OUTPUT_FOLDER,NEST_FEED_FILENAME),'w').write(
        str(baseless_nest_render.rss(dict(profile,nest_link=nest_link,modified=datetime2str(now()),entries=entries))))
    ###@@@ To be continued...

### Various db/clipboard access functions

def get_root_or_public_flock(db):
    jdb = JsonDb(db)
    if jdb.has_key('flock'):
        root = jdb['flock']
    else: # No try/except here. If default file not found or corrupt, don't come crying :)
        sanity = import_flockshare(json.load(file(DEFAULT_FLOCK_FILENAME)))
        assert not sanity['errors'] and sanity['values'],"Invalid flock file {0}".format(DEFAULT_FLOCK_FILENAME)
        root = sanity['values'][0]
        jdb['flock'] = root
    if global_account.is_logged_in():
        return root
    return subflock(root,'flockroll') or {'type':'flock','title':'User has no public FlockRoll','items':[]}

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
def valid_url(url): return urlsplit(url).scheme in ['http','https']
def valid_url_or_empty(url): return not url or valid_url(url)

### Template forms
login_form = web.form.Form(
    web.form.Hidden('csrf_token'),
    web.form.Password("password",description="Password",tabindex=2,class_='focusme'), # tabindex after feed form
    web.form.Button('Login',tabindex=3))

logout_form = web.form.Form(
    web.form.Hidden('csrf_token'),
    web.form.Button('Logout'))

settings_form = web.form.Form(
    web.form.Hidden("csrf_token"),
    web.form.Password("oldpass",description="Current password",tabindex=100,class_='focusme'),
    web.form.Password("newpass",
        web.form.Validator("must be at least 8 characters",lambda x:not x or len(x)>=8),
        description="New password",tabindex=101,class_='focusme'),
    web.form.Password("newagain",description="New password again",tabindex=102),
    web.form.Textbox("title",web.form.notnull,description="Nest's name",size=23,tabindex=103),
    web.form.Textbox("description",description="Description/bio",size=80,tabindex=104),
    web.form.Textbox("link",web.form.Validator("Bad or missing url",valid_url),
        description="Nest's url",size=80,tabindex=105),
    web.form.Button("Save",tabindex=106),
    validators = [
        web.form.Validator("Passwords didn't match.", lambda i: i.newpass==i.newagain)
    ]
)

post_form = web.form.Form(
    web.form.Hidden("csrf_token"),
    web.form.Textbox("title",web.form.notnull,description="Title",size=80,tabindex=100,class_='focusme'),
    web.form.Textbox("link",web.form.Validator("Invalid url",valid_url_or_empty),
        description="Link",size=80,tabindex=101),
    web.form.Textarea("description",description="Body",rows=5,cols=80,tabindex=102),
    web.form.Button("Post",tabindex=103),
)

delpost_form = web.form.Form( web.form.Hidden("csrf_token"), web.form.Hidden("post_id"), web.form.Button("Delete"))
publish_form = web.form.Form( web.form.Hidden("csrf_token"), web.form.Button("Publish"))

feed_form = web.form.Form(
    web.form.Hidden('csrf_token'),
    web.form.Textbox('url',web.form.Validator("Bad or missing url.",valid_url),description='Feed URL',
        size=23,tabindex=1,class_='focusme'), 
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
    web.form.Dropdown('all',args=[('','Normal view'),('yes','Show muted')],value='',description='All feeds?'),
    web.form.Button('Go')
)

edit_feed_form = web.form.Form(
    web.form.Hidden('csrf_token'),
    web.form.Hidden('url'),
    web.form.Textbox('title',web.form.notnull,description='Feed name', size=23, tabindex=100,class_='focusme'),
    web.form.Textbox('description',description='Description',size=80,tabindex=101,value=''),
    web.form.Dropdown('direction',description='Direction',args=[
        ('ltr','Left to right'), ('rtl','Right to left') ],value='ltr',tabindex=102),
    web.form.Button('Update feed',tabindex=103)
)

edit_flock_form = web.form.Form(
    web.form.Hidden('csrf_token'),
    web.form.Hidden('flock'),
    web.form.Hidden('show_mutes_tweak'),
    web.form.Textbox('title',web.form.notnull,description='Flock name', size=23, tabindex=100,class_='focusme'),
    web.form.Textbox('description',description='Description',size=80,tabindex=101,value=''),
    web.form.Button('Save',tabindex=103)
)

# Edit form menu items
EDIT_VERBS_ALWAYS = [ ('copy','Copy'), ]
EDIT_VERBS_UNLESS_ROOT = [ ('cut','Cut'), ]
EDIT_VERBS_IF_CLIPBOARD_UNLESS_ROOT = [ ('paste','Paste after'), ]
EDIT_VERBS_FOR_FLOCK = [ ('export','Share'), ]
EDIT_VERBS_FOR_FLOCK_IF_CLIPBOARD = [ ('prepend','Paste inside'), ]
# These verbs are here for form validation only
EDIT_VERBS_NOT_IN_MENU = [ ('mute','Mute'), ('show','Show'),
    ('clearcb','Clear'), ('addfeed', 'Add feed'), ('addflock', 'Add Flock'), ('import', 'Import FlockShare'), ]

# Used for validation
EDIT_VERBS_ALL = deepcopy(EDIT_VERBS_ALWAYS) + deepcopy(EDIT_VERBS_UNLESS_ROOT)
EDIT_VERBS_ALL += deepcopy(EDIT_VERBS_IF_CLIPBOARD_UNLESS_ROOT) + deepcopy(EDIT_VERBS_FOR_FLOCK) 
EDIT_VERBS_ALL += deepcopy(EDIT_VERBS_FOR_FLOCK_IF_CLIPBOARD) + deepcopy(EDIT_VERBS_NOT_IN_MENU)

edit_form = web.form.Form(web.form.Hidden('csrf_token'),
    web.form.Hidden('subject'),
    web.form.Dropdown('verb',args=EDIT_VERBS_ALL,value='copy'),
    web.form.Button('Do'))

mini_edit_form = web.form.Form(web.form.Hidden('csrf_token'), web.form.Hidden('subject'), web.form.Hidden('verb'))

import_flockshare_form = web.form.Form(
    web.form.Hidden('csrf_token'),
    web.form.Hidden('verb',value='import'), # for some reason we need to say it again at form.fill() ?!?
    web.form.Textarea('subject',description='FlockShare',rows=5,cols=60,class_='flockshare',tabindex=200), 
    web.form.Button('Import FlockShare',tabindex=201)
)

### Rendering helpers

def custom_edit_form(node):
    "returns edit_form with custom menu according to node type and clipboard. Also adds csrf_token"
    form = edit_form()
    form.fill(csrf_token=csrf_token(),subject=node.get('cache_slug',''))
    menu = deepcopy(EDIT_VERBS_ALWAYS)
    if node.get('cache_slug'):
        menu += deepcopy(EDIT_VERBS_UNLESS_ROOT)
        if get_clipboard():
            menu += deepcopy(EDIT_VERBS_IF_CLIPBOARD_UNLESS_ROOT)
    if node.get('type')=='flock':
        if get_clipboard():
            menu += deepcopy(EDIT_VERBS_FOR_FLOCK_IF_CLIPBOARD)
        menu += deepcopy(EDIT_VERBS_FOR_FLOCK)
    form.inputs[2].args = menu
    return form

def form_errors(form):
    return ['{0}: {1}'.format(i.description,i.note) for i in form.inputs if i.note]

def get_feed_render_info(url,feed_dict=None):
        return dict(get_feed_info(url,feed_dict),
            button_html='<form class="inline-form noborder" method="post" action="{0}">{1}</form>'.format(
                web.url('/channel'), urlquote(channel_form({'csrf_token':csrf_token(),'url':url}).render_css())))

import jinja2util
def urlize(s,nofollow=True):
    return jinja2util.urlize(s,nofollow=nofollow,trim_url_limit=32)


### Render objects
render_globals = {
    'ctx':web.ctx, # handy environment info
    'account':global_account,
    'flashes':pop_flashed_messages,
    'urlquote':urlquote,
    'login_form':login_form,
    'delpost_form':delpost_form,
    'publish_form':publish_form,
    'feed_form':feed_form,
    'logout_form':logout_form,
    'channel_form':channel_form,
    'channels_form':channels_form,
    'custom_edit_form':custom_edit_form,
    'mini_edit_form':mini_edit_form,
    'urlize':urlize,
    'csrf_token':csrf_token # to enable csrf_token() hidden fields
}

render = web.template.render('templates',base='layout',globals=render_globals)

# baseless_render doesn't use a page layout wrapper
# for partial render, xml, etc.
baseless_render = web.template.render('templates',globals=render_globals)

# Templates for the static nest
nest_render = web.template.render(NEST_TEMPLATES,base='nest-layout',globals=render_globals)
baseless_nest_render = web.template.render(NEST_TEMPLATES,globals=render_globals)

### FlockShare Import

def add_sanities(a,b):
    """Combines 2 dictionaries returned by sanitize_node()""" 
    return {
        'values':a['values']+b['values'],
        'feeds':a['feeds'].union(b['feeds']),
        'errors':a['errors']+b['errors'],
    }

def sanitizer_error(message,path,here='?'):
    """Returns a trivial-yet valid 'sanity dict' containing an error message"""
    return {'values':[],'feeds':set(),'errors':['{0} at "{1}/{2}"'.format(message,'/'.join(path),here)]}

def sanitize_node(node,path=[]):
    """Accepts an [alleged] flock or feed node, and returns a 'sanity' dict with:
       values - a list with a element (empty if there's a top level error)
       feeds - a set of all feed urls in the sanitized node
       errors - a list of error strings"""
    if type(node)!=type({}): return sanitizer_error('Not a dictionary',path)
    nodetype = node.get('type','baaad')
    if nodetype=='feed':
        url = hard_strip(node.get('url'))
        if not valid_url(url): return sanitizer_error('Invalid feed URL',path)
        value = {'type':'feed','url':url}
        value['mute'] = not not node.get('mute',False)
        return {'values':[value],'feeds':set([url]),'errors':[]}
    elif nodetype=='flock':
        title = hard_strip(node.get('title'))
        if not title: return sanitizer_error('No title for flock',path)
        value = {'type':'flock','title':title,
                 'description':hard_strip(node.get('description')), 'mute':not not node.get('mute')}
        items = node.get('items')
        if type(items)!=type([]): return sanitizer_error('Invalid flock item list',path,title)
        sanities = reduce(add_sanities,[sanitize_node(i,path+[title]) for i in items],
            {'values':[],'feeds':set(),'errors':[]})
        value['items'] = sanities['values']
        return {'values':[value],'feeds':sanities['feeds'],'errors':sanities['errors']}
    else:
        return sanitizer_error('Invalid node type',path)

def import_flockshare(fs,feed_dict=None):
    feed_dict = feed_dict or JsonDb(global_db,"feed")
    sanity = sanitize_node(fs.get('flock'))
    if not sanity['values']: return sanity
    feed_titles = get_all_feed_titles(feed_dict)
    feed_urls = set(feed_dict.keys())
    feeds = fs.get('feeds')
    for url in sanity['feeds']:
        if url in feed_urls: continue
        feed = feeds.get(url)
        if not feed: continue
        title = hard_strip(feed.get('title',url))
        if title.lower() in feed_titles:
            title = u' '.join(title,datetime2str(now()).replace('T',' ')) # the T messes up rtl :)
            sanity['errors'].append(u'Renamed feed "{0}" to avoid conflicts'.format(feed['title']))
        value = {'title':title, 'description':hard_strip(feed.get('description')),'rtl':(not not feed.get('rtl'))}
        link = hard_strip(feed.get('link'))
        if link:
            if valid_url(link):
                value['link'] = link
            else:
                sanity['errors'].append(u'Invalid link for feed "{0}"'.format(title))
        feed_dict[url] = value
        feed_titles.add(title)
        feed_urls.add(url)
    return sanity

### FlockShare export

def export_flockshare(flock,feed_dict=None):
    feed_dict = feed_dict or JsonDb(global_db,"feed")
    fs = {'flock':flock_decachify(flock),'feeds':{}}
    for url in get_flock_feeds(flock):
        fs['feeds'][url] = get_feed_info(url,feed_dict)
    return fs

##### Views #####

### JSON views


class view_api_channel:
    def POST(self):
        web.header('Content-Type', 'application/json')
        url = web.input().get('url')
        return json.dumps(feed_fetch(url,JsonDb(global_db,"cache"),JsonDb(global_db,"feed")))

### HTML views
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
            flash("You're not logged in. {0} refused.".format(web.input().get('verb','operation')))
            raise web.seeother('/')
        form=edit_form()
        if not form.validates():
            for e in form_errors(form):
                flash(e)
            raise web.seeother('/')
        root = get_root_or_public_flock(global_db)
        scrollto = form.d.subject
        feed_dict=JsonDb(global_db,"feed")
        if form.d.verb in ['clearcb','addfeed','addflock','import']: # verbs where subject is not a flock
            scrollto = None
        else:
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
        if form.d.verb=='mute': # Verb: Mute
            node['mute']=True
            save_root_flock(global_db,root)
            flash('Marked {0} as hidden'.format(node['type']))
        elif form.d.verb=='show': # Verb: Show
            node['mute']=False
            save_root_flock(global_db,root)
            flash('Marked {0} as visible'.format(node['type']))
        elif form.d.verb=='copy': # Verb: Copy
            set_clipboard(node)
            flash('Copied {0} to clipboard'.format(node['type']))
        elif form.d.verb=='cut': # Verb: Cut
            scrollto = None
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
        elif form.d.verb=='paste': # Verb: Paste after
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
        elif form.d.verb=='prepend': # Verb: Paste inside
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
        elif form.d.verb=='clearcb': # Verb: Clear
            set_clipboard(None)
            flash('Clipboard was cleared.')
        elif form.d.verb=='addfeed': # Verb: Add feed
            if valid_url(form.d.subject):
                set_clipboard({'type':'feed','url':form.d.subject})
                flash('Feed was copied to clipboard.')
            else:
                flash("Can't add feed. Invalid URL: '{0}").format(form.d.subject)
        elif form.d.verb=='export': # Verb: Export FlockShare
            return render.flockshare({'title':node['title'],'flockshare':json.dumps(export_flockshare(node))})
        elif form.d.verb=='import': # Verb: Export FlockShare
            try:
                node = json.loads(form.d.subject)
            except ValueError:
                node = None
            if type(node)!=type({}):
                flash("Invalid FlockShare syntax")
                raise web.seeother('/')
            sanity = import_flockshare(node,feed_dict)
            for e in sanity['errors'][:5]:
                flash(e)
            if len(sanity['errors'])>5:
                flash('More errors...')
            if sanity['values']:
                set_clipboard(sanity['values'][0])
                flash('Imported into clipboard')
            else:
                flash('Nothing was imported')
            raise web.seeother('/')
        else: # Unknown verb
            flash('Bug: unknown verb {0}'.format(form.d.verb))
            raise web.seeother('/')
        flock_cachify(root,feed_dict)
        rendered = flock_render(root,baseless_render.flocknode)
        cb = get_clipboard()
        cb = cb and flock_render(flock_cachify(cb,feed_dict),baseless_render.clipboardnode)
        return render.index({
            'flock':root,'rendered':rendered,'clipboard':cb,'scrollto':scrollto})

class view_nest:
    def GET(self):
        if not global_account.is_logged_in():
            flash("You're not logged in. Can't view_nest.")
            raise web.seeother('/')
        form = post_form()
        form.fill(csrf_token=csrf_token())
        local_link = 'http://127.0.0.1:{0}/static/{1}'.format(HTTP_PORT,NEST_OUTPUT_FOLDER)
        nest,outbox = sync_nests(hard=True)
        return render.nest({'form':form,'nest':nest,'outbox':outbox,'local_link':local_link})
    @csrf_protected
    def POST(self):
        if not global_account.is_logged_in():
            flash("You're not logged in. Can't post.")
            raise web.seeother('/')
        form = post_form()
        if form.validates():
            entry = add_post(global_db,form.d.title,form.d.description,form.d.link)
            flash('Posted to local outbox.')
            raise web.seeother('/nest')
        else:
            form.inputs[0].set_value(csrf_token())
            local_link = 'http://127.0.0.1:{0}/static/{1}'.format(HTTP_PORT,NEST_OUTPUT_FOLDER)
            nest,outbox = sync_nests(hard=True)
            return render.nest({'form':form,'nest':nest,'outbox':outbox,'local_link':local_link})

class view_delpost:
    def GET(self):
        raise web.seeother('/nest')
    @csrf_protected
    def POST(self):
        form = delpost_form()
        if form.validates():
            del_post(global_db,form.d.post_id)
            flash('Post deleted.')
        raise web.seeother('/nest')

class view_publish:
    def GET(self):
        raise web.seeother('/nest')
    @csrf_protected
    def POST(self):
        form = publish_form()
        if form.validates():
            publish_nest(global_db)
            flash('Published to local nest. Refresh after you upload to the online site, and outbox should disappear.')
        raise web.seeother('/nest')

class view_editfeed:
    def GET(self):
        flash("Sorry. Stale browser page. Please try again whatever you were doing.")
        raise web.seeother('/')
    @csrf_protected
    def POST(self):
        if not global_account.is_logged_in():
            flash("You're not logged in. Can't edit feed.")
            raise web.seeother('/')
        form = edit_feed_form()
        err = False
        if form.validates():
            feed_dict=JsonDb(global_db,"feed")
            url = form.d.url
            rtl = form.d.direction=='rtl'
            title = form.d.title.strip()
            feed_info = get_feed_info(url,feed_dict)
            if title.lower()!=feed_info['title'].lower() and title.lower() in get_all_feed_titles():
                title = u' '.join(title,datetime2str(now()).replace('T',' ')) # the T messes up rtl :)
                flash('Warning! Feed was renamed to avoid conflicts!')
            feed_info.update(title=title,rtl=rtl,description=form.d.description)
            feed_dict[url] = feed_info
            try: # feed's cache is no longer relevant
              del JsonDb(global_db,"cache")[url]
            except KeyError:
              pass
            flash(u"Feed '{0}' updated.".format(title))
            description = urlize(feed_info.get('description',''))
            form.fill(csrf_token=csrf_token(),url=url,title=title,
                direction=form.d.direction,description=form.d.description)
            not_in_flock = not (url in get_flock_feeds(get_root_or_public_flock(global_db)))
            return render.timeline({'title':u'Channel: {0}'.format(feed_info['title']),
                'description':description,'feeds':[get_feed_render_info(url)],
                'feed_url':url,'site_url':feed_info.get('link'),'not_in_flock':not_in_flock,
                'max_page_entries':MAX_PAGE_ENTRIES,'expand_all_entries':True,'hide_feed':True,'edit_form':form,
                'max_feed_entries':MAX_FLOCK_FEED_ENTRIES,'feed_refresh_seconds':FEED_REFRESH_SECONDS})
        else:
            form.fill(csrf_token=csrf_token(),url=form.d.url,title=form.d.title,
                direction=form.d.direction,description=form.d.description)
            return render.editfeed({'form':form})

class view_newflock:
    def GET(self):
        form = edit_flock_form()
        form.fill(csrf_token=csrf_token())
        import_form = import_flockshare_form()
        import_form.fill(csrf_token=csrf_token(),verb='import')
        return render.editflock({'form':form,'import_form':import_form,'new':True})
    @csrf_protected
    def POST(self):
        if not global_account.is_logged_in():
            flash("You're not logged in. Can't add flock.")
            raise web.seeother('/')
        form = edit_flock_form()
        if form.validates():
            set_clipboard({'type':'flock','title':form.d.title,'description':form.d.description,'items':[]})
            flash('Your new flock is now in the clipboard.')
            return web.seeother('/')
        else:
            form.fill(csrf_token=csrf_token())
            import_form = flockshare_form()
            import_form.fill(csrf_token=csrf_token(),verb='import')
            return render.editflock({'form':form,'import_form':import_form,'new':True})

class view_editflock:
    def GET(self):
        flash("Sorry. Stale browser page. Please try again whatever you were doing.")
        raise web.seeother('/')
    @csrf_protected
    def POST(self):
        if not global_account.is_logged_in():
            flash("You're not logged in. Can't edit flock.")
            raise web.seeother('/')
        form = edit_flock_form()
        err = False
        if form.validates():
            root = get_root_or_public_flock(global_db)
            slug = form.d.flock
            path = slug and slug.split('_') or []
            node = flock_get(root,path)
            if not node or node.get('type')!='flock':
                flash('Flock not found. This can happen if you logout. Please try again.')
                return web.seeother('/')
            if path and form.d.title.lower()!=node['title'].lower():
                parent = flock_get(root,path[:-1])
                if parent and subflock(parent,form.d.title):
                    flash('Duplicate name. Please try again')
                    err = True
            if not err:
                node.update(title=form.d.title,description=form.d.description)
                save_root_flock(global_db,root)
                flash(u"Flock '{0}' updated.".format(form.d.title))
                feeds = map(get_feed_render_info,get_flock_feeds(node,respect_mutes=not form.d.show_mutes_tweak))
                description = urlize(node.get('description',''))
                form.fill(csrf_token=csrf_token(),flock=form.d.flock,
                    title=form.d.title,description=form.d.description)
                return render.timeline({'title':u'Channels: {0}'.format(node['title']),
                    'description':description,'feeds':feeds,'max_page_entries':MAX_PAGE_ENTRIES,
                    'expand_all_entries':False,'hide_feed':False,'edit_form':form,
                    'max_feed_entries':MAX_FLOCK_FEED_ENTRIES,'feed_refresh_seconds':FEED_REFRESH_SECONDS})
        else:
            err = True
        if err:
            form.fill(csrf_token=csrf_token(),flock=form.d.flock,title=form.d.title,description=form.d.description)
            return render.editflock({'form':form})

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
        feed_dict = JsonDb(global_db,"feed")
        is_a_known_feed = feed_dict.has_key(form.d.url)
        feed_info = get_feed_render_info(form.d.url,feed_dict)
        if not is_a_known_feed: # ugly patch
            feed_info['button_html'] = feed_info['button_html'].replace('Go','Reload')
        title = feed_info['title']
        description = urlize(feed_info.get('description',''))
        url = feed_info['url']
        not_in_flock = not (url in get_flock_feeds(get_root_or_public_flock(global_db)))
        if global_account.is_logged_in():
            edit_form = edit_feed_form()
            edit_form.fill(csrf_token=csrf_token(),url=form.d.url,title=feed_info['title'],
                description=feed_info.get('description'),direction=feed_info.get('rtl') and 'rtl' or 'ltr')
        else:
            edit_form = None
        return render.timeline({
            'title':u'Channel: {0}'.format(title),'description':description,'feeds':[feed_info],
            'feed_url':url,'site_url':feed_info.get('link'),'not_in_flock':not_in_flock,'edit_form':edit_form,
            'max_page_entries':MAX_PAGE_ENTRIES,'expand_all_entries':True,'hide_feed':is_a_known_feed,
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
        if global_account.is_logged_in():
            edit_form = edit_flock_form()
            edit_form.fill(csrf_token=csrf_token(),flock=form.d.flock,title=flock['title'],
                description=flock.get('description'),show_mutes_tweak=form.d.all)
        else:
            edit_form = None
        return render.timeline({'title':u'Channels: {0}'.format(title),'description':description,'feeds':feeds,
            'max_page_entries':MAX_PAGE_ENTRIES,'expand_all_entries':False,'hide_feed':False,'edit_form':edit_form,
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
    def GET(self):
        flash("Sorry. Stale browser page. Please try again.")
        raise web.seeother('/')
    @csrf_protected
    def POST(self):
        global_account.logout()
        flash('Goodbye.')
        raise web.seeother('/')

class view_settings:
    def GET(self):
        if not (global_account.is_logged_in() or global_account.is_new()):
            flash("You're not logged in. Can't change your password.")
            raise web.seeother('/')
        form = settings_form()
        form.fill(dict(global_account.get_profile(),csrf_token=csrf_token()))
        if global_account.is_new():
            form.inputs[1].attrs['style'] = 'display:none' # hide oldpass
            form.inputs[1].attrs['class'] = '' # remove focusme
            form.inputs[1].description = ''
        return render.settings({'form':form})
    @csrf_protected
    def POST(self):
        form=settings_form()
        if form.validates():
            if global_account.is_new() or global_account.check_password(form.d.oldpass):
                if form.d.newpass:
                    global_account._change_password(form.d.oldpass,form.d.newpass)
                link = form.d.link
                while link.endswith('/'): link = link[:-1]
                global_account._set_profile({'title':form.d.title,'description':form.d.description,'link':link})
                if global_account.is_new():
                    flash("Settings saved, but you need to choose a password.")
                    raise web.seeother('/settings')
                else:
                    flash("Your settings were saved.")
                raise web.seeother('/')
            flash("Incorrect password. Try again.")
        form.inputs[0].value = csrf_token()
        for i in range(3): # Don't leak passwords to html source :)
            form.inputs[i+1].value = ''
        if global_account.is_new(): # no use asking for current password
            form.inputs[1].attrs['style'] = 'display:none' # hide oldpass
            form.inputs[1].attrs['class'] = '' # remove focusme
            form.inputs[1].description = ''
        return render.settings({'form':form})

class view_favicon:
    def GET(self):
        raise web.redirect('/static/favicon.ico')

### Upgrades and patches
def stealth_upgrade():
    jdb = JsonDb(global_db)
    if jdb.get('cache_version',0)<1:
        global_db.query('drop table if exists jsondb_cache') # clear incompatible cache
        jdb['cache_version'] = 1

### Main
if __name__=="__main__":
    stealth_upgrade()
    app.run()
