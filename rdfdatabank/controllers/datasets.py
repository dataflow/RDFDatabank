#-*- coding: utf-8 -*-
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

import logging
import re, os, shutil, codecs
import simplejson
from datetime import datetime, timedelta
from dateutil.relativedelta import *
#from dateutil.parser import parse
import time
from uuid import uuid4
from pylons import request, response, session, tmpl_context as c, url, app_globals as ag
from pylons.controllers.util import abort, redirect
from pylons.decorators import rest
from paste.fileapp import FileApp
from rdfdatabank.lib.base import BaseController, render
from rdfdatabank.lib.utils import create_new, get_readme_text, serialisable_stat, allowable_id2, natural_sort
from rdfdatabank.lib.utils import is_embargoed, test_rdf, munge_manifest, get_embargo_values, get_rdf_template, extract_metadata
from rdfdatabank.lib.file_unpack import get_zipfiles_in_dataset
from rdfdatabank.lib.conneg import MimeType as MT, parse as conneg_parse
from rdfdatabank.lib.auth_entry import add_dataset, delete_dataset, get_datasets_count, get_datasets

JAILBREAK = re.compile("[\/]*\.\.[\/]*")

log = logging.getLogger(__name__)

class DatasetsController(BaseController):      
    @rest.restrict('GET', 'POST')
    def siloview(self, silo):
        if not ag.granary.issilo(silo):
            abort(404)
        c.silo_name = silo
        ident = request.environ.get('repoze.who.identity')
        c.ident = ident

        http_method = request.environ['REQUEST_METHOD']

        if http_method == "GET":
            c.editor = False
            if ag.metadata_embargoed:
                if not ident:
                    abort(401, "Not Authorised")
                silos = ag.authz(ident)
                if silo not in silos:
                    abort(403, "Forbidden")
                c.editor = True
            else:
                if ident:
                    silos = ag.authz(ident)
                    if silo in silos:
                        c.editor = True

            options = request.GET
            c.start = 0
            if 'start' in options and options['start']:
                try:
                    c.start = int(options['start'])
                except ValueError:
                    c.start = 0
            c.rows = 100
            if 'rows' in options and options['rows']:
                try:
                    c.rows = int(options['rows'])
                except ValueError:
                    c.rows = 100
                 
            c_silo = ag.granary.get_rdf_silo(silo)
            # Get title of silo
            state_info = ag.granary.describe_silo(silo)
            if 'title' in state_info and state_info['title']:
                c.title = state_info['title']
            # Get number of data packages in silo
            numFound = get_datasets_count(silo)
            try:
                c.numFound = int(numFound)
            except ValueError:
                c.numFound = 0

            #c.embargos = {'params':{'numFound':numFound, 'start':c.start, 'rows':c.rows}}
            c.embargos = {}
            #for item in c_silo.list_items():
            for item in get_datasets(silo, start=c.start, rows=c.rows):
                try:
                    c.embargos[item] = is_embargoed(c_silo, item)
                except:
                    c.embargos[item] = None
            c.items = c.embargos.keys()
            # conneg return
            accept_list = None
            if 'HTTP_ACCEPT' in request.environ:
                try:
                    accept_list = conneg_parse(request.environ['HTTP_ACCEPT'])
                except:
                    accept_list= [MT("text", "html")]
            if not accept_list:
                accept_list= [MT("text", "html")]
            mimetype = accept_list.pop(0)
            while(mimetype):
                if str(mimetype).lower() in ["text/html", "text/xhtml"]:
                    #Calculate the pagination for display of data packages
                    c.permissible_offsets = []
                    c.pages_to_show = 5
                    try:
                        remainder = c.numFound % c.rows
                        if remainder > 0:
                            c.lastPage = c.numFound - remainder
                        else:
                            c.lastPage = c.numFound - c.rows

                        if c.numFound > c.rows:
                            offset_start = c.start - ( (c.pages_to_show/2) * c.rows )
                            if offset_start < 0:
                                offset_start = 0
         
                            offset_end = offset_start + (c.pages_to_show * c.rows)
                            if offset_end > c.numFound:
                                offset_end = c.numFound
                                if remainder > 0:
                                    offset_start = c.lastPage - (c.pages_to_show * c.rows)
                                else:
                                    offset_start = c.lastPage - ((c.pages_to_show-1) * c.rows)

                                if offset_start < 0:
                                    offset_start = 0
                              
                            c.permissible_offsets = list( xrange( offset_start, offset_end, c.rows) )
                    except ValueError:
                        pass
                    return render('/siloview.html')
                elif str(mimetype).lower() in ["text/plain", "application/json"]:
                    response.content_type = 'application/json; charset="UTF-8"'
                    response.status_int = 200
                    response.status = "200 OK"
                    return simplejson.dumps(c.embargos)
                try:
                    mimetype = accept_list.pop(0)
                except IndexError:
                    mimetype = None
            #Whoops nothing satisfies - return text/html            
            return render('/siloview.html')
        elif http_method == "POST":
            if not ident:
                abort(401, "Not Authorised")

            silos = ag.authz(ident)
            if silo not in silos:
                abort(403, "Forbidden")
            params = request.POST

            if not params.has_key("id"):
                response.content_type = "text/plain"
                response.status_int = 400
                response.status = "400 Bad Request: Parameter 'id' is not available"
                return "Parameter 'id' is not available"
                
            c_silo = ag.granary.get_rdf_silo(silo)        
            if c_silo.exists(params['id']):
                response.content_type = "text/plain"
                response.status_int = 409
                response.status = "409 Conflict: Data package already exists"
                return "Data package already exists"

            # Supported params:
            # id, title, embargoed, embargoed_until, embargo_days_from_now
            id = params['id']
            if not allowable_id2(id):
                response.content_type = "text/plain"
                response.status_int = 400
                response.status = "400 Bad request. Data package name not valid"
                return "Data package name can only contain %s"%ag.naming_rule_humanized
            del params['id']

            item = create_new(c_silo, id, ident['repoze.who.userid'], **params)
            add_dataset(silo, id)
            # Broadcast change as message
            try:
                ag.b.creation(silo, id, ident=ident['repoze.who.userid'])
            except:
                pass
                 
            # conneg return
            accept_list = None
            if 'HTTP_ACCEPT' in request.environ:
                try:
                    accept_list = conneg_parse(request.environ['HTTP_ACCEPT'])
                except:
                    accept_list= [MT("text", "html")]
            if not accept_list:
                accept_list= [MT("text", "html")]
            mimetype = accept_list.pop(0)
            while(mimetype):
                if str(mimetype).lower() in ["text/html", "text/xhtml"]:
                    redirect(url(controller="datasets", action="datasetview", silo=silo, id=id))
                elif str(mimetype).lower() in ["text/plain", "application/json"]:
                    response.content_type = "text/plain"
                    response.status_int = 201
                    response.status = "201 Created"
                    response.headers["Content-Location"] = url(controller="datasets", action="datasetview", silo=silo, id=id)
                    return "201 Created"
                try:
                    mimetype = accept_list.pop(0)
                except IndexError:
                    mimetype = None
            # Whoops - nothing satisfies - return text/plain
            response.content_type = "text/plain"
            response.status_int = 201
            response.headers["Content-Location"] = url(controller="datasets", action="datasetview", silo=silo, id=id)
            response.status = "201 Created"
            return "201 Created"
                    
    @rest.restrict('GET', 'POST', 'DELETE')
    def datasetview(self, silo, id):       
        if not ag.granary.issilo(silo):
            abort(404)
        # Check to see if embargo is on:
        c.silo_name = silo
        c.id = id

        http_method = request.environ['REQUEST_METHOD']

        ident = request.environ.get('repoze.who.identity')  
        c.ident = ident
        c_silo = ag.granary.get_rdf_silo(silo)

        c.version = None
        c.editor = False
        
        if not (http_method == "GET"):
            #identity management of item 
            if not request.environ.get('repoze.who.identity'):
                abort(401, "Not Authorised")
            silos = ag.authz(ident)
            if silo not in silos:
                abort(403, "Forbidden")
            silos_admin = ag.authz(ident, permission='administrator')
            silos_manager = ag.authz(ident, permission='manager')

        if http_method in ["GET", "DELETE"]:
            if not c_silo.exists(id):
                abort(404)

        if http_method == "GET":
            embargoed = False
            item = c_silo.get_item(id)

            options = request.GET

            currentversion = str(item.currentversion)
            c.version = currentversion
            if 'version' in options:
                if not options['version'] in item.manifest['versions']:
                    abort(404)
                c.version = str(options['version'])
                if c.version and not c.version == currentversion:
                    item.set_version_cursor(c.version)

            creator = None
            if item.manifest and item.manifest.state and 'metadata' in item.manifest.state and item.manifest.state['metadata'] and \
                'createdby' in item.manifest.state['metadata'] and item.manifest.state['metadata']['createdby']:
                creator = item.manifest.state['metadata']['createdby']

            if ag.metadata_embargoed:
                if not ident:
                    abort(401, "Not Authorised")
                silos = ag.authz(ident)
                if silo not in silos:
                    abort(403, "Forbidden")
                silos_admin = ag.authz(ident, permission='administrator')
                silos_manager = ag.authz(ident, permission='manager')
                if ident['repoze.who.userid'] == creator or silo in silos_admin or silo in silos_manager:
                    c.editor = True
            elif item.metadata.get('embargoed') not in ["false", 0, False]:
                #TODO: This will always provide the embargo information for the latest version.
                # The embargo status should always reflect the latest version, but should the embargo information displayed be that of the vesion???
                embargoed = True
                if ident:
                    silos = ag.authz(ident)      
                    silos_admin = ag.authz(ident, permission='administrator')
                    silos_manager = ag.authz(ident, permission='manager')
                    if silo in silos:
                        #if ident['repoze.who.userid'] == creator or ident.get('role') in ["admin", "manager"]:
                        if ident['repoze.who.userid'] == creator or silo in silos_admin or silo in silos_manager:
                            c.editor = True
            elif ident:
                silos = ag.authz(ident)
                silos_admin = ag.authz(ident, permission='administrator')
                silos_manager = ag.authz(ident, permission='manager')
                if silo in silos:
                    #if ident['repoze.who.userid'] == creator or ident.get('role') in ["admin", "manager"]:
                    if ident['repoze.who.userid'] == creator or silo in silos_admin or silo in silos_manager:
                        c.editor = True
            
            c.show_files = True
            #Only the administrator, manager and creator can view embargoed files.
            if embargoed and not c.editor:
                c.show_files = False

            #Display but do not edit previous versions of files, since preious versions are read only.
            if c.version and not c.version == currentversion:
                c.editor = False

            # View options
            if "view" in options and c.editor:
                c.view = options['view']
            elif c.editor:
                c.view = 'editor'
            else:
                c.view = 'user'

            c.embargos = {}
            c.embargos[id] = is_embargoed(c_silo, id)
            c.parts = item.list_parts(detailed=True)
            c.manifest_pretty = item.rdf_to_string(format="pretty-xml")
            c.metadata = None
            c.metadata = extract_metadata(item)
            c.versions = item.manifest['versions']
            c.versions = natural_sort(c.versions)
            #c.manifest = item.rdf_to_string()
            c.manifest = get_rdf_template(item.uri, id)
            c.zipfiles = get_zipfiles_in_dataset(item)
            c.readme_text = None
            #if item.isfile("README"):
            if "README" in c.parts.keys():
                c.readme_text = get_readme_text(item)
            #if item.manifest:
            #    state = item.manifest.state
                    
            # conneg:
            accept_list = None
            if 'HTTP_ACCEPT' in request.environ:
                try:
                    accept_list = conneg_parse(request.environ['HTTP_ACCEPT'])
                except:
                    accept_list= [MT("text", "html")]
            if not accept_list:
                accept_list= [MT("text", "html")]
            mimetype = accept_list.pop(0)
            
            while(mimetype):
                if str(mimetype).lower() in ["text/html", "text/xhtml"]:
                    return render('/datasetview.html')
                elif str(mimetype).lower() in ["text/plain", "application/json"]:
                    response.content_type = 'application/json; charset="UTF-8"'
                    returndata = {}
                    returndata['embargos'] = c.embargos
                    returndata['view'] = c.view
                    returndata['show_files'] = c.show_files
                    returndata['editor'] = c.editor
                    returndata['parts'] = {}
                    for part in c.parts:
                        returndata['parts'][part] = serialisable_stat(c.parts[part])
                    returndata['readme_text'] = c.readme_text
                    returndata['manifest_pretty'] = c.manifest_pretty
                    returndata['manifest'] = c.metadata
                    returndata['zipfiles'] = c.zipfiles
                    if c.version:
                        returndata['version'] = c.version
                    #items['state'] = state
                    response.status_int = 200
                    response.status = "200 OK"
                    return simplejson.dumps(returndata)
                elif str(mimetype).lower() in ["application/rdf+xml", "text/xml"]:
                    response.status_int = 200
                    response.status = "200 OK"
                    response.content_type = 'application/rdf+xml; charset="UTF-8"'
                    return c.manifest_pretty
                elif str(mimetype).lower() == "text/rdf+n3":
                    response.content_type = 'text/rdf+n3; charset="UTF-8"'
                    response.status_int = 200
                    response.status = "200 OK"
                    return item.rdf_to_string(format="n3")
                elif str(mimetype).lower() == "application/x-turtle":
                    response.content_type = 'application/x-turtle; charset="UTF-8"'
                    response.status_int = 200
                    response.status = "200 OK"
                    return item.rdf_to_string(format="turtle")
                elif str(mimetype).lower() in ["text/rdf+ntriples", "text/rdf+nt"]:
                    response.content_type = 'text/rdf+ntriples; charset="UTF-8"'
                    response.status_int = 200
                    response.status = "200 OK"
                    return item.rdf_to_string(format="nt")
                # Whoops - nothing satisfies
                try:
                    mimetype = accept_list.pop(0)
                except IndexError:
                    mimetype = None
            #Whoops - nothing staisfies - default to text/html
            return render('/datasetview.html')
        elif http_method == "POST":
            code = None
            params = request.POST
            #Create new dataset if it does not exist
            if not c_silo.exists(id):
                if not allowable_id2(id):
                    response.content_type = "text/plain"
                    response.status_int = 400
                    response.status = "400 Bad request. Data package name not valid"
                    return "Data package name can contain only the following characters - %s and has to be more than 1 character"%ag.naming_rule_humanized
                item = create_new(c_silo, id, ident['repoze.who.userid'])
                add_dataset(silo, id)
                code = 201
                response.status = "201 Created"
                response.status_int = 201
                response.headers["Content-Location"] = url(controller="datasets", action="datasetview", id=id, silo=silo)
                response_message = "201 Created empyt data package"
            #Update embargo info
            if params.has_key('embargoed') and params['embargoed']:
                item = c_silo.get_item(id)
                creator = None
                if item.manifest and item.manifest.state and 'metadata' in item.manifest.state and item.manifest.state['metadata'] and \
                    'createdby' in item.manifest.state['metadata'] and item.manifest.state['metadata']['createdby']:
                    creator = item.manifest.state['metadata']['createdby']
                #if not (ident['repoze.who.userid'] == creator or ident.get('role') in ["admin", "manager"]):
                if not (ident['repoze.who.userid'] == creator or silo in silos_admin or silo in silos_manager):
                    abort(403)
                if not params['embargoed'].lower() in ['true', 'false', '0', '1']:
                    abort(400, "The value for embargoed has to be either 'True' or 'False'")

                item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf'])
                if params.has_key('embargoed_until') and params['embargoed_until']:
                    e, e_d = get_embargo_values(embargoed=params['embargoed'], embargoed_until=params['embargoed_until'])
                elif params.has_key('embargo_days_from_now') and params['embargo_days_from_now']:
                    e, e_d = get_embargo_values(embargoed=params['embargoed'], embargo_days_from_now=params['embargo_days_from_now'])
                else:
                    e, e_d = get_embargo_values(embargoed=params['embargoed'])
                item.metadata['embargoed_until'] = ''
                item.del_triple(item.uri, u"oxds:isEmbargoed")
                item.del_triple(item.uri, u"oxds:embargoedUntil")
                try:   
                    ag.r.set("%s:%s:embargoed_until" % (c_silo.state['storage_dir'], id), ' ')
                except:
                    pass

                if e:
                    item.metadata['embargoed'] = True
                    item.add_triple(item.uri, u"oxds:isEmbargoed", 'True')
                    try:
                        ag.r.set("%s:%s:embargoed" % (c_silo.state['storage_dir'], id), True)
                    except:
                        pass
                    if e_d:
                        item.metadata['embargoed_until'] = e_d
                        item.add_triple(item.uri, u"oxds:embargoedUntil", e_d)
                        try:
                            ag.r.set("%s:%s:embargoed_until" % (c_silo.state['storage_dir'], id), e_d)
                        except:
                            pass
                else:
                    item.metadata['embargoed'] = False
                    item.add_triple(item.uri, u"oxds:isEmbargoed", 'False')
                    try:
                        ag.r.set("%s:%s:embargoed" % (c_silo.state['storage_dir'], id), False)
                    except:
                        pass

                item.del_triple(item.uri, u"dcterms:modified")
                item.add_triple(item.uri, u"dcterms:modified", datetime.now())
                item.del_triple(item.uri, u"oxds:currentVersion")
                item.add_triple(item.uri, u"oxds:currentVersion", item.currentversion)
                item.sync()

                if not code:
                    code = 204
                    response.content_type = "text/plain"
                    response.status_int = 204
                    response.status = "204 Updated"
                    response_message = None
            if params.has_key('file'):
                # File upload by a not-too-savvy method - Service-orientated fallback:
                # Assume file upload to 'filename'
                item = c_silo.get_item(id)
                creator = None
                if item.manifest and item.manifest.state and 'metadata' in item.manifest.state and item.manifest.state['metadata'] and \
                    'createdby' in item.manifest.state['metadata'] and item.manifest.state['metadata']['createdby']:
                    creator = item.manifest.state['metadata']['createdby']
                #if not (ident['repoze.who.userid'] == creator or ident.get('role') in ["admin", "manager"]):
                if not (ident['repoze.who.userid'] == creator or silo in silos_admin or silo in silos_manager):
                    abort(403)

                upload = params.get('file')
                #if not upload:
                #    abort(400, "No file was received")
                filename = params.get('filename')
                if not filename:
                    filename = params['file'].filename
                if filename and JAILBREAK.search(filename) != None:
                    abort(400, "'..' cannot be used in the path or as a filename")
                target_path = filename
                
                if item.isfile(target_path):
                    code = 204
                elif item.isdir(target_path):
                    response.content_type = "text/plain"
                    response.status_int = 403
                    response.status = "403 Forbidden"
                    return "Cannot POST a file on to an existing directory"
                else:
                    code = 201

                if filename == "manifest.rdf":
                    #Copy the uploaded file to a tmp area 
                    #mani_file = os.path.join('/tmp', filename.lstrip(os.sep))
                    mani_file = os.path.join('/tmp', uuid4().hex)
                    mani_file_obj = open(mani_file, 'w')
                    shutil.copyfileobj(upload.file, mani_file_obj)
                    upload.file.close()
                    mani_file_obj.close()
                    #test rdf file
                    if not test_rdf(mani_file):
                        response.status_int = 400
                        return "Bad manifest file"
                    #munge rdf
                    item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf'])
                    a = item.get_rdf_manifest()
                    b = a.to_string()
                    #munge_manifest(manifest_str, item)
                    munge_manifest(mani_file, item)
                else:
                    if code == 204:
                        item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf', filename])
                    else:
                        item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf'])
                    item.put_stream(target_path, upload.file)
                    upload.file.close()
                item.del_triple(item.uri, u"dcterms:modified")
                item.add_triple(item.uri, u"dcterms:modified", datetime.now())
                item.del_triple(item.uri, u"oxds:currentVersion")
                item.add_triple(item.uri, u"oxds:currentVersion", item.currentversion)
                item.sync()
                
                if code == 201:
                    try:
                        ag.b.creation(silo, id, target_path, ident=ident['repoze.who.userid'])
                    except:
                        pass
                    response.status = "201 Created"
                    response.status_int = 201
                    response.headers["Content-Location"] = url(controller="datasets", action="itemview", id=id, silo=silo, path=filename)
                    response_message = "201 Created. Added file %s to item %s" % (filename, id)
                else:
                    try:
                        ag.b.change(silo, id, target_path, ident=ident['repoze.who.userid'])
                    except:
                        pass
                    response.status = "204 Updated"
                    response.status_int = 204
                    response_message = None
            elif params.has_key('text'):
                # Text upload convenience service
                item = c_silo.get_item(id)
                filename = params.get('filename')
                if not filename:
                    abort(400, "Bad Request. Must supply a filename")
                if JAILBREAK.search(filename) != None:
                    abort(400, "'..' cannot be used in the path or as a filename")

                creator = None
                if item.manifest and item.manifest.state and 'metadata' in item.manifest.state and item.manifest.state['metadata'] and \
                    'createdby' in item.manifest.state['metadata'] and item.manifest.state['metadata']['createdby']:
                    creator = item.manifest.state['metadata']['createdby']
                #if not (ident['repoze.who.userid'] == creator or ident.get('role') in ["admin", "manager"]):
                if not (ident['repoze.who.userid'] == creator or silo in silos_admin or silo in silos_manager):
                    abort(403)
                
                target_path = filename
                
                if item.isfile(target_path):
                    code = 204
                elif item.isdir(target_path):
                    response.content_type = "text/plain"
                    response.status_int = 403
                    response.status = "403 forbidden"
                    return "Cannot POST a file on to an existing directory"
                else:
                    code = 201
                
                if filename == "manifest.rdf":
                    # valid to make sure it's valid RDF
                    # Otherwise this dataset will not be accessible
                    text = params['text']
                    fname = '/tmp/%s'%uuid4().hex
                    f = codecs.open(fname, 'w', 'utf-8')
                    #f = open(fname, 'w')
                    f.write(text)
                    f.close()
                    #if not test_rdf(text):
                    if not test_rdf(fname):
                        abort(400, "Not able to parse RDF/XML")
                    item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf'])
                    a = item.get_rdf_manifest()
                    b = a.to_string()
                    munge_manifest(fname, item)
                    os.remove(fname)
                else:
                    if code == 204:
                        item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf', filename])
                    else:
                        item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf'])
                    item.put_stream(target_path, params['text'].encode("utf-8"))
                item.del_triple(item.uri, u"dcterms:modified")
                item.add_triple(item.uri, u"dcterms:modified", datetime.now())
                item.del_triple(item.uri, u"oxds:currentVersion")
                item.add_triple(item.uri, u"oxds:currentVersion", item.currentversion)
                item.sync()
                
                if code == 201:
                    try:
                        ag.b.creation(silo, id, target_path, ident=ident['repoze.who.userid'])
                    except:
                        pass
                    response.status = "201 Created"
                    response.status_int = 201
                    response.headers["Content-Location"] = url(controller="datasets", action="datasetview", id=id, silo=silo)
                    response_message = "201 Created. Added file %s to item %s" % (filename, id)
                else:
                    try:
                        ag.b.change(silo, id, target_path, ident=ident['repoze.who.userid'])
                    except:
                        pass
                    response.status = "204 Updated"
                    response.status_int = 204
                    response_message = None
            if not code:
                response.content_type = "text/plain"
                response.status_int = 400
                response.status = "400 Bad request"
                return "400 Bad Request. No valid parameters found."
            # conneg return
            accept_list = None
            if 'HTTP_ACCEPT' in request.environ:
                try:
                    accept_list = conneg_parse(request.environ['HTTP_ACCEPT'])
                except:
                    accept_list= [MT("text", "html")]
            if not accept_list:
                accept_list= [MT("text", "html")]
            mimetype = accept_list.pop(0)
            while(mimetype):
                if str(mimetype).lower() in ["text/html", "text/xhtml"]:
                    redirect(url(controller="datasets", action="datasetview", id=id, silo=silo))
                elif str(mimetype).lower() in ["text/plain", "application/json"]:
                    response.content_type = "text/plain"
                    return response_message
                try:
                    mimetype = accept_list.pop(0)
                except IndexError:
                    mimetype = None
            #Whoops - nothing satisfies - return text / plain
            response.content_type = "text/plain"
            return response_message
        elif http_method == "DELETE":
            item = c_silo.get_item(id)
            creator = None
            if item.manifest and item.manifest.state and 'metadata' in item.manifest.state and item.manifest.state['metadata'] and \
                'createdby' in item.manifest.state['metadata'] and item.manifest.state['metadata']['createdby']:
                creator = item.manifest.state['metadata']['createdby']
            #if not (ident['repoze.who.userid'] == creator or ident.get('role') in ["admin", "manager"]):
            if not (ident['repoze.who.userid'] == creator or silo in silos_admin or silo in silos_manager):
                abort(403)

            try:
                ag.r.delete("%s:%s:embargoed_until" % (c_silo.state['storage_dir'], id))
                ag.r.delete("%s:%s:embargoed" % (c_silo.state['storage_dir'], id))
            except:
                pass

            # Broadcast deletion
            try:
                ag.b.deletion(silo, id, ident=ident['repoze.who.userid'])
            except:
                pass

            c_silo.del_item(id)
            delete_dataset(silo, id)
            
            response.content_type = "text/plain"
            response.status_int = 200
            response.status = "200 OK"
            return "{'ok':'true'}" # required for the JQuery magic delete to succede.

    @rest.restrict('GET', 'POST', 'PUT', 'DELETE')
    def itemview(self, silo, id, path):
        if not ag.granary.issilo(silo):
            abort(404)

        c.silo_name = silo
        c.id = id
        c.path = path

        c_silo = ag.granary.get_rdf_silo(silo)   
        if not c_silo.exists(id):
            abort(404)

        ident = request.environ.get('repoze.who.identity')  
        c.ident = ident
        item = c_silo.get_item(id)
        creator = None
        if item.manifest and item.manifest.state and 'metadata' in item.manifest.state and item.manifest.state['metadata'] and \
            'createdby' in item.manifest.state['metadata'] and item.manifest.state['metadata']['createdby']:
            creator = item.manifest.state['metadata']['createdby']

        c.version = None
        c.editor = False
       
        http_method = request.environ['REQUEST_METHOD']
        
        if not (http_method == "GET"):
            #identity management of item 
            if not request.environ.get('repoze.who.identity'):
                abort(401, "Not Authorised")
            silos = ag.authz(ident)      
            if silo not in silos:
                abort(403, "Forbidden")
            silos_admin = ag.authz(ident, permission='administrator')
            silos_manager = ag.authz(ident, permission='manager')
            #if not (ident['repoze.who.userid'] == creator or ident.get('role') in ["admin", "manager"]):
            if not (ident['repoze.who.userid'] == creator or silo in silos_admin or silo in silos_manager):
                abort(403, "Forbidden")
        elif http_method == "GET":
            embargoed = False
            options = request.GET

            currentversion = str(item.currentversion)
            c.version = currentversion
            if 'version' in options:
                if not options['version'] in item.manifest['versions']:
                    abort(404)
                c.version = str(options['version'])
                if c.version and not c.version == currentversion:
                    item.set_version_cursor(c.version)

            if ag.metadata_embargoed:
                if not ident:
                    abort(401, "Not Authorised")
                silos = ag.authz(ident)      
                if silo not in silos:
                    abort(403, "Forbidden")
                silos_admin = ag.authz(ident, permission='administrator')
                silos_manager = ag.authz(ident, permission='manager')
                #if ident['repoze.who.userid'] == creator or ident.get('role') in ["admin", "manager"]:
                if ident['repoze.who.userid'] == creator or silo in silos_admin or silo in silos_manager:
                    c.editor = True
            elif item.metadata.get('embargoed') not in ["false", 0, False]:
                if not ident:
                    abort(401)
                silos = ag.authz(ident)      
                if silo not in silos:
                    abort(403)
                silos_admin = ag.authz(ident, permission='administrator')
                silos_manager = ag.authz(ident, permission='manager')
                #if not ident['repoze.who.userid'] == creator and not ident.get('role') in ["admin", "manager"]:
                if not (ident['repoze.who.userid'] == creator or silo in silos_admin or silo in silos_manager):
                    abort(403)
                embargoed = True
                c.editor = True                   
            elif ident:
                silos = ag.authz(ident)
                silos_admin = ag.authz(ident, permission='administrator')
                silos_manager = ag.authz(ident, permission='manager')
                if silo in silos:
                    #if ident['repoze.who.userid'] == creator or ident.get('role') in ["admin", "manager"]:
                    if ident['repoze.who.userid'] == creator or silo in silos_admin or silo in silos_manager:
                        c.editor = True

            c.show_files = True
            #Only the administrator, manager and creator can view embargoed files.
            if embargoed and not c.editor:
                c.show_files = False

            #Display but do not edit previous versions of files, since preious versions are read only.
            if c.version and not c.version == currentversion:
                c.editor = False

            # View options
            if "view" in options and c.editor:
                c.view = options['view']
            elif c.editor:
                c.view = 'editor'
            else:
                c.view = 'user'
        
        if http_method == "GET":
            if item.isfile(path):
                fileserve_app = FileApp(item.to_dirpath(path))
                return fileserve_app(request.environ, self.start_response)
            elif item.isdir(path):
                #c.parts = item.list_parts(detailed=True)
                c.versions = item.manifest['versions']
                c.versions = natural_sort(c.versions)
                c.parts = item.list_parts(path, detailed=True)
                c.readme_text = None
                if "README" in c.parts.keys():
                    c.readme_text = get_readme_text(item, "%s/README" % path)
                    
                accept_list = None
                if 'HTTP_ACCEPT' in request.environ:
                    try:
                        accept_list = conneg_parse(request.environ['HTTP_ACCEPT'])
                    except:
                        accept_list= [MT("text", "html")]
                if not accept_list:
                    accept_list= [MT("text", "html")]
                mimetype = accept_list.pop(0)
                while(mimetype):
                    if str(mimetype).lower() in ["text/html", "text/xhtml"]:
                        return render("/itemview.html")
                    elif str(mimetype).lower() in ["text/plain", "application/json"]:
                        response.content_type = 'application/json; charset="UTF-8"'
                        response.status_int = 200
                        response.status = "200 OK"
                        returndata = {}
                        returndata['parts'] = {}
                        for part in c.parts:
                            returndata['parts'][part] = serialisable_stat(c.parts[part])
                        returndata['readme_text'] = c.readme_text
                        return simplejson.dumps(returndata)
                    try:
                        mimetype = accept_list.pop(0)
                    except IndexError:
                        mimetype = None
                #Whoops - nothing satisfies - return text/html
                return render("/itemview.html")
            else:
                abort(404)
        elif http_method == "PUT":
            # Pylons loads the request body into request.body...
            # This is not going to work for large files... ah well
            # POST will handle large files as they are pushed to disc,
            # but this won't
            content = request.body
                
            if JAILBREAK.search(path) != None:
                abort(400, "'..' cannot be used in the path")
                    
            if item.isfile(path):
                code = 204
            elif item.isdir(path):
                response.content_type = "text/plain"
                response.status_int = 403
                response.status = "403 Forbidden"
                return "Cannot PUT a file on to an existing directory"
            else:
                code = 201

            #Check if path is manifest.rdf - If, yes Munge
            if "manifest.rdf" in path:
                fname = '/tmp/%s'%uuid4().hex
                f = open(fname, 'w')
                f.write(content)
                f.close()
                #test content is valid rdf
                #if not test_rdf(content):
                "Manifest file created:", fname
                if not test_rdf(fname):
                    response.status_int = 400
                    return "Bad manifest file"
                #munge rdf
                item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf'])
                a = item.get_rdf_manifest()
                b = a.to_string()
                #munge_manifest(content, item)
                munge_manifest(fname, item)
                os.remove(fname)
            else:
                if code == 204:
                    item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf', path])
                else:
                    item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf'])
                item.put_stream(path, content)
            item.del_triple(item.uri, u"dcterms:modified")
            item.add_triple(item.uri, u"dcterms:modified", datetime.now())
            item.del_triple(item.uri, u"oxds:currentVersion")
            item.add_triple(item.uri, u"oxds:currentVersion", item.currentversion)
            item.sync()
                
            if code == 201:
                try:
                    ag.b.creation(silo, id, path, ident=ident['repoze.who.userid'])
                except:
                    pass
                response.status = "201 Created"
                response.status_int = 201
                response.headers["Content-Location"] = url(controller="datasets", action="itemview", id=id, silo=silo, path=path)
                response_message = "201 Created"
            else:
                try:
                    ag.b.change(silo, id, path, ident=ident['repoze.who.userid'])
                except:
                    pass
                response.status = "204 Updated"
                response.status_int = 204
                response_message = None
            
            # conneg return
            accept_list = None
            if 'HTTP_ACCEPT' in request.environ:
                try:
                    accept_list = conneg_parse(request.environ['HTTP_ACCEPT'])
                except:
                    accept_list= [MT("text", "html")]
            if not accept_list:
                accept_list= [MT("text", "html")]
            mimetype = accept_list.pop(0)
            while(mimetype):
                if str(mimetype).lower() in ["text/html", "text/xhtml"]:
                    redirect(url(controller="datasets", action="itemview", id=id, silo=silo, path=path))
                elif str(mimetype).lower() in ["text/plain", "application/json"]:
                    response.content_type = "text/plain"
                    return response_message
                try:
                    mimetype = accept_list.pop(0)
                except IndexError:
                    mimetype = None
            #Whoops - nothing satisfies - return text / plain
            response.content_type = "text/plain"
            return response_message
        elif http_method == "POST":
            # POST... differences from PUT:
            # path = filepath that this acts on, should be dir, or non-existant
            # if path is a file, this will revert to PUT's functionality and
            # overwrite the file, if there is a multipart file uploaded
            # Expected params: filename, file (uploaded file)
            params = request.POST
            if not params.has_key('file'):
                abort(400, "No file was received")
            filename = params.get('filename')
            upload = params.get('file')
            if not filename:
                filename = params['file'].filename
            if filename and JAILBREAK.search(filename) != None:
                abort(400, "'..' cannot be used in the path or as a filename")
            target_path = path
            if item.isdir(path) and filename:
                target_path = os.path.join(path, filename)
                
            if item.isfile(target_path):
                code = 204
            elif item.isdir(target_path):
                response.content_type = "text/plain"
                response.status_int = 403
                response.status = "403 Forbidden"
                return "Cannot POST a file on to an existing directory"
            else:
                code = 201

            if filename == "manifest.rdf":
                #Copy the uploaded file to a tmp area 
                #mani_file = os.path.join('/tmp', filename.lstrip(os.sep))
                mani_file = os.path.join('/tmp', uuid4().hex)
                mani_file_obj = open(mani_file, 'w')
                shutil.copyfileobj(upload.file, mani_file_obj)
                upload.file.close()
                mani_file_obj.close()
                #test rdf file
                if not test_rdf(mani_file):
                    response.status_int = 400
                    return "Bad manifest file"
                #munge rdf
                item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf'])
                a = item.get_rdf_manifest()
                b = a.to_string()
                #munge_manifest(manifest_str, item)
                munge_manifest(mani_file, item)
                os.remove(mani_file)
            else:
                if code == 204:
                    item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf', filename])
                else:
                    item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf'])                
                item.put_stream(target_path, upload.file)
                upload.file.close()
            item.del_triple(item.uri, u"dcterms:modified")
            item.add_triple(item.uri, u"dcterms:modified", datetime.now())
            item.del_triple(item.uri, u"oxds:currentVersion")
            item.add_triple(item.uri, u"oxds:currentVersion", item.currentversion)
            item.sync()
                
            if code == 201:
                try:
                    ag.b.creation(silo, id, target_path, ident=ident['repoze.who.userid'])
                except:
                    pass
                response.status = "201 Created"
                response.status_int = 201
                response.headers["Content-Location"] = url(controller="datasets", action="itemview", id=id, silo=silo, path=path)
                response_message = "201 Created"
            else:
                try:
                    ag.b.change(silo, id, target_path, ident=ident['repoze.who.userid'])
                except:
                    pass
                response.status = "204 Updated"
                response.status_int = 204
                response_message = None

            # conneg return
            accept_list = None
            if 'HTTP_ACCEPT' in request.environ:
                try:
                    accept_list = conneg_parse(request.environ['HTTP_ACCEPT'])
                except:
                    accept_list= [MT("text", "html")]
            if not accept_list:
                accept_list= [MT("text", "html")]
            mimetype = accept_list.pop(0)
            while(mimetype):
                if str(mimetype).lower() in ["text/html", "text/xhtml"]:
                    redirect(url(controller="datasets", action="itemview", id=id, silo=silo, path=path))
                elif str(mimetype).lower() in ["text/plain", "application/json"]:
                    response.content_type = "text/plain"
                    return response_message
                try:
                    mimetype = accept_list.pop(0)
                except IndexError:
                    mimetype = None
            #Whoops - nothing satisfies - return text / plain
            response.content_type = "text/plain"
            return response_message
        elif http_method == "DELETE":
            if item.isfile(path):
                if 'manifest.rdf' in path:
                    response.content_type = "text/plain"
                    response.status_int = 403
                    response.status = "403 Forbidden"
                    return "Forbidden - Cannot delete the manifest"
                if '3=' in path or '4=' in path:
                    response.content_type = "text/plain"
                    response.status_int = 403
                    response.status = "403 Forbidden"
                    return "Forbidden - These files are generated by the system and connot be deleted"
                item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf'])
                item.del_stream(path)
                item.del_triple(item.uri, u"dcterms:modified")
                item.add_triple(item.uri, u"dcterms:modified", datetime.now())
                item.del_triple(item.uri, u"oxds:currentVersion")
                item.add_triple(item.uri, u"oxds:currentVersion", item.currentversion)
                item.sync()
                try:
                    #ag.b.deletion(silo, id, path, ident=ident['repoze.who.userid'])
                    ag.b.change(silo, id, path, ident=ident['repoze.who.userid'])
                except:
                    pass
                response.content_type = "text/plain"
                response.status_int = 200
                response.status = "200 OK"
                return "{'ok':'true'}"   # required for the JQuery magic delete to succede.
            elif item.isdir(path):
                item.increment_version_delta(clone_previous_version=True, copy_filenames=['manifest.rdf'])
                item.del_triple(item.uri, u"oxds:currentVersion")
                item.add_triple(item.uri, u"oxds:currentVersion", item.currentversion)
                item.del_dir(path)
                item.del_triple(item.uri, u"dcterms:modified")
                item.add_triple(item.uri, u"dcterms:modified", datetime.now())
                item.sync()
                try:
                    #ag.b.deletion(silo, id, path, ident=ident['repoze.who.userid'])
                    ag.b.change(silo, id, path, ident=ident['repoze.who.userid'])
                except:
                    pass
                response.content_type = "text/plain"
                response.status_int = 200
                response.status = "200 OK"
                return "{'ok':'true'}"   # required for the JQuery magic delete to succede.
            else:
                abort(404)

