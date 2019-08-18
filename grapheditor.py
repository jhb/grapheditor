import neo4j as neo4j
from chameleon import PageTemplate, PageTemplateLoader
from wtforms import Form, BooleanField, StringField, validators, widgets, SelectField
# from flask_wtf import FlaskForm as Form
import flask
from flask import request, url_for, redirect
from neo4j import GraphDatabase
from flask_socketio import SocketIO
from werkzeug.datastructures import MultiDict

api = flask.Flask(__name__)
api.secret_key = b'GraphIsGreat'
socketio = SocketIO(api)
driver = GraphDatabase.driver('bolt://localhost:7687')
session = driver.session()


class DictObject:

    def __init__(self, items):
        self._items = items
        self.labels = []
        for k, v in items:
            setattr(self, k, v)

    def items(self):
        return self._items


class TemplateWrapper:

    def __init__(self, template, **kwargs):
        self.template = template
        self.kwargs = kwargs

    def __call__(self, **kwargs):
        kwargs.update(self.kwargs)
        return self.template(**kwargs)


def getTemplate(name):
    templates = PageTemplateLoader('templates', '.pt')
    return TemplateWrapper(templates[name], flask=flask, templates=templates)


def getNodes():
    with driver.session() as session:
        result = session.run('match (n) return n order by id(n)')
        return [row['n'] for row in result]


@api.route('/nodelist')
def nodelist():
    nodes = getNodes()
    template = getTemplate('nodelist')
    return template(nodes=nodes)


def getNode(nid):
    with driver.session() as session:
        print('getNode',nid)
        #import ipdb; ipdb.set_trace()
        result = session.run("match (n) where id(n)={id} return n", id=nid)
        return result.single()['n']


def updateNode(node, items):
    nid = node.id
    itemsd = dict(items)
    print(itemsd)
    t = "n.%s = '%s'"
    parts = []
    for k, v in items:
        if k.startswith('new_') or k.startswith('labels') or k=='nid':
            continue
        parts.append(t % (k, v))
    if itemsd.get('new_name',''):
        parts.append(t % (itemsd['new_name'], itemsd['new_value']))
    statement = "MATCH (n) WHERE id(n) = %s " % nid

    oldlabels = set(node.labels)
    newlabels = set([l.strip() for l in itemsd['labels'].split(':')])
    toremove = oldlabels.difference(newlabels)
    toadd = newlabels.difference(oldlabels)

    if toremove:
        statement+='REMOVE n:%s ' % ':'.join(toremove)
    statement+="SET %s " % ', '.join(parts)
    if toadd:
        if parts:
            statement+=', '
        statement += "n:%s" % itemsd['labels']
    print(statement)
    with driver.session() as session:
        result = session.run(statement)
    return statement


def delNodeProperty(nid, propertyname):
    statement = """MATCH (n) WHERE id(n) = %s REMOVE n.%s""" % (nid, propertyname)
    with driver.session() as session:
        result = session.run(statement)


@api.route('/node/<nid>', methods=['GET', 'POST'])
def node(nid=7,req=None):
    node = getNode(int(nid))


    if 'delete' in request.args:
        delNodeProperty(nid, request.args['delete'])
        flask.flash('%s removed from node' % request.args['delete'])
        return flask.redirect(request.base_url)

    class MyForm(Form):
        pass

    MyForm.labels = StringField('labels', description='labels of the node')

    if request.method == 'POST':
        items = request.form.items()
        items = list(items)
    else:
        items = node.items()
        items = list(items)
        items.append(('labels', ':'.join(sorted(node.labels))))

    print(items)

    for k, v in sorted(items):
        setattr(MyForm, k, StringField(k, description='foo description'))
    MyForm.new_name = StringField('name', description='The name of the property')
    MyForm.new_value = StringField('value', description='The value of the new property')

    form = MyForm(request.form, DictObject(items))

    if request.method == 'POST' and form.validate():
        statement = updateNode(nid, items)
        flask.flash('Node %s updated <small> -- %s</small>' % (nid, statement))
        return flask.redirect('/node/%s' % nid)

    template = getTemplate('nodeform.pt')

    return template(form=form, node=node)


@api.route('/')
def index():
    template = getTemplate('index')
    return template()


@api.route('/favicon.ico')
def favicon():
    return redirect(url_for('static', filename='favicon.ico'))


def messageReceived(methods=['GET', 'POST']):
    print('message was received!!!')


@socketio.on('node clicked')
def handle_node_clicked(json,methods=['GET','POST']):
    print('node clicked',json)

def newnode(nid=7,formdata=None):
    node = getNode(int(nid))
    if 'delete' in request.args:
        delNodeProperty(nid, request.args['delete'])
        flask.flash('%s removed from node' % request.args['delete'])
        return flask.redirect(request.base_url)

    class MyForm(Form):
        pass

    MyForm.labels = StringField('labels', description='labels of the node')

    if formdata:
        items = formdata.items()
        items = list(items)
    else:
        items = node.items()
        items = list(items)
        items.append(('labels', ':'.join(sorted(node.labels))))

    print(items)

    for k, v in sorted(items):
        setattr(MyForm, k, StringField(k, description='foo description'))
    MyForm.new_name = StringField('name', description='The name of the property')
    MyForm.new_value = StringField('value', description='The value of the new property')

    form = MyForm(formdata, DictObject(items))

    if formdata and form.validate():
        statement = updateNode(node, items)
        #flask.flash('Node %s updated <small> -- %s</small>' % (nid, statement))
        #return flask.redirect('/node/%s' % nid)

    template = getTemplate('nodeform.pt')

    return template(form=form, node=node)



@socketio.on('gee')
def dispatch_ge_event(msg,methods=['GET','POST']):
    print('gee',msg)
    for func in eventroutes.get(msg['event'],[]):
        out = func(msg)
        if type(out)!=type([]):
            out=[out]
        for msg in out:
            emit(msg)

def shownodelist(msg):
    nodes = getNodes()
    msg = {'event':   'display',
           'section': 'graph',
           'occ': 'nodelist',
           'html':    getTemplate('nodelist')(nodes=getNodes())}
    return msg

def shownodeview(msg):
    print('show node view')
    nid = int(msg['nid'])
    msg = {'event':   'display',
           'section': 'view',
           'occ': nid,
           'html':    getTemplate('nodeview')(node=getNode(nid))}
    return msg

def shownodeform(msg,nid=None):
    if not nid:
        nid = int(msg['nid'])
    msg = {'event': 'display',
           'section': 'action',
           'occ': nid,
           'html': newnode(nid)}
    return msg

def nodesubmit(msg):
    nid = int(msg['formdata']['nid'])
    newnode(nid,MultiDict(msg['formdata'].items()))
    out=[shownodeform(msg,nid)]
    # newmsg = {'event':   'clear',
    #        'section': 'action'};
    # out = [newmsg]
    out.append(shownodelist(msg))
    if nid == msg['occupied']['view']:
        msg['nid']=nid
        out.append(shownodeview(msg))
    return out

def emit(msg):
    socketio.emit('gee', msg, callback=messageReceived)

eventroutes = {'init':[shownodelist],
               'node clicked':[shownodeview],
               'node hover': [shownodeview],
               'node edit': [shownodeform],
               'node submit': [nodesubmit]}

if __name__ == '__main__':
    print('x' * 30)
    socketio.run(api, debug=1, port=9000, )
