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

"""Pylons middleware initialization"""

#from paste import httpexceptions
from beaker.middleware import CacheMiddleware, SessionMiddleware
from paste.cascade import Cascade
from paste.registry import RegistryManager
from paste.urlparser import StaticURLParser
from paste.deploy.converters import asbool
from pylons import config
from pylons.middleware import ErrorHandler, StatusCodeRedirect
from pylons.wsgiapp import PylonsApp
from routes.middleware import RoutesMiddleware

from rdfdatabank.config.environment import load_environment

from repoze.who.config import make_middleware_with_config as make_who_with_config

from webob.exc import HTTPNotFound

class FilteredApp(object):
    ''' 
    Only allow access when path_info starts with 'path', otherwise throw 404
    '''
    def __init__(self, app, path):
        self.app = app
        self.path = path
   
    def __call__(self, environ, start_response):
        if self.path and environ['PATH_INFO'].startswith(self.path):
            environ['PATH_INFO'] = environ['PATH_INFO'][len(self.path):] or '/'
            environ['SCRIPT_NAME'] += self.path
        #    return self.app(environ, start_response)
        #else:
        #    raise HTTPNotFound()
        return self.app(environ, start_response)

def make_app(global_conf, full_stack=True, static_files=True, **app_conf):
    """Create a Pylons WSGI application and return it

    ``global_conf``
        The inherited configuration for this application. Normally from
        the [DEFAULT] section of the Paste ini file.

    ``full_stack``
        Whether this application provides a full WSGI stack (by default,
        meaning it handles its own exceptions and errors). Disable
        full_stack when this application is "managed" by another WSGI
        middleware.

    ``static_files``
        Whether this application serves its own static files; disable
        when another web server is responsible for serving them.

    ``app_conf``
        The application's local configuration. Normally specified in
        the [app:<name>] section of the Paste ini file (where <name>
        defaults to main).

    """
    # Configure the Pylons environment
    load_environment(global_conf, app_conf)

    # The Pylons WSGI app
    app = PylonsApp()

    #app = httpexceptions.make_middleware(app, global_conf)
    #if asbool(config['debug']):
    #    from repoze.profile.profiler import AccumulatingProfileMiddleware
    #    app = AccumulatingProfileMiddleware(
    #       app,
    #       log_filename=app_conf['profile.log_filename'],
    #       discard_first_request=True,
    #       flush_at_shutdown=True,
    #       path=app_conf['profile.path']
    #       )

    # Routing/Session/Cache Middleware
    app = RoutesMiddleware(app, config['routes.map'])
    app = SessionMiddleware(app, config)
    app = CacheMiddleware(app, config)

    #TODO: Check if the new error controller works with sword server
    # CUSTOM MIDDLEWARE HERE (filtered by error handling middlewares)
    if asbool(full_stack):
        # Handle Python exceptions
        app = ErrorHandler(app, global_conf, **config['pylons.errorware'])

        # Display error documents for 401, 403, 404 status codes (and
        # 500 when debug is disabled)
        if asbool(config['debug']):
            app = StatusCodeRedirect(app)
        else:
            app = StatusCodeRedirect(app, [400, 401, 403, 404, 500])
    
    app = make_who_with_config(app, global_conf, app_conf['who.config_file'], app_conf['who.log_file'], app_conf['who.log_level'])

    # Establish the Registry for this application
    app = RegistryManager(app)

    if asbool(static_files):
        # Serve static files
        static_app = StaticURLParser(config['pylons.paths']['static_files'])
        if config['base.path']:
            static_app = FilteredApp(static_app, config['base.path'])
        app = Cascade([static_app, app])
    if config['base.path']:
        app = FilteredApp(app, config['base.path'])
    return app
