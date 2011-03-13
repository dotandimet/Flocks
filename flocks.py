# -*- coding: utf-8 -*-
import web

### config
DB_FILENAME = 'flocks.db'
DEFAULT_FLOCK_FILENAME = 'default_flock.js'
LOGIN_TIMEOUT = 60
DEBUG_DB = False
###

urls = (
    "/", "view_flock",
    "/login","view_login",
    "/logout","view_logout",
    "/set_password","view_set_password",
)

app = web.application(urls, globals())
global_db = web.database(dbn='sqlite',db=DB_FILENAME)

# Session/debug tweak from http://webpy.org/cookbook/session_with_reloader
if web.config.get('_session') is None:
    session = web.session.Session(app, web.session.DiskStore('sessions'))
    web.config._session = session
else:
    session = web.config._session

# The flash() trick I've learned from flask
def flash(msg):
    flashes = session.get('flashed_messages',[])
    session['flashed_messages'] = flashes+[msg]

def pop_flashed_messages():
    flashes = session.get('flashed_messages',[])
    session['flashed_messages'] = []
    return flashes
    
    

#### CSRF protection
def csrf_token():
    """In the template, you should add inside your POST forms:
  <input type=hidden name=csrf_token value="$csrf_token()">
You'll need to initialize your render object like:
  web.template.render('templates',globals={'csrf_token':csrf_token})"""
    if not session.has_key('csrf_token'):
        from uuid import uuid4
        session.csrf_token=uuid4().hex
    return session.csrf_token

def csrf_protected(f):
    """Usage:
  @csrf_protected
  def POST(self):
      ...
(Remember to have a csrf_token() hidden field at the form itself)"""
    def decorated(*args,**kwargs):
        inp = web.input()
        if not (inp.has_key('csrf_token') and inp.csrf_token==session.pop('csrf_token',None)):
            raise web.HTTPError(
                "400 Bad request",
                {'content-type':'text/html'},
                'CSRF forgery (or stale browser form). <a href="">Back to the form</a>')
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

### Sam - Single accout manager

# some time utils
import datetime
def now(): return datetime.datetime.now()
def seconds2delta(secs): return datetime.timedelta(0,secs)
def tuple2datetime(t): return datetime.datetime(*tuple[6:])
def datetime2str(dt): return dt.strftime('%Y-%m-%dT%H:%M:%S')
def str2datetime(s): return datetime.datetime.strptime(s,'%Y-%m-%dT%H:%M:%S')

class Sam:
    def __init__(self,db,app):
        self.jdb = JsonDb(db,"sam")
        self.app = app
        self.is_new = not self.jdb.has_key('passhash')
        self.loadhook()
        self.app.add_processor(lambda handler: [self.loadhook(),handler()][1])

    def loadhook(self):
        expires = session.get('sam_expires')
        if expires:
            if now()<str2datetime(expires):
                self._set_logged_in()
                return
            else:
                flash("Automatically logged out because of idle time.")
        self._set_logged_out()

    def _set_logged_in(self):
        session['sam_expires'] = datetime2str(now()+seconds2delta(LOGIN_TIMEOUT))
        self.is_logged_in = True
    
    def _set_logged_out(self):
        self.is_logged_in = False
        if session.has_key('sam_expires'):
            del session['sam_expires']

    def _check_password(self,password):
        assert not self.is_new,"Attempt to check password with empty account"
        import hmac
        return hmac.new(self.jdb['key'].decode('hex'),password).hexdigest() == self.jdb['passhash']

    def login(self,password):
        if self._check_password(password):
            self._set_logged_in()
            return True
        self._set_logged_out()
        return False

    def logout(self):
        self._set_logged_out()

    def change_password(self,oldpass,newpass):
        "oldpass is ignored if self.is_new"
        if self.is_new or self._check_password(oldpass):
            import hmac
            from os import urandom
            key = urandom(20)
            self.jdb.update({
                'key':key.encode('hex'),
                'passhash':hmac.new(key,newpass).hexdigest()})
            self.is_new = False
            self._set_logged_in()
            return True
        return False
    
### Flock functions
def flockslug(obj):
    "Receives a name string or a flock node (dict). Returns an html-safe slug. Case insensitive."
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

def get_flock_feeds(flock,respect_mutes=False):
    "Get all urls of feeds (leafs) in a flock tree. If respect_mutes, ignores mute feeds"
    feeds=set()
    if respect_mutes and flock.get('mute'):
        return feeds
    flocktype=flock.get('type')
    if flocktype=='feed':
        feeds.add(flock.get('url'))
    elif flocktype=='flock':
        feeds = feeds.union(*[get_flock_feeds(i,respect_mutes) for i in flock.get('items',[])])
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
    for k in ['title','description','link']:
        if k=='link' or not myfeed.has_key(k): # link is always updated
            v=otherfeed.get(k,'').strip()
            if v:
                myfeed[k]=v

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
    "At the moment, always returns root flock!!!! Will be fixed soon"
    jdb = JsonDb(db)
    if jdb.has_key('flock'):
        root = jdb['flock']
    else:
        root = import_flock_file(db,DEFAULT_FLOCK_FILENAME)
        jdb['flock'] = root
    if global_account.is_logged_in:
        return root
    return subflock(root,'public') or {'type':'flock','title':'No public flock','items':[]}

### our single account manager
global_account = Sam(global_db,app)

### Render objects
render_globals = {
    'ctx':web.ctx, # handy environment info
    'account':global_account,
    'flashes':pop_flashed_messages,
    'csrf_token':csrf_token # to enable csrf_token() hidden fields
}

render = web.template.render('templates',base='layout',globals=render_globals)

# plain_render doesn't use a page layout wrapper
# for partial render, xml, etc.
plain_render = web.template.render('templates',globals=render_globals)

### Views
class view_flock:
    def GET(self):
        flock = flock_cachify(get_root_or_public_flock(global_db),feed_dict=JsonDb(global_db,"feed"))
        return render.index({
            'title':flock.get('title','[untitled]'),
            'description':flock.get('description',''),
            'items':[flock_render(item,plain_render.flocknode) for item in flock.get('items',[])] })

class view_login:
    login_form = web.form.Form(
        web.form.Password("password",description="Password",tabindex=1))
    def GET(self):
        if global_account.is_new: # can't login to an empty nest
            flash("Can't login to an empty nest.")
            return web.redirect(web.url('/'))
        return render.login({'form':self.login_form()})
    @csrf_protected
    def POST(self):
        form = self.login_form()
        if form.validates() and global_account.login(form.d.password):
            flash('You have been logged in.')
            return web.redirect(web.url('/'))
        form.fill(password='') # we don't want password hints in the html source
        flash('Wrong password. Please try again.')
        return render.login({'form':self.login_form()})

class view_logout:
    @csrf_protected
    def POST(self):
        global_account.logout()
        flash('You have been logged out.')
        return web.redirect(web.url('/'))

class view_set_password:
    password_form = web.form.Form(
        web.form.Password("oldpass",description="Old password",tabindex=1),
        web.form.Password("newpass",
            web.form.Validator("must be at least 8 characters",lambda x:len(x)>=8),
            description="New password",tabindex=2),
        web.form.Password("newagain",description="New password again",tabindex=3),
        validators = [
            web.form.Validator("Passwords didn't match.", lambda i: i.newpass == i.newagain)
        ]
    )
    def GET(self):
        if not (global_account.is_logged_in or global_account.is_new):
            flash("You're not logged in. Can't change your password.")
            return web.redirect(web.url('/'))
        form = self.password_form()
        if global_account.is_new:
            form.inputs[0].attrs['style'] = 'display:none'
            form.inputs[0].description = ''
        return render.set_password({'form':form})
    @csrf_protected
    def POST(self):
        form=self.password_form()
        if form.validates():
            if global_account.change_password(form.d.oldpass,form.d.newpass):
                flash("Your password was saved.")
                return web.redirect(web.url('/'))
            flash("Incorrect password. Try again.")
        form.fill(oldpass='',newpass='',newagain='') # we don't want password hints in the html source
        if global_account.is_new:
            form.inputs[0].attrs['style'] = 'display:none'
            form.inputs[0].description = ''
        return render.set_password({'form':form})

if __name__ == "__main__":
   app.run()
