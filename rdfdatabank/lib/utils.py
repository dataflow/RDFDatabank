# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from dateutil.relativedelta import *
from dateutil.parser import parse
from time import sleep
from redis import Redis
from redis.exceptions import ConnectionError
import os
import simplejson

from pylons import app_globals as ag

from rdflib import ConjunctiveGraph
from StringIO import StringIO
from rdflib import StringInputSource
#from rdflib.parser import StringInputSource
from rdflib import Namespace, RDF, RDFS, URIRef, Literal, BNode


from uuid import uuid4
import re

ID_PATTERN = re.compile(r"^[0-9A-z\-\:]+$")

def authz(granary_list,ident):
    g = ag.granary
    g.state.revert()
    g._register_silos()
    granary_list = g.silos
    def _parse_owners(silo_name):
        kw = g.describe_silo(silo_name)
        if "owners" in kw.keys():
            owners = [x.strip() for x in kw['owners'].split(",") if x]
            return owners
        else:
            return []
    if 'role' in ident and ident['role'] == "admin":
        authd = []
        silos_owned = ident['owner']
        if '*' in silos_owned:
            #User has access to all silos
            return granary_list
        for item in granary_list:
            if item in silos_owned:
                authd.append(item)
            else:
                owners = _parse_owners(item)
                if '*' in owners:
                    #All users have access to the silo
                    authd.append(item)
                if ident['repoze.who.userid'] in owners:
                    authd.append(item)
        return authd
    else:
        authd = []
        silos_owned = ident['owner']
        for item in granary_list:
            if item in silos_owned:
                authd.append(item)
            else:
                owners = _parse_owners(item)
                if ident['repoze.who.userid'] in owners:
                    authd.append(item)
        return authd

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
    e = ag.r.get("%s:%s:embargoed" % (silo.state['storage_dir'], id))
    e_d = ag.r.get("%s:%s:embargoed_until" % (silo.state['storage_dir'], id))

    if refresh or (not e or not e_d):
        if silo.exists(id):
            item = silo.get_item(id)
            e = item.metadata.get("embargoed")
            e_d = item.metadata.get("embargoed_until")
            if e not in ['false', 0, False]:
                e = True
            else:
                e = False
            ag.r.set("%s:%s:embargoed" % (silo.state['storage_dir'], id), e)
            ag.r.set("%s:%s:embargoed_until" % (silo.state['storage_dir'], id), e_d)
    return (e, e_d)

def is_embargoed_no_redis(silo, id, refresh=False):
    #Redis kept crashing for silos with a largo number of data packages (~80,000). I tried re-connecting, it didn't work. 
    #So not using Redis
    # TODO evaluate ag.r.expire settings for these keys - popularity resets ttl or increases it?
    if silo.exists(id):
        item = silo.get_item(id)
        e = item.metadata.get("embargoed")
        e_d = item.metadata.get("embargoed_until")
        if e not in ['false', 0, False]:
            e = True
        else:
            e = False
    return (e, e_d)

def create_new(silo, id, creator, title=None, embargoed=True, embargoed_until=None, embargo_days_from_now=None, **kw):
    item = silo.get_item(id, startversion="0")
    item.metadata['createdby'] = creator
    item.metadata['embargoed_until'] = ''
    item.metadata['uuid'] = uuid4().hex
    item.add_namespace('oxds', "http://vocab.ox.ac.uk/dataset/schema#")
    item.add_triple(item.uri, u"rdf:type", "oxds:DataSet")

    if embargoed==True or embargoed.lower() in ['true', '1'] :
        item.metadata['embargoed'] = True
        item.add_triple(item.uri, u"oxds:isEmbargoed", 'True')
        embargoed_until_date = None
        if embargoed_until:
            try:
                embargoed_until_date = parse(embargoed_until).isoformat()
            except:
                embargoed_until_date = (datetime.now() + relativedelta(years=+70)).isoformat()
        elif embargo_days_from_now and embargo_days_from_now.isdigit():
            embargoed_until_date = (datetime.now() + timedelta(days=int(embargo_days_from_now))).isoformat()
        #TODO: Do we want the default embargo_until to be 70 years or indefinite. Going with indefinite
        #else:
        #    embargoed_until_date = (datetime.now() + relativedelta(years=+70)).isoformat()
        if embargoed_until_date:
            item.metadata['embargoed_until'] = embargoed_until_date
            item.add_triple(item.uri, u"oxds:embargoedUntil", embargoed_until_date)
    else:
        item.add_triple(item.uri, u"oxds:isEmbargoed", 'False')
        item.metadata['embargoed'] = False
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
    #fname = '/tmp/%s'%uuid4().hex
    #f = codecs.open(fname, 'w', 'utf-8')
    #f.write(manifest_str)
    #f.close()
    
    g = ConjunctiveGraph()
    #gparsed = g.parse(StringInputSource(manifest_str), format='xml')
    #gparsed = g.parse(StringIO(manifest_str), format='xml')
    gparsed = g.parse(manifest_file, format='xml')
    for s,p,o in gparsed.triples((None, RDF.type, None)):
        mani_types.append(str(o))
    #os.remove(fname) 
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


