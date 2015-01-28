# -*- coding: utf-8 -*-
"""
Copyright (c) 2012 University of Oxford

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, --INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

from datetime import datetime, timedelta
from dateutil.relativedelta import *
from dateutil.parser import parse
from time import sleep, strftime
import os
import simplejson

from pylons import app_globals as ag

from rdflib import ConjunctiveGraph
from StringIO import StringIO
from rdflib import StringInputSource
from rdflib import Namespace, RDF, RDFS, URIRef, Literal, BNode

import uuid
import re
from collections import defaultdict

from rdfdatabank.lib.auth_entry import list_silos, list_user_groups
from rdfdatabank.config.namespaces import NAMESPACES

ID_PATTERN = re.compile(r"^[0-9A-z\-\:]+$")

def authz(ident, permission=[]):
    #NOTE: g._register_silos() IS AN EXPENSIVE OPERATION. LISTING SILOS FROM DATABASE INSTEAD
    #g = ag.granary
    #g.state.revert()
    #g._register_silos()
    #granary_list = g.silos
    granary_list = list_silos()
    if permission and not type(permission).__name__ == 'list':
        permission = [permission]
    if not permission:
        permission = [] 
    silos = []
    if not ident or not 'user' in ident or not ident['user'] or not ident['user'].groups:
        return silos
    for i in ident['user'].groups:
        if i.silo == '*':
            return granary_list
        if i.silo in granary_list and not i.silo in silos:
            if not permission:
                silos.append(i.silo)
            else:
                 for p in i.permissions:
                     if p.permission_name in permission:
                         silos.append(i.silo)
    """
    user_groups = list_user_groups(ident['repoze.who.userid'])
    for g,p in user_groups:
        if g == '*':
            f = open('/var/log/databank/authz.log', 'a')
            f.write('List of all Silos: %s\n'%str(granary_list))
            f.write('List of user groups: %s\n'%str(user_groups))
            f.write('Permissions to match: %s\n'%str(permission))
            f.write('Group is *. Returning all silos\n\n')
            f.close()
            return granary_list
        if g in granary_list and not g in silos:
            if not permission:
                silos.append(g)
            elif p in permission:
                silos.append(g)
    f = open('/var/log/databank/authz.log', 'a')
    f.write('List of all Silos: %s\n'%str(granary_list))
    f.write('List of user groups: %s\n'%str(user_groups))
    f.write('Permissions to match: %s\n'%str(permission))
    f.write('List of auth Silos: %s\n\n'%str(silos))
    f.close()
    """
    return silos

def allowable_id(identifier):
    if ID_PATTERN.match(identifier):
        return identifier

def allowable_id2(strg):
    if len(strg) < 2 or ' ' in strg:
        return False
    search=re.compile(r'%s'%ag.naming_rule).search
    return not bool(search(strg))

def is_embargoed(silo, id, refresh=False):
    # TODO evaluate ag.r.expire settings for these keys - popularity resets ttl or increases it?
    e = None
    e_d = None
    #try:
    #    e = ag.r.get("%s:%s:embargoed" % (silo.state['storage_dir'], id))
    #    e_d = ag.r.get("%s:%s:embargoed_until" % (silo.state['storage_dir'], id))
    #except:
    #    pass

    if refresh or not e or not e_d:
        if silo.exists(id):
            item = silo.get_item(id)
            e = item.metadata.get("embargoed")
            e_d = item.metadata.get("embargoed_until")
            if e not in ['false', 0, False]:
                e = True
            else:
                e = False
            #try:
            #    ag.r.set("%s:%s:embargoed" % (silo.state['storage_dir'], id), e)
            #    ag.r.set("%s:%s:embargoed_until" % (silo.state['storage_dir'], id), e_d)
            #except:
                pass
    return (e, e_d)

def get_embargo_values(embargoed=None, embargoed_until=None, embargo_days_from_now=None):
    if isinstance(embargoed, basestring):
        embargoed = embargoed.strip()
    if isinstance(embargoed_until, basestring):
        embargoed_until = embargoed_until.strip()
    if isinstance(embargo_days_from_now, basestring):
        embargo_days_from_now = embargo_days_from_now.strip()
    e_status=None
    e_date=None
    if embargoed == None:
        #No embargo details are supplied by user
        e_status = True
        e_date = (datetime.now() + relativedelta(years=+70)).isoformat()
    elif embargoed==True or embargoed.lower() in ['true', '1'] :
        #embargo status is True
        e_status = True
        e_date = None
        if embargoed_until:
            try:
                e_date = parse(embargoed_until, dayfirst=True, yearfirst=False).isoformat()
            except:
                e_date = (datetime.now() + relativedelta(years=+70)).isoformat()
        elif embargo_days_from_now:
            if embargo_days_from_now.isdigit():
                e_date = (datetime.now() + timedelta(days=int(embargo_days_from_now))).isoformat()
            else:
                e_date = (datetime.now() + relativedelta(years=+70)).isoformat()
    elif embargoed==False or embargoed.lower() in ['false', '0'] :
        e_status = False
    else:
        #Default case: Treat it as though embargo=None
        e_status = True
        e_date = (datetime.now() + relativedelta(years=+70)).isoformat()
    return (e_status, e_date)

def create_new(silo, id, creator, title=None, embargoed=None, embargoed_until=None, embargo_days_from_now=None, **kw):
    item = silo.get_item(id, startversion="0")
    item.metadata['createdby'] = creator
    try:
        item.metadata['uuid'] = uuid.UUID(id).hex
    except:
        item.metadata['uuid'] = uuid.uuid4().hex
    item.add_namespace('oxds', "http://vocab.ox.ac.uk/dataset/schema#")
    item.add_triple(item.uri, u"rdf:type", "oxds:DataSet")

    item.metadata['embargoed_until'] = ''
    item.del_triple(item.uri, u"oxds:isEmbargoed")
    item.del_triple(item.uri, u"oxds:embargoedUntil")
    try:
        ag.r.set("%s:%s:embargoed_until" % (silo.state['storage_dir'], id), ' ')
    except:
        pass
    e, e_d = get_embargo_values(embargoed=embargoed, embargoed_until=embargoed_until, embargo_days_from_now=embargo_days_from_now)
    if e:
        item.metadata['embargoed'] = True
        item.add_triple(item.uri, u"oxds:isEmbargoed", 'True')
        try:
            ag.r.set("%s:%s:embargoed" % (silo.state['storage_dir'], id), True)
        except:
            pass
        if e_d:
            item.metadata['embargoed_until'] = e_d
            item.add_triple(item.uri, u"oxds:embargoedUntil", e_d)
            try:
                ag.r.set("%s:%s:embargoed_until" % (silo.state['storage_dir'], id), e_d)
            except:
                pass
    else:
        item.metadata['embargoed'] = False
        item.add_triple(item.uri, u"oxds:isEmbargoed", 'False')
        try:
            ag.r.set("%s:%s:embargoed" % (silo.state['storage_dir'], id), False)
        except:
            pass

    item.add_triple(item.uri, u"dcterms:identifier", id)
    item.add_triple(item.uri, u"dcterms:mediator", creator)
    item.add_triple(item.uri, u"dcterms:publisher", ag.publisher)
    item.add_triple(item.uri, u"dcterms:created", datetime.now())
    item.add_triple(item.uri, u"oxds:currentVersion", item.currentversion)
    if ag.rights and ag.rights.startswith('http'):
        item.add_triple(item.uri, u"dcterms:rights", URIRef(ag.rights))
    elif ag.rights:
        item.add_triple(item.uri, u"dcterms:rights", Literal(ag.rights))
    if ag.license and ag.license.startswith('http'):
        item.add_triple(item.uri, u"dcterms:license", URIRef(ag.license))
    elif ag.license:
        item.add_triple(item.uri, u"dcterms:license", Literal(ag.license))
    
    #TODO: Add current version metadata
    if title:
        item.add_triple(item.uri, u"rdfs:label", title)
    item.sync()
    return item

def get_readme_text(item, filename="README"):
    with item.get_stream(filename) as fn:
        text = fn.read().decode("utf-8")
    return u"%s\n\n%s" % (filename, text)

def get_rdf_template(item_uri, item_id):
    g = ConjunctiveGraph(identifier=item_uri)
    g.bind('rdf', 'http://www.w3.org/1999/02/22-rdf-syntax-ns#')
    g.bind('dcterms', 'http://purl.org/dc/terms/')
    g.add((URIRef(item_uri), URIRef('http://purl.org/dc/terms/identifier'), Literal(item_id)))
    data2 = g.serialize(format='xml', encoding="utf-8") + '\n'
    return data2

#def test_rdf(text):
def test_rdf(mfile):
    g = ConjunctiveGraph()
    try:
        g = g.parse(mfile, format='xml')
        return True
    except Exception as inst:
        return False

def munge_manifest(manifest_file, item):    
    #Get triples from the manifest file and remove the file
    triples = None
    ns = None
    seeAlsoFiles = None
    ns, triples, seeAlsoFiles = read_manifest(item, manifest_file)
    if ns and triples:
        for k, v in ns.iteritems():
            item.add_namespace(k, v)
        for (s, p, o) in triples:
            if str(p) == 'http://purl.org/dc/terms/title':
                try:
                    item.del_triple(URIRef(s), u"dcterms:title")
                except:
                    pass    
            if str(p) == 'http://purl.org/dc/terms/license':
                try:
                    item.del_triple(URIRef(s), u"dcterms:license")
                except:
                    pass
            if str(p) == 'http://purl.org/dc/terms/rights':
                try:
                    item.del_triple(URIRef(s), u"dcterms:rights")
                except:
                    pass
        for (s, p, o) in triples:
            item.add_triple(s, p, o)
    manifest_file_name = os.path.basename(manifest_file)
    item.manifest['versionlog'][item.currentversion].append('Updated file manifest.rdf')
    item.sync()
    if seeAlsoFiles:
        for fileuri in seeAlsoFiles:
            fullfilepath = None
            filepath = fileuri.replace(item.uri, '').strip().lstrip('/')
            fullfilepath = item.to_dirpath(filepath=filepath)
            if fullfilepath and item.isfile(fullfilepath):
                ans = test_rdf(fullfilepath)
                #with item.get_stream(filepath) as fn:
                #    text = fn.read()
                #if test_rdf(text):
                #    munge_manifest(text, item)
                if ans:
                    munge_manifest(fullfilepath, item)
    return True

def read_manifest(item, manifest_file):
    triples = []
    namespaces = {}
    seeAlsoFiles = []
    oxdsClasses = ['http://vocab.ox.ac.uk/dataset/schema#Grouping', 'http://vocab.ox.ac.uk/dataset/schema#DataSet']

    aggregates = item.list_rdf_objects(item.uri, "ore:aggregates")
    
    g = ConjunctiveGraph()
    gparsed = g.parse(manifest_file, format='xml')
    namespaces = dict(g.namespaces())
    #Get the subjects
    subjects = {}
    for s in gparsed.subjects():
        if s in subjects:
            continue
        if type(s).__name__ == 'URIRef':
            if str(s).startswith('file://'):
                ss = str(s).replace('file://', '')
                if manifest_file in ss:
                    subjects[s] = URIRef(item.uri)
                else:
                    manifest_file_path, manifest_file_name = os.path.split(manifest_file)
                    ss = ss.replace(manifest_file_path, '').strip('/')
                    for file_uri in aggregates:
                        if ss in str(file_uri):
                            subjects[s] = URIRef(file_uri)
                            break
                    if not s in subjects:
                        subjects[s] = URIRef(item.uri)
            else:
                subjects[s] = URIRef(s)
        elif type(s).__name__ == 'BNode':
            replace_subject = True
            for o in gparsed.objects():
                if o == s:
                    replace_subject = False
            if replace_subject:
                subjects[s] = URIRef(item.uri)
            else:
                subjects[s] = s
    #Get the dataset type 
    #set the subject uri to item uri if it is of type as defined in oxdsClasses
    datasetType = False
    for s,p,o in gparsed.triples((None, RDF.type, None)):
        if str(o) in oxdsClasses:
            if type(s).__name__ == 'URIRef' and len(s) > 0 and str(s) != str(item.uri) and str(subjects[s]) != str(item.uri):
                namespaces['owl'] = URIRef("http://www.w3.org/2002/07/owl#")
                triples.append((item.uri, 'owl:sameAs', s))
                triples.append((item.uri, RDF.type, o))              
            elif type(s).__name__ == 'BNode' or len(s) == 0 or str(s) == str(item.uri) or str(subjects[s]) == str(item.uri):
                gparsed.remove((s, p, o))
            subjects[s] = item.uri

    #Get the uri for the see also files
    for s,p,o in gparsed.triples((None, URIRef('http://www.w3.org/2000/01/rdf-schema#seeAlso'), None)):
        if type(o).__name__ == 'URIRef' and len(o) > 0:
            obj = str(o)
            if obj.startswith('file://'):
                obj_path, obj_name = os.path.split(obj)
                obj = obj.replace(obj_path, '').strip('/')
            for file_uri in aggregates:
                if obj in str(file_uri):
                    seeAlsoFiles.append(file_uri)
        gparsed.remove((s, p, o))

    #Add remaining triples
    for s,p,o in gparsed.triples((None, None, None)):
        triples.append((subjects[s], p, o))
    return namespaces, triples, seeAlsoFiles

def manifest_type(manifest_file):
    mani_types = []
    g = ConjunctiveGraph()
    gparsed = g.parse(manifest_file, format='xml')
    for s,p,o in gparsed.triples((None, RDF.type, None)):
        mani_types.append(str(o))
    if "http://vocab.ox.ac.uk/dataset/schema#DataSet" in mani_types:
        return "http://vocab.ox.ac.uk/dataset/schema#DataSet"
    elif "http://vocab.ox.ac.uk/dataset/schema#Grouping" in mani_types:
        return "http://vocab.ox.ac.uk/dataset/schema#Grouping"
    return None

def serialisable_stat(stat):
    stat_values = {}
    for f in ['st_atime', 'st_blksize', 'st_blocks', 'st_ctime', 'st_dev', 'st_gid', 'st_ino', 'st_mode', 'st_mtime', 'st_nlink', 'st_rdev', 'st_size', 'st_uid']:
        try:
            stat_values[f] = stat.__getattribute__(f)
        except AttributeError:
            pass
    return stat_values

def natural_sort(l): 
    convert = lambda text: int(text) if text.isdigit() else text.lower() 
    alphanum_key = lambda key: [ convert(c) for c in re.split('([0-9]+)', key) ] 
    return sorted(l, key = alphanum_key)

def extract_metadata(item):
    g = item.get_graph()
    m = defaultdict(list)
    for s,p,o in g.triples((URIRef(item.uri), None, None)):
        if type(o).__name__ == 'BNode':
            continue
        if 'oxds' in o or "http://vocab.ox.ac.uk/dataset/schema#" in o:
            continue
        term = g.qname(p).split(':', 1)[1]
        if term in ['created', 'date', 'modified', 'dateAccepted', 'dateCopyrighted', 'dateSubmitted', 'embargoedUntil']:
            try:
                dt = formatDate(str(o))
            except:
                dt = o
            m[g.qname(p)].append(dt)
        else:
            try:
                m[g.qname(p)].append(o.strip())
            except:
                m[g.qname(p)].append(o)
    for s,p,o in g.triples((None, NAMESPACES['bibo']['doi'], None)):
        if str(s).startswith(str(item.uri)):
            try:
                m[g.qname(p)].append(o.strip())
            except:
                m[g.qname(p)].append(o)
    return dict(m)

def formatDate(dt):
    dt_human = dt
    try:
        dt_obj = parse(dt, dayfirst=True, yearfirst=False)
        dt_human = dt_obj.strftime("%B %d %Y, %I:%M %p")
    except:
        return dt
    return dt_human

def getSiloModifiedDate(silo_name):
    solr_params = {}
    solr_params['q'] = "silo:%s"%silo_name
    solr_params['wt'] = 'json'
    solr_params['start'] = 0
    solr_params['rows'] = 1
    solr_params['sort'] = "modified desc"
    solr_params['fl'] = 'modified'
    solr_response = None
    try:
        solr_response = ag.solr.raw_query(**solr_params)
        result = simplejson.loads(solr_response)
    except:
        return ''
    if not solr_response:
        return ''
    docs = result['response'].get('docs',None)
    numFound = result['response'].get('numFound',None)
    if docs and len(docs) > 0 and docs[0] and 'modified' in  docs[0] and len(docs[0]['modified']) > 0:
        dt = docs[0]['modified'][0]
    else:
        return ''
    dt = formatDate(dt)
    return dt 

