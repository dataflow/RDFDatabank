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

"""The application's Globals object"""

from pylons import config

from recordsilo import Granary
from redis import Redis

from rdfdatabank.lib.utils import authz
from rdfdatabank.lib.data_sync import sync_members
from rdfdatabank.lib.htpasswd import HtpasswdFile
from rdfdatabank.lib.broadcast import BroadcastToRedis

#from rdfdatabank.config.users import _USERS
from rdfdatabank.config.namespaces import NAMESPACES, PREFIXES

class Globals(object):

    """Globals acts as a container for objects available throughout the
    life of the application

    """

    def __init__(self):
        """One instance of Globals is created during application
        initialization and is available during requests via the
        'app_globals' variable

        """
        
        self.authz = authz
        #self.users = _USERS
        self.NAMESPACES = NAMESPACES
        self.PREFIXES = PREFIXES

        if config.has_key("granary.uri_root"):
            self.root = config['granary.uri_root']
       
        if config.has_key("granary.store"):
            self.granary = Granary(config['granary.store'])

        self.base = config.get("base.path", "")
        self.base = self.base.strip()
        if self.base and not self.base.endswith("/"):
            self.base = self.base + "/"
            
        if config.has_key("redis.host"):
            self.redishost = config['redis.host']
            try:
                self.r = Redis(self.redishost)
            except:
                self.r = None
            if self.r and config.has_key("broadcast.to") and config['broadcast.to'] == "redis" and  config.has_key("broadcast.queue"):
                self.b = BroadcastToRedis(config['redis.host'], config['broadcast.queue'])
        else:
            self.r = None
            self.redishost = None
            self.b = None
            
        if config.has_key("solr.host"):
            from solr import SolrConnection
            self.solrhost = config['solr.host']
            try:
                self.solr = SolrConnection(self.solrhost)
            except:
                self.solr = None
        else:
            self.solrhost = None
            self.solr = None
        
        if config.has_key("naming_rule"):
            self.naming_rule = config['naming_rule']

        if config.has_key("naming_rule_humanized"):
            self.naming_rule_humanized = config['naming_rule_humanized']
        elif config.has_key("naming_rule"):
            self.naming_rule_humanized = config['naming_rule']

        if config.has_key("metadata.embargoed"):
            self.metadata_embargoed = config['metadata.embargoed']
            if isinstance(self.metadata_embargoed, basestring):
                if self.metadata_embargoed.lower().strip() == 'true':
                    self.metadata_embargoed = True
                else:
                    self.metadata_embargoed = False
            elif not type(self.metadata_embargoed).__name__ == 'bool':
                self.metadata_embargoed = False
        else:
            self.metadata_embargoed = False

        if config.has_key("auth.file"):
            pwdfile = config['auth.file']
            self.passwdfile = HtpasswdFile(pwdfile)
            self.passwdfile.load()
         
        if config.has_key("auth.info"):
            self.userfile = config['auth.info']

        if config.has_key("doi.count"):
            self.doi_count_file = config['doi.count']
        
        if config.has_key("formats_served"):
            self.formats_served = config['formats_served']
        else:
            self.formats_served = ["text/html", "text/xhtml", "text/plain", "application/json", "application/rdf+xml", "text/xml"]

        if config.has_key("publisher"):
            self.publisher = config['publisher']
        else:
            self.publisher = "Bodleian Libraries, University of Oxford"

        if config.has_key("rights"):
            self.rights = config['rights']
      
        if config.has_key("license"):
            self.license = config['license']

        if config.has_key("api.version"):
            self.api_version = config['api.version']

        try:
            sync_members(self.granary)
        except:
            pass
